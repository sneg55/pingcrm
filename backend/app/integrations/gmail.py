"""Gmail API integration for syncing email threads as Interactions."""
from __future__ import annotations

import email.utils
import logging
import uuid
from datetime import UTC, datetime
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

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
MAX_RESULTS = 500  # threads per page
GMAIL_LOOKBACK_QUERY = "newer_than:1y"  # sync last year of email


def _build_gmail_service(refresh_token: str) -> Any:
    """Build authenticated Gmail API service from a user's refresh token."""
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    return service


def _extract_header(headers: list[dict], name: str) -> str:
    """Extract a header value by name (case-insensitive)."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_email_addresses(header_value: str) -> list[str]:
    """Parse a comma-separated list of RFC 2822 email addresses, returning only addresses."""
    if not header_value:
        return []
    addresses = []
    for _name, addr in email.utils.getaddresses([header_value]):
        addr = addr.strip().lower()
        if addr:
            addresses.append(addr)
    return addresses


def _thread_to_metadata(thread_data: dict) -> dict | None:
    """
    Extract metadata from a Gmail thread dict returned by the API.

    Returns a dict with keys:
        thread_id, subject, participants, snippet, occurred_at,
        from_addresses, to_addresses, cc_addresses
    or None if the thread cannot be parsed.
    """
    messages = thread_data.get("messages", [])
    if not messages:
        return None

    # First message for subject, last message for direction/recency
    first_msg = messages[0]
    last_msg = messages[-1]

    first_headers = first_msg.get("payload", {}).get("headers", [])
    subject = _extract_header(first_headers, "subject") or "(no subject)"

    # Use last message headers for direction (reflects most recent activity)
    last_headers = last_msg.get("payload", {}).get("headers", [])
    from_header = _extract_header(last_headers, "from")
    to_header = _extract_header(last_headers, "to")
    cc_header = _extract_header(last_headers, "cc")

    from_addresses = _parse_email_addresses(from_header)
    to_addresses = _parse_email_addresses(to_header)
    cc_addresses = _parse_email_addresses(cc_header)

    # Collect all participants across all messages for contact matching
    all_participants: set[str] = set()
    for msg in messages:
        msg_headers = msg.get("payload", {}).get("headers", [])
        for hdr in ("from", "to", "cc"):
            all_participants.update(_parse_email_addresses(_extract_header(msg_headers, hdr)))
    participants = list(all_participants)

    # internalDate is Unix epoch in milliseconds
    internal_date_ms = int(last_msg.get("internalDate", 0))
    occurred_at = datetime.fromtimestamp(internal_date_ms / 1000, tz=UTC)

    # With format="metadata", individual messages may lack a snippet.
    # Fall back to the thread-level snippet which is always present.
    snippet = last_msg.get("snippet", "") or thread_data.get("snippet", "")

    # For multi-message threads, also capture the first message snippet
    # so we can show what the contact originally wrote (not just our reply).
    first_snippet = ""
    if len(messages) > 1:
        first_snippet = first_msg.get("snippet", "") or ""

    return {
        "thread_id": thread_data.get("id", ""),
        "subject": subject,
        "participants": participants,
        "snippet": snippet,
        "first_snippet": first_snippet,
        "occurred_at": occurred_at,
        "from_addresses": from_addresses,
        "to_addresses": to_addresses,
        "cc_addresses": cc_addresses,
    }


async def _find_contact_by_email(
    email_addr: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Look up a Contact belonging to *user_id* whose emails list contains *email_addr*."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.emails.contains([email_addr]),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _upsert_interaction(
    *,
    contact: Contact,
    user_id: uuid.UUID,
    thread_id: str,
    direction: str,
    snippet: str,
    occurred_at: datetime,
    db: AsyncSession,
) -> Interaction:
    """
    Create an Interaction for *thread_id* if one doesn't exist yet,
    or return the existing one (idempotent on raw_reference_id).
    """
    result = await db.execute(
        select(Interaction).where(
            Interaction.raw_reference_id == thread_id,
            Interaction.contact_id == contact.id,
            Interaction.user_id == user_id,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Always update direction if it changed (e.g. thread now has both
        # inbound and outbound messages → mutual)
        if existing.direction != direction and direction == "mutual":
            existing.direction = "mutual"

        # Update timestamp and snippet if thread has newer messages
        if occurred_at > existing.occurred_at:
            existing.occurred_at = occurred_at
            if snippet:
                existing.content_preview = snippet[:500]
        elif snippet and (not existing.content_preview or existing.direction == "mutual"):
            # Backfill snippet for mutual threads (show contact's message, not user's reply)
            existing.content_preview = snippet[:500]
        return existing

    interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user_id,
        platform="email",
        direction=direction,
        content_preview=snippet[:500] if snippet else None,
        raw_reference_id=thread_id,
        occurred_at=occurred_at,
    )
    db.add(interaction)
    return interaction


async def sync_gmail_for_user(user: User, db: AsyncSession) -> int:
    """
    Sync Gmail threads for *user* and persist them as Interaction records.

    Returns the number of new interactions created.
    """
    if not user.google_refresh_token:
        logger.warning("User %s has no google_refresh_token; skipping Gmail sync.", user.id)
        return 0

    try:
        service = _build_gmail_service(user.google_refresh_token)
    except Exception:
        logger.exception("Failed to build Gmail service for user %s.", user.id)
        return 0

    user_email = user.email.lower()

    # Fetch all thread IDs from last year, paginating through results
    thread_items: list[dict] = []
    page_token: str | None = None
    try:
        while True:
            kwargs: dict[str, Any] = {
                "userId": "me",
                "maxResults": MAX_RESULTS,
                "q": GMAIL_LOOKBACK_QUERY,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            list_response = service.users().threads().list(**kwargs).execute()
            thread_items.extend(list_response.get("threads", []))
            page_token = list_response.get("nextPageToken")
            if not page_token:
                break
    except Exception:
        logger.exception("Failed to list Gmail threads for user %s.", user.id)
        return 0

    if not thread_items:
        return 0

    new_count = 0

    for item in thread_items:
        thread_id = item.get("id")
        if not thread_id:
            continue

        # Fetch full thread with all messages and headers
        try:
            thread_data = (
                service.users()
                .threads()
                .get(userId="me", id=thread_id, format="metadata",
                     metadataHeaders=["From", "To", "Cc", "Subject", "Date"])
                .execute()
            )
        except Exception:
            logger.exception("Failed to fetch thread %s for user %s.", thread_id, user.id)
            continue

        meta = _thread_to_metadata(thread_data)
        if not meta:
            continue

        # Determine direction relative to the authenticated user.
        # Check ALL messages in the thread to detect mutual conversations.
        user_sent = False
        user_received = False
        for msg in thread_data.get("messages", []):
            msg_headers = msg.get("payload", {}).get("headers", [])
            msg_from = _parse_email_addresses(_extract_header(msg_headers, "from"))
            if user_email in msg_from:
                user_sent = True
            else:
                user_received = True

        if user_sent and user_received:
            direction = "mutual"
        elif user_sent:
            direction = "outbound"
        else:
            direction = "inbound"

        # Use last message to determine counterparts for contact matching
        if user_email in meta["from_addresses"]:
            counterpart_emails = [e for e in (meta["to_addresses"] + meta["cc_addresses"])
                                  if e != user_email]
        else:
            counterpart_emails = [e for e in meta["from_addresses"] if e != user_email]

        # Match counterparts to contacts in the database
        matched_contacts: list[Contact] = []
        for addr in counterpart_emails:
            contact = await _find_contact_by_email(addr, user.id, db)
            if contact and contact not in matched_contacts:
                matched_contacts.append(contact)

        # Fallback: check all thread participants if last message didn't match
        if not matched_contacts:
            for addr in meta["participants"]:
                if addr == user_email:
                    continue
                contact = await _find_contact_by_email(addr, user.id, db)
                if contact and contact not in matched_contacts:
                    matched_contacts.append(contact)

        if not matched_contacts:
            continue

        # For mutual threads, prefer the first inbound snippet (what the
        # contact wrote) over the last outbound snippet (your reply).
        display_snippet = meta["snippet"]
        if direction == "mutual" and meta.get("first_snippet"):
            display_snippet = meta["first_snippet"]

        for contact in matched_contacts:
            interaction = await _upsert_interaction(
                contact=contact,
                user_id=user.id,
                thread_id=thread_id,
                direction=direction,
                snippet=f"{meta['subject']}: {display_snippet}"[:500] if meta.get("subject") else display_snippet,
                occurred_at=meta["occurred_at"],
                db=db,
            )
            # Check if this was newly added (no prior pk in identity map means new)
            is_new = interaction.created_at is None  # True before flush
            if is_new:
                new_count += 1

            # Update last_interaction_at on contact if this is more recent
            occurred = meta["occurred_at"]
            if (
                contact.last_interaction_at is None
                or contact.last_interaction_at < occurred
            ):
                contact.last_interaction_at = occurred

    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to flush interactions for user %s.", user.id)
        await db.rollback()
        return 0

    logger.info("Gmail sync for user %s: %d new interaction(s).", user.id, new_count)
    return new_count


async def sync_contact_emails(user: User, contact: Contact, db: AsyncSession) -> int:
    """Search Gmail for threads involving a specific contact's email addresses.

    Returns the number of new interactions created.
    """
    if not user.google_refresh_token:
        logger.warning("User %s has no google_refresh_token; skipping contact email sync.", user.id)
        return 0

    if not contact.emails:
        return 0

    try:
        service = _build_gmail_service(user.google_refresh_token)
    except Exception:
        logger.exception("Failed to build Gmail service for user %s.", user.id)
        return 0

    user_email = user.email.lower()

    # Build Gmail search query: from/to any of the contact's email addresses
    email_clauses = " OR ".join(f"from:{e} OR to:{e}" for e in contact.emails)
    query = f"({email_clauses}) newer_than:1y"

    thread_items: list[dict] = []
    page_token: str | None = None
    try:
        while True:
            kwargs: dict[str, Any] = {
                "userId": "me",
                "maxResults": MAX_RESULTS,
                "q": query,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            list_response = service.users().threads().list(**kwargs).execute()
            thread_items.extend(list_response.get("threads", []))
            page_token = list_response.get("nextPageToken")
            if not page_token:
                break
    except Exception:
        logger.exception("Failed to list Gmail threads for contact %s.", contact.id)
        return 0

    if not thread_items:
        return 0

    new_count = 0

    for item in thread_items:
        thread_id = item.get("id")
        if not thread_id:
            continue

        try:
            thread_data = (
                service.users()
                .threads()
                .get(userId="me", id=thread_id, format="metadata",
                     metadataHeaders=["From", "To", "Cc", "Subject", "Date"])
                .execute()
            )
        except Exception:
            logger.exception("Failed to fetch thread %s for contact %s.", thread_id, contact.id)
            continue

        meta = _thread_to_metadata(thread_data)
        if not meta:
            continue

        if user_email in meta["from_addresses"]:
            direction = "outbound"
        else:
            direction = "inbound"

        interaction = await _upsert_interaction(
            contact=contact,
            user_id=user.id,
            thread_id=thread_id,
            direction=direction,
            snippet=meta["snippet"],
            occurred_at=meta["occurred_at"],
            db=db,
        )
        is_new = interaction.created_at is None
        if is_new:
            new_count += 1

        occurred = meta["occurred_at"]
        if contact.last_interaction_at is None or contact.last_interaction_at < occurred:
            contact.last_interaction_at = occurred

    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to flush contact email sync for contact %s.", contact.id)
        await db.rollback()
        return 0

    logger.info("Contact email sync for contact %s: %d new interaction(s).", contact.id, new_count)
    return new_count
