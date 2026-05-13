"""Gmail API integration for syncing email messages as Interactions."""
from __future__ import annotations

import email.utils
import logging
import re
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

import base64

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
MAX_RESULTS = 500  # threads per page
GMAIL_LOOKBACK_QUERY = "newer_than:1y"  # sync last year of email

# Patterns for stripping quoted email text from snippets
_QUOTE_PATTERNS = [
    re.compile(r"\s*On\s+\w+\s+\d+,\s+\d{4}\s+at\s+\d+:\d+.*wrote:.*", re.DOTALL),  # On March 23, 2026 at 12:41, Name wrote:
    re.compile(r"\s*On\s+\d{4}-\d{2}-\d{2}.*wrote:.*", re.DOTALL),  # On 2026-03-23 ... wrote:
    re.compile(r"\s*--\s*\n.*", re.DOTALL),  # -- signature separator
    re.compile(r"\s*_{3,}.*", re.DOTALL),  # ___ separator
    re.compile(r"\s*-{3,}\s*(Original Message|Forwarded).*", re.DOTALL | re.IGNORECASE),  # --- Original Message
]


def _clean_snippet(snippet: str) -> str:
    """Strip quoted reply text and signatures from an email snippet."""
    if not snippet:
        return ""
    text = snippet
    for pat in _QUOTE_PATTERNS:
        text = pat.split(text, 1)[0]
    return text.strip()


def _extract_plain_body(payload: dict) -> str:
    """Extract plain-text body from a Gmail message payload.

    Handles both simple messages (body directly in payload) and multipart
    messages (text/plain part nested under payload.parts).
    Returns up to 2000 chars of plain text.
    """
    def _find_text_part(part: dict) -> str | None:
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                try:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                except Exception:
                    logger.warning(
                        "gmail body part decode failed",
                        extra={"provider": "gmail"},
                        exc_info=True,
                    )
                    return None
        for sub in part.get("parts", []):
            result = _find_text_part(sub)
            if result:
                return result
        return None

    body = _find_text_part(payload)
    if body:
        return body[:2000].strip()
    return ""


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


_PLUS_ADDR_RE = re.compile(r"\+([a-f0-9]{7})@")


def _extract_bcc_hashes(addresses: list[str], user_email: str) -> list[str]:
    """Extract BCC hashes from +hash addresses matching the user's email domain.

    E.g. 'nsawinyh+c7f3a2b@gmail.com' → ['c7f3a2b'] if user is nsawinyh@gmail.com
    """
    if not user_email:
        return []
    local, _, domain = user_email.partition("@")
    if not domain:
        return []
    hashes = []
    for addr in addresses:
        if not addr.endswith(f"@{domain}"):
            continue
        m = _PLUS_ADDR_RE.search(addr)
        if m and addr.startswith(f"{local}+"):
            hashes.append(m.group(1))
    return hashes


async def _find_contact_by_bcc_hash(
    bcc_hash: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Look up a Contact by its BCC hash."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.bcc_hash == bcc_hash,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _find_contact_by_email(
    email_addr: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Look up a Contact belonging to *user_id* whose emails list contains
    *email_addr* (case-insensitive, after lower+trim)."""
    from sqlalchemy import text
    from app.services.contact_resolver import normalize_email
    norm = normalize_email(email_addr)
    if not norm:
        return None
    result = await db.execute(
        text(
            """
            SELECT id FROM contacts
            WHERE user_id = :uid
              AND EXISTS (
                SELECT 1 FROM unnest(emails) e
                WHERE lower(trim(e)) = :norm
              )
            LIMIT 1
            """
        ),
        {"uid": user_id, "norm": norm},
    )
    row = result.first()
    if not row:
        return None
    return await db.get(Contact, row[0])


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
