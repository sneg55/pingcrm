"""AI Message Composer using Anthropic Claude API."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.interaction import Interaction

logger = logging.getLogger(__name__)

# Retry configuration for transient Anthropic API errors.
_RETRY_TRANSIENT_STATUS_CODES = {429, 500, 529}
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0  # seconds
_RETRY_BACKOFF_FACTOR = 2.0
_RETRY_JITTER = 0.5  # ± seconds


async def _call_anthropic_with_retry(client: Any, **kwargs) -> Any:
    """Call client.messages.create with exponential backoff on transient errors.

    Retries on APIStatusError with status codes in _RETRY_TRANSIENT_STATUS_CODES.
    Raises the last exception if all attempts are exhausted.
    """
    from anthropic import APIStatusError  # noqa: PLC0415

    last_exc: Exception | None = None
    for attempt in range(_RETRY_MAX_ATTEMPTS):
        try:
            return await asyncio.wait_for(
                client.messages.create(**kwargs),
                timeout=30,
            )
        except APIStatusError as exc:
            if exc.status_code not in _RETRY_TRANSIENT_STATUS_CODES:
                raise
            last_exc = exc
        except asyncio.TimeoutError as exc:
            last_exc = exc

        if attempt < _RETRY_MAX_ATTEMPTS - 1:
            delay = _RETRY_BASE_DELAY * (_RETRY_BACKOFF_FACTOR ** attempt)
            jitter = random.uniform(-_RETRY_JITTER, _RETRY_JITTER)
            sleep_time = max(0.0, delay + jitter)
            logger.warning(
                "_call_anthropic_with_retry: transient error on attempt %d/%d, "
                "retrying in %.2fs: %s",
                attempt + 1, _RETRY_MAX_ATTEMPTS, sleep_time, last_exc,
            )
            await asyncio.sleep(sleep_time)

    raise last_exc  # type: ignore[misc]


_TWEET_CACHE_TTL = 12 * 60 * 60  # 12 hours


async def _fetch_twitter_context(
    contact: Contact, user: Any = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Fetch recent tweets and bio for prompt enrichment. Best-effort.

    Uses the ``bird`` CLI (cookie-based auth) to fetch tweets, with Redis
    caching (12 h TTL) to avoid repeated calls for the same contact.

    Returns ``(section_str, tweets)``. ``section_str`` is empty when the
    contact has no handle or nothing was fetched; ``tweets`` is the raw list
    (with ``createdAt`` timestamps) used downstream for freshness checks.
    """
    if not contact.twitter_handle:
        return "", []

    tweets: list[dict[str, Any]] = []
    lines: list[str] = []
    if contact.twitter_bio:
        lines.append(f"Bio: {contact.twitter_bio}")

    try:
        tweets = await _get_cached_tweets(contact, user=user)
        if tweets:
            lines.append("Recent tweets:")
            for t in tweets:
                text = t.get("text", "")[:200]
                # bird uses "createdAt" (e.g. "Sat Mar 07 11:44:26 +0000 2026")
                date = t.get("createdAt", "")[:16]
                lines.append(f"  - {text} ({date})")
    except Exception:
        logger.exception("_fetch_twitter_context: failed for @%s", contact.twitter_handle)

    if not lines:
        return "", tweets
    return "RECENT TWITTER ACTIVITY:\n" + "\n".join(lines), tweets


_TWITTER_FRESH_DAYS = 30
_CONVO_STALE_DAYS = 90
_BIRD_DATE_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def _should_anchor_on_twitter(
    tweets: list[dict[str, Any]],
    last_interaction_at: datetime | None,
) -> bool:
    """True when fresh Twitter activity exists AND conversation is stale.

    Prevents the LLM from reopening a years-old thread when there is a
    more timely signal to lead with.
    """
    if not tweets or not last_interaction_at:
        return False

    now = datetime.now(UTC)
    last_ix = last_interaction_at
    if last_ix.tzinfo is None:
        last_ix = last_ix.replace(tzinfo=UTC)
    if (now - last_ix).days <= _CONVO_STALE_DAYS:
        return False

    for t in tweets:
        date_str = t.get("createdAt", "")
        if not date_str:
            continue
        try:
            tweet_dt = datetime.strptime(date_str, _BIRD_DATE_FORMAT)
        except (ValueError, TypeError):
            continue
        if (now - tweet_dt).days <= _TWITTER_FRESH_DAYS:
            return True
    return False


