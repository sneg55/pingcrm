"""Weekly digest email service.

For MVP the email is logged rather than sent via SMTP (Phase 3).
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.services.followup_engine import get_weekly_digest

logger = logging.getLogger(__name__)

_BASE_URL = "https://app.pingcrm.io"


def _format_date(dt: datetime | None) -> str:
    if dt is None:
        return "Unknown"
    return dt.strftime("%b %d, %Y")


def _build_html(user_email: str, items: list[dict]) -> str:
    """Build the HTML body of the digest email."""

    rows_html = ""
    for item in items:
        contact_name = item["contact_name"]
        reason = item["reason"]
        last_interaction = item["last_interaction"]
        message_preview = item["message_preview"]
        suggestion_id = item["suggestion_id"]
        open_link = f"{_BASE_URL}/suggestions/{suggestion_id}"

        rows_html += f"""
        <tr>
          <td style="padding: 20px 0; border-bottom: 1px solid #e5e7eb;">
            <p style="margin: 0 0 4px 0; font-size: 16px; font-weight: 600; color: #111827;">
              {contact_name}
            </p>
            <p style="margin: 0 0 4px 0; font-size: 13px; color: #6b7280;">
              {reason} &middot; Last contact: {last_interaction}
            </p>
            <p style="margin: 8px 0; font-size: 14px; color: #374151;
                       background: #f9fafb; border-left: 3px solid #6366f1;
                       padding: 8px 12px; border-radius: 0 4px 4px 0;">
              &ldquo;{message_preview}&rdquo;
            </p>
            <a href="{open_link}"
               style="display: inline-block; margin-top: 8px; padding: 8px 16px;
                       background: #6366f1; color: #ffffff; text-decoration: none;
                       border-radius: 6px; font-size: 13px; font-weight: 500;">
              Open in Ping
            </a>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ping: Your weekly networking digest</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0"
               style="background-color: #ffffff; border-radius: 12px;
                      box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden;">

          <!-- Header -->
          <tr>
            <td style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                        padding: 32px 40px; text-align: center;">
              <p style="margin: 0 0 8px 0; font-size: 28px; font-weight: 700; color: #ffffff;">
                Ping
              </p>
              <p style="margin: 0; font-size: 16px; color: #e0e7ff;">
                Your weekly networking digest
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding: 32px 40px;">
              <p style="margin: 0 0 24px 0; font-size: 15px; color: #374151;">
                Hi there! Here are the people you should reach out to this week.
              </p>
              <table width="100%" cellpadding="0" cellspacing="0">
                {rows_html}
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 24px 40px; background: #f9fafb; text-align: center;
                        border-top: 1px solid #e5e7eb;">
              <p style="margin: 0; font-size: 12px; color: #9ca3af;">
                You're receiving this because you use Ping CRM.
                <a href="{_BASE_URL}/settings/notifications"
                   style="color: #6366f1; text-decoration: none;">Manage preferences</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


async def send_weekly_digest(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Generate and log the weekly digest email for a user.

    Fetches up to 5 pending suggestions, builds an HTML email and logs it.
    Actual SMTP delivery is deferred to Phase 3.

    Args:
        user_id: UUID of the user whose digest to send.
        db: Async database session.

    Returns:
        A dict with 'subject', 'to', 'suggestion_count', and 'html' keys.
    """
    from app.models.user import User

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    user_email = user.email if user and hasattr(user, "email") else "user@example.com"

    suggestions = await get_weekly_digest(user_id, db)
    suggestions = suggestions[:5]  # cap at 5

    items: list[dict] = []
    for suggestion in suggestions:
        contact_result = await db.execute(
            select(Contact).where(Contact.id == suggestion.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        contact_name = (
            contact.full_name or contact.given_name or "Unknown"
        ) if contact else "Unknown"
        last_interaction = _format_date(
            contact.last_interaction_at if contact else None
        )

        trigger_labels = {
            "time_based": "It's been a while",
            "event_based": "Recent news",
            "scheduled": "Scheduled follow-up",
        }
        reason = trigger_labels.get(suggestion.trigger_type, suggestion.trigger_type)

        # Truncate preview to ~120 characters
        preview = suggestion.suggested_message
        if len(preview) > 120:
            preview = preview[:117] + "..."

        items.append(
            {
                "contact_name": contact_name,
                "reason": reason,
                "last_interaction": last_interaction,
                "message_preview": preview,
                "suggestion_id": str(suggestion.id),
            }
        )

    subject = "Ping: Your weekly networking digest"
    html = _build_html(user_email, items)

    # MVP: log instead of sending via SMTP
    logger.info(
        "send_weekly_digest: would send email to %s | subject=%r | contacts=%d\n---\n%s\n---",
        user_email,
        subject,
        len(items),
        html[:500] + ("..." if len(html) > 500 else ""),
    )

    return {
        "subject": subject,
        "to": user_email,
        "suggestion_count": len(items),
        "html": html,
        "sent_at": datetime.now(UTC).isoformat(),
    }
