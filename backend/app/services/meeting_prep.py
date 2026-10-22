"""Meeting-prep composer: query upcoming meetings, build attendee briefs,
generate AI talking points, and render an HTML prep email."""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.services.meeting_prep_email import compose_prep_email
from app.services.message_composer import _call_anthropic_with_retry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task 3: get_upcoming_meetings
# ---------------------------------------------------------------------------


async def get_upcoming_meetings(
    user_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
    db: AsyncSession,
) -> list[dict]:
    """Return meetings (grouped by Google Calendar event ID) in the given window.

    Each meeting Interaction has ``platform='meeting'`` and
    ``raw_reference_id='gcal:{event_id}:{contact_id}'``.  Multiple rows for
    the same event (one per attendee) are collapsed into a single dict.

    Returns a list of dicts::

        {event_id, title, occurred_at, contact_ids}
    """
    stmt = (
        select(Interaction)
        .where(
            Interaction.user_id == user_id,
            Interaction.platform == "meeting",
            Interaction.occurred_at >= window_start,
            Interaction.occurred_at < window_end,
        )
        .order_by(Interaction.occurred_at.asc())
    )
    result = await db.execute(stmt)
    interactions = result.scalars().all()

    grouped: dict[str, dict] = {}
    for ix in interactions:
        if not ix.raw_reference_id:
            continue
        parts = ix.raw_reference_id.split(":")
        if len(parts) < 3 or parts[0] != "gcal":
            continue

        event_id = parts[1]
        contact_id = parts[2]

        if event_id not in grouped:
            grouped[event_id] = {
                "event_id": event_id,
                "title": ix.content_preview or "Untitled meeting",
                "occurred_at": ix.occurred_at,
                "contact_ids": [],
            }

        try:
            cid = uuid.UUID(contact_id)
        except ValueError:
            logger.warning(
                "get_upcoming_meetings: skipping malformed contact id in reference",
                extra={"raw_reference_id": ix.raw_reference_id},
            )
            continue
        if cid not in grouped[event_id]["contact_ids"]:
            grouped[event_id]["contact_ids"].append(cid)

    return list(grouped.values())


# ---------------------------------------------------------------------------
# Task 4: build_prep_brief
# ---------------------------------------------------------------------------


async def build_prep_brief(
    contact_ids: list[uuid.UUID],
    db: AsyncSession,
) -> list[dict]:
    """Build an attendee brief for each contact ID.

    Returns a list of dicts with contact metadata, score label, and the last 5
    non-meeting interactions.
    """
    if not contact_ids:
        return []

    # --- Fetch contacts (exclude archived) ---
    contacts_result = await db.execute(
        select(Contact).where(
            Contact.id.in_(contact_ids),
            Contact.priority_level != "archived",
        )
    )
    contacts = {c.id: c for c in contacts_result.scalars().all()}
    if not contacts:
        return []

    # --- Fetch recent non-meeting interactions (up to 5 per contact) ---
    max_rows = len(contact_ids) * 20  # over-fetch to avoid starving low-activity contacts
    interactions_result = await db.execute(
        select(Interaction)
        .where(
            Interaction.contact_id.in_(contact_ids),
            Interaction.platform != "meeting",
        )
        .order_by(Interaction.occurred_at.desc())
        .limit(max_rows)
    )
    all_interactions = interactions_result.scalars().all()

    # Group by contact, keeping at most 5 each
    ix_by_contact: dict[uuid.UUID, list[Interaction]] = defaultdict(list)
    for ix in all_interactions:
        if len(ix_by_contact[ix.contact_id]) < 5:
            ix_by_contact[ix.contact_id].append(ix)

    # --- Build briefs ---
    briefs: list[dict] = []
    for cid in contact_ids:
        contact = contacts.get(cid)
        if contact is None:
            continue

        score = contact.relationship_score
        if score >= 7:
            score_label = "Strong"
        elif score >= 4:
            score_label = "Warm"
        else:
            score_label = "Cold"

        recent = []
        for ix in ix_by_contact.get(cid, []):
            recent.append({
                "date": ix.occurred_at,
                "preview": ix.content_preview,
                "platform": ix.platform,
            })

        briefs.append({
            "contact_id": cid,
            "name": contact.full_name,
            "title": contact.title,
            "company": contact.company,
            "score": score,
            "score_label": score_label,
            "interaction_count": contact.interaction_count,
            "last_interaction_at": contact.last_interaction_at,
            "avatar_url": contact.avatar_url,
            "twitter_bio": contact.twitter_bio,
            "linkedin_headline": contact.linkedin_headline,
            "linkedin_bio": contact.linkedin_bio,
            "telegram_bio": contact.telegram_bio,
            "recent_interactions": recent,
        })

    return briefs


# ---------------------------------------------------------------------------
# Task 5: generate_talking_points
# ---------------------------------------------------------------------------


async def generate_talking_points(briefs: list[dict], meeting_title: str) -> str:
    """Use Claude Haiku to generate concise talking points for a meeting.

    Returns the AI-generated text, or an empty string on failure / missing key.
    """
    if not settings.ANTHROPIC_API_KEY:
        return ""

    # Build prompt from attendee briefs
    attendee_sections: list[str] = []
    for b in briefs:
        lines = [f"- {b.get('name', 'Unknown')}"]
        if b.get("title"):
            lines.append(f"  Title: {b['title']}")
        if b.get("company"):
            lines.append(f"  Company: {b['company']}")
        lines.append(f"  Relationship: {b.get('score_label', 'Unknown')}")

        # Bios
        for bio_key, bio_label in [
            ("twitter_bio", "Twitter bio"),
            ("linkedin_headline", "LinkedIn headline"),
            ("linkedin_bio", "LinkedIn bio"),
            ("telegram_bio", "Telegram bio"),
        ]:
            if b.get(bio_key):
                lines.append(f"  {bio_label}: {b[bio_key]}")

        # Recent interactions
        recent = b.get("recent_interactions", [])
        if recent:
            lines.append("  Recent interactions:")
            for ri in recent[:3]:
                preview = (ri.get("preview") or "")[:100]
                lines.append(f"    - [{ri.get('platform', '?')}] {preview}")

        attendee_sections.append("\n".join(lines))

    prompt = f"""You are a networking assistant. Generate 3-5 concise talking points for an upcoming meeting.

MEETING: {meeting_title}

ATTENDEES:
{chr(10).join(attendee_sections)}

INSTRUCTIONS:
- Write 3-5 bullet points that would help the user prepare
- Reference specific details from attendee bios and recent interactions
- Keep each point to 1-2 sentences
- Be practical and actionable
- Output only the bullet points, no preamble

Talking points:"""

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        message = await _call_anthropic_with_retry(
            client,
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        logger.exception(
            "generate_talking_points: API call failed",
            extra={"provider": "anthropic", "meeting_title": meeting_title},
        )
        return ""


__all__ = [
    "build_prep_brief",
    "compose_prep_email",
    "generate_talking_points",
    "get_upcoming_meetings",
]