async def _get_cached_tweets(contact: Contact, user: Any = None) -> list[dict[str, Any]]:
    """Return recent tweets, preferring a Redis cache hit.

    On cache miss, fetches via the ``bird`` CLI and caches for 12 hours.
    """
    from app.core.redis import get_redis

    handle = contact.twitter_handle
    cache_key = f"twitter_tweets:{handle}"

    # --- Check cache ---
    redis = get_redis()
    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.debug("_get_cached_tweets: Redis read failed for %s", cache_key)

    # --- Fetch fresh tweets via bird CLI ---
    from app.integrations.bird import fetch_user_tweets_bird
    from app.services.bird_session import get_cookies

    if user is None:
        logger.warning(
            "_get_cached_tweets: no user passed for @%s — bird CLI skipped, "
            "Twitter context will be empty. This is a caller bug.",
            handle,
        )
        tweets = []
    else:
        cookies = get_cookies(user)
        if cookies is None:
            tweets = []
        else:
            auth_token, ct0 = cookies
            tweets, _err = await fetch_user_tweets_bird(
                handle, auth_token=auth_token, ct0=ct0,
            )
            # composer is best-effort — _err is logged inside _run_bird already

    # --- Cache result (even if empty, to avoid hammering) ---
    if tweets:
        try:
            await redis.set(cache_key, json.dumps(tweets), ex=_TWEET_CACHE_TTL)
        except Exception:
            logger.debug("_get_cached_tweets: Redis write failed for %s", cache_key)

    return tweets


_DASH_RE = re.compile(r"\s*[—–]\s*")
_DOUBLE_COMMA_RE = re.compile(r",\s*,")


def _strip_dashes(text: str) -> str:
    """Replace em/en dashes with commas. LLMs overuse them and users dislike the style."""
    return _DOUBLE_COMMA_RE.sub(",", _DASH_RE.sub(", ", text))


def analyze_conversation_tone(interactions: list[Interaction]) -> str:
    """Determine conversation tone (formal/casual) from past interactions.

    Returns 'casual' if the majority of messages use informal language
    indicators, otherwise returns 'formal'.
    """
    if not interactions:
        return "formal"

    casual_indicators = [
        "hey", "hi", "lol", "haha", "!", "btw", "fyi", "thx", "thanks!",
        "cheers", "awesome", "cool", "great!", "yeah", "yep",
    ]

    casual_score = 0
    total_checked = 0

    for interaction in interactions:
        if not interaction.content_preview:
            continue
        text = interaction.content_preview.lower()
        total_checked += 1
        for indicator in casual_indicators:
            if indicator in text:
                casual_score += 1
                break

    if total_checked == 0:
        return "formal"

    return "casual" if (casual_score / total_checked) >= 0.4 else "formal"


