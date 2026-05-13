"""Gmail API integration for syncing email messages as Interactions."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

from app.integrations.gmail_helpers import (
    _build_gmail_service,
    _clean_snippet,
    _extract_bcc_hashes,
    _extract_header,
    _extract_plain_body,
    _find_contact_by_bcc_hash,
    _find_contact_by_email,
    _parse_email_addresses,
)

logger = logging.getLogger(__name__)

MAX_RESULTS = 500  # threads per page
GMAIL_LOOKBACK_QUERY = "newer_than:1y"  # sync last year of email


def _process_thread_messages(
    thread_data: dict, user_email: str
) -> list[dict]:
    """Extract per-message metadata from a Gmail thread.

    Returns a list of dicts, one per message:
        {message_id, thread_id, subject, direction, snippet, occurred_at,
         counterpart_emails, all_participants, bcc_hashes}
    """
    messages = thread_data.get("messages", [])
    if not messages:
        return []

    thread_id = thread_data.get("id", "")

    # Get subject from first message
    first_headers = messages[0].get("payload", {}).get("headers", [])
    subject = _extract_header(first_headers, "subject") or "(no subject)"

    # Collect all participants for fallback contact matching
    all_participants: set[str] = set()
    for msg in messages:
        msg_headers = msg.get("payload", {}).get("headers", [])
        for hdr in ("from", "to", "cc"):
            all_participants.update(_parse_email_addresses(_extract_header(msg_headers, hdr)))

    results = []
    for msg in messages:
        msg_id = msg.get("id", "")
        if not msg_id:
            continue

        msg_headers = msg.get("payload", {}).get("headers", [])
        from_addrs = _parse_email_addresses(_extract_header(msg_headers, "from"))
        to_addrs = _parse_email_addresses(_extract_header(msg_headers, "to"))
        cc_addrs = _parse_email_addresses(_extract_header(msg_headers, "cc"))
        bcc_addrs = _parse_email_addresses(_extract_header(msg_headers, "bcc"))

        # Extract BCC hashes from +hash addresses
        all_addrs = to_addrs + cc_addrs + bcc_addrs
        bcc_hashes = _extract_bcc_hashes(all_addrs, user_email)

        # Direction: outbound if user sent it, inbound otherwise
        if user_email in from_addrs:
            direction = "outbound"
            counterpart_emails = [e for e in (to_addrs + cc_addrs) if e != user_email and "+" not in e.split("@")[0]]
        else:
            direction = "inbound"
            counterpart_emails = [e for e in from_addrs if e != user_email]

        # Timestamp
        internal_date_ms = int(msg.get("internalDate", 0))
        occurred_at = datetime.fromtimestamp(internal_date_ms / 1000, tz=UTC)

        # Content: prefer full body (from format="full") over snippet
        body = _extract_plain_body(msg.get("payload", {}))
        snippet = body if body else (msg.get("snippet", "") or "")

        results.append({
            "message_id": msg_id,
            "thread_id": thread_id,
            "subject": subject,
            "direction": direction,
            "snippet": snippet,
            "occurred_at": occurred_at,
            "counterpart_emails": counterpart_emails,
            "all_participants": list(all_participants),
            "bcc_hashes": bcc_hashes,
        })

    return results


async def _sync_thread_messages(
    thread_data: dict,
    user: User,
    user_email: str,
    db: AsyncSession,
    service: Any = None,
) -> int:
    """Sync individual messages from a thread as separate Interactions.

    Returns count of new interactions created.
    """
    msg_metas = _process_thread_messages(thread_data, user_email)

    # If any message has BCC hashes and service is available, re-fetch
    # the thread with format="full" to get actual email body (not just snippet).
    has_bcc = any(meta.get("bcc_hashes") for meta in msg_metas)
    if has_bcc and service and not _extract_plain_body(thread_data.get("messages", [{}])[0].get("payload", {})):
        try:
            full_data = (
                service.users()
                .threads()
                .get(userId="me", id=thread_data.get("id", ""), format="full")
                .execute()
            )
            msg_metas = _process_thread_messages(full_data, user_email)
        except Exception:
            logger.warning("Failed to re-fetch thread %s with full format", thread_data.get("id"))
    if not msg_metas:
        return 0

    new_count = 0

    for meta in msg_metas:
        # Dedup by message ID (not thread ID)
        ref_id = f"gmail:{meta['message_id']}"

        # Priority 1: Match via BCC hash (user+hash@domain → contact)
        matched_contacts: list[Contact] = []
        matched_via_bcc = False
        for bcc_hash in meta.get("bcc_hashes", []):
            contact = await _find_contact_by_bcc_hash(bcc_hash, user.id, db)
            if contact and contact not in matched_contacts:
                matched_contacts.append(contact)
                matched_via_bcc = True

        # Priority 2: Match counterpart emails to contacts
        if not matched_contacts:
            for addr in meta["counterpart_emails"]:
                contact = await _find_contact_by_email(addr, user.id, db)
                if contact and contact not in matched_contacts:
                    matched_contacts.append(contact)

        # Priority 3: Fallback — check all thread participants
        if not matched_contacts:
            for addr in meta["all_participants"]:
                if addr == user_email:
                    continue
                contact = await _find_contact_by_email(addr, user.id, db)
                if contact and contact not in matched_contacts:
                    matched_contacts.append(contact)

        if not matched_contacts:
            continue

        # BCC-logged emails are intentionally forwarded — keep full content.
        # Regular emails: strip quoted reply text for cleaner previews.
        preview = meta["snippet"] if matched_via_bcc else _clean_snippet(meta["snippet"])

        # Skip messages with empty content after cleaning (e.g. signature-only
        # forward wrappers like "-- Nick Sawinyh")
        if not preview.strip():
            continue

        for contact in matched_contacts:
            # Check if already exists
            existing_result = await db.execute(
                select(Interaction).where(
                    Interaction.raw_reference_id == ref_id,
                    Interaction.contact_id == contact.id,
                    Interaction.user_id == user.id,
                ).limit(1)
            )
            if existing_result.scalar_one_or_none():
                continue

            # Also check old thread-level ref_id for backward compatibility
            # (previous sync used thread_id as ref, not message_id)
            old_ref = meta["thread_id"]
            old_result = await db.execute(
                select(Interaction).where(
                    Interaction.raw_reference_id == old_ref,
                    Interaction.contact_id == contact.id,
                    Interaction.user_id == user.id,
                ).limit(1)
            )
            old_existing = old_result.scalar_one_or_none()
            if old_existing:
                # Migrate: update ref_id to message-level, keep the record
                old_existing.raw_reference_id = ref_id
                old_existing.direction = meta["direction"]
                old_existing.content_preview = preview[:500] if preview else None
                old_existing.occurred_at = meta["occurred_at"]
                # Don't count as new — it's a migration of existing record
                continue

            interaction = Interaction(
                id=uuid.uuid4(),
                contact_id=contact.id,
                user_id=user.id,
                platform="email",
                direction=meta["direction"],
                content_preview=preview[:500] if preview else None,
                raw_reference_id=ref_id,
                occurred_at=meta["occurred_at"],
            )
            db.add(interaction)
            new_count += 1

            # Update last_interaction_at on contact
            if (
                contact.last_interaction_at is None
                or contact.last_interaction_at < meta["occurred_at"]
            ):
                contact.last_interaction_at = meta["occurred_at"]

    return new_count


async def sync_gmail_for_user(user: User, db: AsyncSession) -> int:
    """Sync Gmail messages for *user* as per-message Interaction records.

    Each email message in a thread becomes its own Interaction with correct
    direction (inbound/outbound) and snippet.

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

        try:
            thread_data = (
                service.users()
                .threads()
                .get(userId="me", id=thread_id, format="metadata",
                     metadataHeaders=["From", "To", "Cc", "Bcc", "Subject", "Date"])
                .execute()
            )
        except Exception:
            logger.exception("Failed to fetch thread %s for user %s.", thread_id, user.id)
            continue

        new_count += await _sync_thread_messages(thread_data, user, user_email, db, service=service)

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
                     metadataHeaders=["From", "To", "Cc", "Bcc", "Subject", "Date"])
                .execute()
            )
        except Exception:
            logger.exception("Failed to fetch thread %s for contact %s.", thread_id, contact.id)
            continue

        new_count += await _sync_thread_messages(thread_data, user, user_email, db, service=service)

    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to flush contact email sync for contact %s.", contact.id)
        await db.rollback()
        return 0

    logger.info("Contact email sync for contact %s: %d new interaction(s).", contact.id, new_count)
    return new_count
