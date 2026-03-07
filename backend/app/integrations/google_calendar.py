"""Google Calendar integration — sync events and extract participants as contacts."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

logger = logging.getLogger(__name__)

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
MAX_RESULTS = 250
# How far back to sync on first run (3 years)
DEFAULT_LOOKBACK_DAYS = 365 * 3


def _build_calendar_service(refresh_token: str) -> Any:
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=CALENDAR_SCOPES,
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _parse_event_time(event: dict, key: str) -> datetime | None:
    """Extract a datetime from an event's start/end dict."""
    time_info = event.get(key, {})
    dt_str = time_info.get("dateTime")
    if dt_str:
        return datetime.fromisoformat(dt_str)
    # All-day events use 'date' instead
    date_str = time_info.get("date")
    if date_str:
        return datetime.fromisoformat(date_str).replace(tzinfo=UTC)
    return None


def _extract_attendee_emails(event: dict, user_email: str) -> list[str]:
    """Return attendee email addresses excluding the authenticated user and resources."""
    attendees = event.get("attendees", [])
    emails: list[str] = []
    for att in attendees:
        email = (att.get("email") or "").strip().lower()
        if not email or email == user_email.lower():
            continue
        # Skip resource calendars (rooms, etc.)
        if att.get("resource", False):
            continue
        emails.append(email)
    return emails


async def _find_or_create_contact(
    email_addr: str,
    display_name: str | None,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Contact:
    """Find an existing contact by email or create a new one."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.emails.contains([email_addr]),
        )
    )
    contact = result.scalar_one_or_none()
    if contact:
        return contact

    # Parse display name into given/family
    given_name = None
    family_name = None
    if display_name:
        parts = display_name.strip().split(None, 1)
        given_name = parts[0] if parts else None
        family_name = parts[1] if len(parts) > 1 else None

    contact = Contact(
        user_id=user_id,
        full_name=display_name,
        given_name=given_name,
        family_name=family_name,
        emails=[email_addr],
        source="google_calendar",
    )
    db.add(contact)
    await db.flush()
    return contact


async def sync_calendar_events(user: User, db: AsyncSession) -> dict[str, int]:
    """Sync Google Calendar events for a user.

    - Creates contacts for event participants not already in the DB.
    - Creates 'meeting' interactions for each contact-event pair.

    Returns dict with keys: new_contacts, new_interactions, events_processed.
    """
    if not user.google_refresh_token:
        return {"new_contacts": 0, "new_interactions": 0, "events_processed": 0}

    service = _build_calendar_service(user.google_refresh_token)
    user_email = user.email.lower()

    time_min = (datetime.now(UTC) - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()
    time_max = (datetime.now(UTC) + timedelta(days=30)).isoformat()

    events_processed = 0
    new_contacts = 0
    new_interactions = 0

    page_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "calendarId": "primary",
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": MAX_RESULTS,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.events().list(**kwargs).execute()
        items = response.get("items", [])

        for event in items:
            event_id = event.get("id", "")
            summary = event.get("summary", "(no title)")
            status = event.get("status", "confirmed")

            if status == "cancelled":
                continue

            start_dt = _parse_event_time(event, "start")
            if not start_dt:
                continue

            attendee_emails = _extract_attendee_emails(event, user_email)
            if not attendee_emails:
                continue

            events_processed += 1

            # Build name lookup from attendees
            attendee_names: dict[str, str] = {}
            for att in event.get("attendees", []):
                att_email = (att.get("email") or "").strip().lower()
                att_name = att.get("displayName")
                if att_email and att_name:
                    attendee_names[att_email] = att_name

            for att_email in attendee_emails:
                # Check if contact already exists
                existing_result = await db.execute(
                    select(Contact).where(
                        Contact.user_id == user.id,
                        Contact.emails.contains([att_email]),
                    )
                )
                existing = existing_result.scalar_one_or_none()

                if existing:
                    contact = existing
                    # Backfill name from calendar if contact has no name yet
                    cal_name = attendee_names.get(att_email)
                    if cal_name and not contact.full_name:
                        parts = cal_name.strip().split(None, 1)
                        contact.full_name = cal_name
                        contact.given_name = parts[0] if parts else None
                        contact.family_name = parts[1] if len(parts) > 1 else None
                else:
                    contact = await _find_or_create_contact(
                        att_email,
                        attendee_names.get(att_email),
                        user.id,
                        db,
                    )
                    new_contacts += 1

                # Upsert interaction (idempotent on raw_reference_id)
                ref_id = f"gcal:{event_id}:{contact.id}"
                int_result = await db.execute(
                    select(Interaction).where(
                        Interaction.raw_reference_id == ref_id,
                        Interaction.user_id == user.id,
                    )
                )
                if int_result.scalar_one_or_none():
                    continue

                interaction = Interaction(
                    contact_id=contact.id,
                    user_id=user.id,
                    platform="meeting",
                    direction="mutual",
                    content_preview=summary[:500],
                    raw_reference_id=ref_id,
                    occurred_at=start_dt,
                )
                db.add(interaction)
                new_interactions += 1

                # Update last_interaction_at
                if contact.last_interaction_at is None or contact.last_interaction_at < start_dt:
                    contact.last_interaction_at = start_dt

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    await db.flush()
    logger.info(
        "Calendar sync for user %s: %d events, %d new contacts, %d new interactions.",
        user.id, events_processed, new_contacts, new_interactions,
    )
    return {
        "new_contacts": new_contacts,
        "new_interactions": new_interactions,
        "events_processed": events_processed,
    }
