"""Meeting-prep composer: query upcoming meetings, build attendee briefs,
generate AI talking points, and render an HTML prep email."""
from __future__ import annotations

import html as html_mod
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

    # --- Fetch contacts ---
    contacts_result = await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
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


# ---------------------------------------------------------------------------
# Task 6: compose_prep_email
# ---------------------------------------------------------------------------


def compose_prep_email(
    meeting: dict,
    briefs: list[dict],
    talking_points: str,
) -> tuple[str, str]:
    """Render the meeting-prep email as (subject, html_body).

    Parameters
    ----------
    meeting:
        Dict with ``title``, ``occurred_at``, ``contact_ids``.
    briefs:
        List of attendee brief dicts from :func:`build_prep_brief`.
    talking_points:
        AI-generated talking points (may be empty).

    Returns
    -------
    A ``(subject, html_body)`` tuple.
    """
    esc = html_mod.escape
    base_url = getattr(settings, "FRONTEND_URL", "https://pingcrm.sawinyh.com")
    title = esc(meeting.get("title", "Untitled meeting"))
    raw_title = meeting.get("title", "Untitled meeting")
    subject = f"Meeting prep: {raw_title} in 30 minutes"
    subject = subject.replace("\r", "").replace("\n", " ")  # prevent CRLF header injection

    # --- Attendee cards ---
    attendee_cards = ""
    for b in briefs:
        name = esc(b.get("name") or "Unknown")
        job_title = esc(b.get("title") or "")
        company = esc(b.get("company") or "")
        score = b.get("score", 0)
        score_label = esc(b.get("score_label", "Cold"))
        avatar = b.get("avatar_url") or ""

        # Score badge colour
        if score >= 7:
            badge_color = "#16a34a"  # green
        elif score >= 4:
            badge_color = "#d97706"  # amber
        else:
            badge_color = "#6b7280"  # gray

        # Avatar or initials
        if avatar:
            avatar_html = (
                f'<img src="{esc(avatar)}" alt="{name}" '
                f'style="width:48px;height:48px;border-radius:50%;object-fit:cover;" />'
            )
        else:
            initials = "".join(
                word[0].upper() for word in (b.get("name") or "?").split()[:2]
            )
            avatar_html = (
                f'<div style="width:48px;height:48px;border-radius:50%;'
                f'background:#e0e7ff;color:#4f46e5;display:flex;align-items:center;'
                f'justify-content:center;font-weight:bold;font-size:18px;">'
                f'{esc(initials)}</div>'
            )

        # Bio lines
        bio_lines_html = ""
        for bio_key, bio_label in [
            ("twitter_bio", "Twitter"),
            ("linkedin_headline", "LinkedIn"),
            ("linkedin_bio", "LinkedIn about"),
            ("telegram_bio", "Telegram"),
        ]:
            val = b.get(bio_key)
            if val:
                bio_lines_html += (
                    f'<p style="margin:4px 0;font-size:13px;color:#6b7280;">'
                    f'<strong>{esc(bio_label)}:</strong> {esc(val)}</p>'
                )

        # Recent interactions
        recent_html = ""
        for ri in b.get("recent_interactions", [])[:3]:
            preview = esc((ri.get("preview") or "")[:120])
            platform = esc(ri.get("platform", ""))
            date_val = ri.get("date")
            if hasattr(date_val, "strftime"):
                date_str = date_val.strftime("%b %d")
            else:
                date_str = str(date_val)[:10] if date_val else ""
            recent_html += (
                f'<tr>'
                f'<td style="padding:4px 8px;font-size:12px;color:#9ca3af;">{esc(date_str)}</td>'
                f'<td style="padding:4px 8px;font-size:12px;color:#9ca3af;">{platform}</td>'
                f'<td style="padding:4px 8px;font-size:13px;color:#374151;">{preview}</td>'
                f'</tr>'
            )

        recent_table = ""
        if recent_html:
            recent_table = (
                f'<table style="width:100%;border-collapse:collapse;margin-top:8px;">'
                f'<tr style="border-bottom:1px solid #e5e7eb;">'
                f'<th style="text-align:left;padding:4px 8px;font-size:11px;color:#9ca3af;font-weight:600;">Date</th>'
                f'<th style="text-align:left;padding:4px 8px;font-size:11px;color:#9ca3af;font-weight:600;">Channel</th>'
                f'<th style="text-align:left;padding:4px 8px;font-size:11px;color:#9ca3af;font-weight:600;">Preview</th>'
                f'</tr>'
                f'{recent_html}'
                f'</table>'
            )

        # Subtitle line
        subtitle_parts = [p for p in [job_title, company] if p]
        subtitle = " at ".join(subtitle_parts) if subtitle_parts else ""

        attendee_cards += f"""
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
          <table style="width:100%;border-collapse:collapse;"><tr>
            <td style="width:56px;vertical-align:top;">{avatar_html}</td>
            <td style="padding-left:12px;vertical-align:top;">
              <p style="margin:0;font-size:16px;font-weight:600;color:#111827;">{name}</p>
              {'<p style="margin:2px 0 0;font-size:13px;color:#6b7280;">' + esc(subtitle) + '</p>' if subtitle else ''}
              <span style="display:inline-block;margin-top:4px;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600;color:#ffffff;background:{badge_color};">{score_label} ({score}/10)</span>
            </td>
          </tr></table>
          {bio_lines_html}
          {recent_table}
        </div>
        """

    # --- Talking points section ---
    talking_points_section = ""
    if talking_points:
        talking_points_section = f"""
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin-bottom:20px;">
          <h2 style="margin:0 0 8px;font-size:16px;color:#166534;">Suggested Talking Points</h2>
          <div style="font-size:14px;color:#374151;white-space:pre-wrap;">{esc(talking_points)}</div>
        </div>
        """

    # --- Full HTML ---
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8" /></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table style="width:100%;background:#f3f4f6;padding:20px 0;" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table style="width:600px;max-width:100%;background:#ffffff;border-radius:12px;overflow:hidden;" cellpadding="0" cellspacing="0">
        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#0d9488,#14b8a6);padding:24px 32px;">
            <h1 style="margin:0;font-size:20px;color:#ffffff;">Meeting Prep</h1>
            <p style="margin:4px 0 0;font-size:14px;color:#ccfbf1;">{title}</p>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:24px 32px;">
            <h2 style="margin:0 0 16px;font-size:16px;color:#374151;">Attendees</h2>
            {attendee_cards}
            {talking_points_section}
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="padding:16px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;text-align:center;">
            <p style="margin:0;font-size:12px;color:#9ca3af;">
              Sent by <a href="{esc(base_url)}" style="color:#0d9488;text-decoration:none;">PingCRM</a>
              &middot;
              <a href="{esc(base_url)}/settings" style="color:#0d9488;text-decoration:none;">Manage preferences</a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return subject, html_body
