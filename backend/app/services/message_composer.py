"""AI Message Composer using Anthropic Claude API."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.interaction import Interaction

logger = logging.getLogger(__name__)


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
    contact_context = (
        f"Name: {contact.full_name or first_name}{company_info}{title_info}\n"
        f"Relationship score: {contact.relationship_score}/10\n"
        f"Last interaction: {contact.last_interaction_at.date() if contact.last_interaction_at else 'unknown'}"
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
    if trigger_type == "event_based" and event_summary:
        reason = f"You noticed a recent event about this contact: {event_summary}"
        example = (
            "Example: 'Saw your tweet about the seed round, congrats! How are things feeling now?'"
        )
    elif trigger_type == "time_based":
        reason = "It has been a while since your last interaction (90+ days)."
        example = (
            "Example: \"Hey Alex, it's been a minute. How's everything going with the new product?\""
        )
    else:
        reason = "A scheduled follow-up is due."
        example = "Example: 'Hey, just checking in — how have things been going?'"

    preferred_channel = "email"
    if interactions:
        preferred_channel = interactions[0].platform

    prompt = f"""You are a networking assistant helping a user maintain genuine professional relationships.
Write a short, natural follow-up message for the contact below.

CONTACT:
{contact_context}

TONE: {tone} (match this tone in the message)
PREFERRED CHANNEL: {preferred_channel}

REASON FOR FOLLOW-UP:
{reason}

LAST CONVERSATION EXCERPT:
{last_convo_summary}

INSTRUCTIONS:
- Write 2-3 sentences max
- Be warm and genuine, not salesy
- Reference the reason naturally
- Do NOT use placeholders like [Name] — use the actual first name: {first_name}
- Output only the message text, no subject line, no explanation
{example}

Message:"""

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    draft = message.content[0].text.strip()
    logger.info(
        "compose_followup_message: composed message for contact %s (trigger=%s)",
        contact_id,
        trigger_type,
    )
    return draft