async def compose_followup_message(
    contact_id: uuid.UUID,
    trigger_type: str,
    event_summary: str | None,
    db: AsyncSession,
    revival_context: bool = False,
    user: Any = None,
) -> str:
    """Compose a personalised follow-up message using Anthropic Claude.

    Args:
        contact_id: UUID of the contact to message.
        trigger_type: One of 'time_based', 'event_based', 'scheduled'.
        event_summary: Human-readable summary of the detected event (for
            event_based triggers), or None.
        db: Async database session.

    Returns:
        A short, natural draft message (2-3 sentences).
    """
    import anthropic

    # ------------------------------------------------------------------
    # Fetch contact profile
    # ------------------------------------------------------------------
    contact_result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise ValueError(f"Contact {contact_id} not found")

    first_name = contact.given_name or (contact.full_name or "there").split()[0]
    company_info = f" at {contact.company}" if contact.company else ""
    title_info = f" ({contact.title})" if contact.title else ""
    bio_lines = ""
    if getattr(contact, "twitter_bio", None):
        bio_lines += f"\nTwitter bio: {contact.twitter_bio}"
    if getattr(contact, "telegram_bio", None):
        bio_lines += f"\nTelegram bio: {contact.telegram_bio}"
    contact_context = (
        f"Name: {contact.full_name or first_name}{company_info}{title_info}\n"
        f"Relationship score: {contact.relationship_score}/10\n"
        f"Last interaction: {contact.last_interaction_at.date() if contact.last_interaction_at else 'unknown'}"
        f"{bio_lines}"
    )

    # ------------------------------------------------------------------
    # Fetch last 5 interactions for tone analysis
    # ------------------------------------------------------------------
    interactions_result = await db.execute(
        select(Interaction)
        .where(Interaction.contact_id == contact_id)
        .order_by(Interaction.occurred_at.desc())
        .limit(5)
    )
    interactions = list(interactions_result.scalars().all())

    tone = analyze_conversation_tone(interactions)

    last_convo_lines: list[str] = []
    for ix in reversed(interactions):
        if ix.content_preview:
            direction = "You" if ix.direction == "outbound" else first_name
            last_convo_lines.append(f"  {direction}: {ix.content_preview[:120]}")
    last_convo_summary = (
        "\n".join(last_convo_lines) if last_convo_lines else "No recent conversations on record."
    )

    # ------------------------------------------------------------------
    # Build prompt
    # ------------------------------------------------------------------
    if trigger_type == "birthday":
        reason = "This contact's birthday is today or in the next few days. Send a warm, personal birthday message."
        example = "Example: 'Happy birthday! Hope you have a great one. Let's catch up soon.'"
    elif trigger_type == "event_based" and event_summary:
        reason = f"You noticed a recent event about this contact: {event_summary}"
        example = (
            "Example: 'Saw your tweet about the seed round, congrats! How are things feeling now?'"
        )
    elif trigger_type == "time_based":
        reason = "It has been a while since your last interaction (90+ days). Use their recent activity to make the message feel timely and relevant."
        example = (
            "Example: \"Hey Alex, it's been a minute. How's everything going with the new product?\""
        )
    else:
        reason = "A scheduled follow-up is due."
        example = "Example: 'Hey, just checking in. How have things been going?'"

    # Override reason/example for revival (Pool B) contacts
    if revival_context and trigger_type != "birthday":
        last_date = contact.last_interaction_at.date() if contact.last_interaction_at else "a long time ago"
        reason = (
            f"You haven't spoken to this contact since {last_date}. "
            "Write a warm reconnection message that acknowledges the time gap "
            "without being apologetic. Reference shared history or a recent event."
        )
        if trigger_type == "event_based" and event_summary:
            reason += f"\nA recent event provides a natural reason to reconnect: {event_summary}"
        example = (
            'Example: "Hey Alex, it\'s been way too long! I saw your company just '
            'raised a round, congrats. Would love to catch up when you have a moment."'
        )

    # ------------------------------------------------------------------
    # Fetch Twitter context for every trigger — stale conversation
    # excerpts otherwise dominate event_based/birthday/scheduled prompts.
    # ------------------------------------------------------------------
    twitter_context, twitter_tweets = await _fetch_twitter_context(contact, user=user)
    anchor_on_twitter = _should_anchor_on_twitter(twitter_tweets, contact.last_interaction_at)

    preferred_channel = "email"
    if interactions:
        preferred_channel = interactions[0].platform

    twitter_section = f"\n{twitter_context}\n" if twitter_context else ""
    instruction_lines: list[str] = []
    if twitter_context:
        instruction_lines.append(
            "- If the contact has recent Twitter activity, reference it naturally "
            "(e.g., congratulate an achievement, ask about a project they tweeted about)"
        )
    if anchor_on_twitter:
        instruction_lines.append(
            f"- The last conversation is {_CONVO_STALE_DAYS}+ days old but Twitter activity "
            f"is within {_TWITTER_FRESH_DAYS} days. Anchor the message on the fresh Twitter "
            "signal. Do NOT reopen the stale thread or reference the old conversation excerpt."
        )
    twitter_instruction = ("\n" + "\n".join(instruction_lines)) if instruction_lines else ""

    prompt = f"""You are a networking assistant helping a user maintain genuine professional relationships.
Write a short, natural follow-up message for the contact below.

CONTACT:
{contact_context}
{twitter_section}
TONE: {tone} (match this tone in the message)
PREFERRED CHANNEL: {preferred_channel}

REASON FOR FOLLOW-UP:
{reason}

LAST CONVERSATION EXCERPT:
{last_convo_summary}

INSTRUCTIONS:
- Write 2-3 sentences max
- Be warm and genuine, not salesy
- Reference the reason naturally{twitter_instruction}
- Do NOT use placeholders like [Name]. Use the actual first name: {first_name}
- Do NOT use em dashes (—) or en dashes (–). Use commas, periods, or "and" instead.
- Output only the message text, no subject line, no explanation
{example}

Message:"""

    if not settings.ANTHROPIC_API_KEY:
        return f"Hey {first_name}, just wanted to check in. How have things been going?"

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        message = await _call_anthropic_with_retry(
            client,
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        draft = message.content[0].text.strip()
    except (asyncio.TimeoutError, Exception):
        logger.exception(
            "compose_followup_message: API call failed for contact %s",
            contact_id,
        )
        # Fallback to a simple template-based message
        draft = f"Hey {first_name}, just wanted to check in. How have things been going?"

    draft = _strip_dashes(draft)

    logger.info(
        "compose_followup_message: composed message for contact %s (trigger=%s)",
        contact_id,
        trigger_type,
    )
    return draft
