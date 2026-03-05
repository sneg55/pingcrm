"""LLM-based event classifier using Anthropic Claude."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.detected_event import DetectedEvent

logger = logging.getLogger(__name__)

_VALID_EVENT_TYPES = frozenset({
    "job_change",
    "fundraising",
    "product_launch",
    "promotion",
    "milestone",
    "event_attendance",
    "none",
})

_CONFIDENCE_THRESHOLD = 0.7

_SYSTEM_PROMPT = (
    "You are a professional relationship intelligence assistant. "
    "Your job is to classify signals from contact activity into structured events."
)


def _get_anthropic_client():
    """Return an Anthropic client.  Imported lazily to avoid import-time side-effects."""
    import anthropic  # noqa: PLC0415
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _parse_classifier_response(raw: str) -> dict[str, Any]:
    """Parse the JSON blob returned by the LLM.

    Handles both bare JSON and JSON wrapped in a markdown code fence.
    """
    text = raw.strip()
    # Strip optional markdown code fences.
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence (```json or ```)
        lines = lines[1:] if lines else lines
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("_parse_classifier_response: could not parse JSON from LLM output: %r", raw)
        return {"event_type": "none", "confidence": 0.0, "summary": ""}

    event_type = str(data.get("event_type", "none")).strip().lower()
    if event_type not in _VALID_EVENT_TYPES:
        event_type = "none"

    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    summary = str(data.get("summary", "")).strip()

    return {"event_type": event_type, "confidence": confidence, "summary": summary}


# ---------------------------------------------------------------------------
# Public classifier functions
# ---------------------------------------------------------------------------


def classify_tweet(tweet_text: str, contact_name: str) -> dict[str, Any]:
    """Classify a single tweet using Anthropic Claude.

    Args:
        tweet_text: The raw tweet content.
        contact_name: Name of the contact who wrote the tweet.

    Returns:
        A dict with keys ``event_type`` (str), ``confidence`` (float),
        ``summary`` (str).
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("classify_tweet: ANTHROPIC_API_KEY not configured; returning 'none'.")
        return {"event_type": "none", "confidence": 0.0, "summary": ""}

    prompt = (
        f"Contact name: {contact_name}\n"
        f"Tweet text: {tweet_text}\n\n"
        "Classify this tweet into one of the following event types:\n"
        "  job_change, fundraising, product_launch, promotion, milestone, "
        "event_attendance, none\n\n"
        "Return ONLY a JSON object with these fields:\n"
        '  { "event_type": "<type>", "confidence": <0.0-1.0>, "summary": "<one-sentence summary>" }\n'
        "Do not include any other text."
    )

    try:
        client = _get_anthropic_client()
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text if message.content else ""
        return _parse_classifier_response(raw)
    except Exception:
        logger.exception("classify_tweet: Anthropic API call failed.")
        return {"event_type": "none", "confidence": 0.0, "summary": ""}


def classify_bio_change(
    old_bio: str,
    new_bio: str,
    contact_name: str,
) -> dict[str, Any]:
    """Detect meaningful changes between two bio versions using Anthropic Claude.

    Args:
        old_bio: Previous bio text.
        new_bio: Current bio text.
        contact_name: Name of the contact.

    Returns:
        A dict with keys ``event_type`` (str), ``confidence`` (float),
        ``summary`` (str).
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("classify_bio_change: ANTHROPIC_API_KEY not configured; returning 'none'.")
        return {"event_type": "none", "confidence": 0.0, "summary": ""}

    if not old_bio and not new_bio:
        return {"event_type": "none", "confidence": 0.0, "summary": ""}

    prompt = (
        f"Contact name: {contact_name}\n"
        f"Previous bio: {old_bio or '(empty)'}\n"
        f"New bio: {new_bio or '(empty)'}\n\n"
        "Analyse the change in this person's Twitter bio. "
        "Classify the most significant signal into one of these event types:\n"
        "  job_change, fundraising, product_launch, promotion, milestone, "
        "event_attendance, none\n\n"
        "Return ONLY a JSON object with these fields:\n"
        '  { "event_type": "<type>", "confidence": <0.0-1.0>, "summary": "<one-sentence summary>" }\n'
        "Do not include any other text."
    )

    try:
        client = _get_anthropic_client()
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text if message.content else ""
        return _parse_classifier_response(raw)
    except Exception:
        logger.exception("classify_bio_change: Anthropic API call failed.")
        return {"event_type": "none", "confidence": 0.0, "summary": ""}


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


async def process_contact_activity(
    contact_id: uuid.UUID,
    tweets: list[dict[str, Any]],
    bio_change: dict[str, Any] | None,
    db: AsyncSession,
) -> list[DetectedEvent]:
    """Run classifiers over tweets and bio change, persist high-confidence events.

    Args:
        contact_id: UUID of the contact.
        tweets: List of tweet dicts with at least ``text`` key.
        bio_change: Dict with ``old_bio``, ``new_bio``, ``contact_name`` keys,
                    or None when there is no bio change.
        db: Active async database session.

    Returns:
        List of DetectedEvent records that were created (confidence >= 0.7).
    """
    created_events: list[DetectedEvent] = []
    contact_name = (bio_change or {}).get("contact_name", "Unknown")

    # Classify individual tweets.
    for tweet in tweets:
        text = tweet.get("text", "").strip()
        if not text:
            continue

        classification = classify_tweet(text, contact_name)

        if (
            classification["event_type"] != "none"
            and classification["confidence"] >= _CONFIDENCE_THRESHOLD
        ):
            # Build a source URL if tweet id is available (best-effort).
            tweet_id = tweet.get("id")
            source_url = (
                f"https://twitter.com/i/web/status/{tweet_id}" if tweet_id else None
            )

            event = DetectedEvent(
                contact_id=contact_id,
                event_type=classification["event_type"],
                confidence=classification["confidence"],
                summary=classification["summary"],
                source_url=source_url,
                detected_at=datetime.now(UTC),
            )
            db.add(event)
            await db.flush()
            await db.refresh(event)
            created_events.append(event)

    # Classify bio change.
    if bio_change and bio_change.get("new_bio"):
        old_bio = bio_change.get("old_bio", "")
        new_bio = bio_change.get("new_bio", "")
        classification = classify_bio_change(old_bio, new_bio, contact_name)

        if (
            classification["event_type"] != "none"
            and classification["confidence"] >= _CONFIDENCE_THRESHOLD
        ):
            event = DetectedEvent(
                contact_id=contact_id,
                event_type=classification["event_type"],
                confidence=classification["confidence"],
                summary=classification["summary"],
                source_url=None,
                detected_at=datetime.now(UTC),
            )
            db.add(event)
            await db.flush()
            await db.refresh(event)
            created_events.append(event)

    return created_events
