from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.gmail_helpers import _build_gmail_service
from app.integrations.gmail_threads import _sync_thread_messages
from app.integrations.google_accounts import load_google_mailboxes
from app.models.contact import Contact
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_RESULTS = 500
GMAIL_LOOKBACK_QUERY = "newer_than:1y"
THREAD_METADATA_HEADERS = ["From", "To", "Cc", "Bcc", "Subject", "Date"]


def _list_thread_items(service: Any, query: str) -> list[dict]:
    thread_items: list[dict] = []
    page_token: str | None = None
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
            return thread_items


async def _sync_mailbox(
    user: User,
    mailbox_email: str,
    refresh_token: str,
    own_emails: frozenset[str],
    query: str,
    db: AsyncSession,
) -> int:
    try:
        service = _build_gmail_service(refresh_token)
    except Exception:
        logger.exception(
            "Failed to build Gmail service for user %s account %s.", user.id, mailbox_email
        )
        return 0

    try:
        thread_items = _list_thread_items(service, query)
    except Exception:
        logger.exception(
            "Failed to list Gmail threads for user %s account %s.", user.id, mailbox_email
        )
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
                     metadataHeaders=THREAD_METADATA_HEADERS)
                .execute()
            )
        except Exception:
            logger.exception(
                "Failed to fetch thread %s for user %s account %s.",
                thread_id, user.id, mailbox_email,
            )
            continue

        new_count += await _sync_thread_messages(
            thread_data, user, mailbox_email, own_emails, db, service=service
        )
    return new_count


async def _sync_all_mailboxes(user: User, query: str, db: AsyncSession, scope: str) -> int:
    mailboxes = await load_google_mailboxes(user, db)
    if not mailboxes.accounts:
        logger.warning("User %s has no connected Google account; skipping %s.", user.id, scope)
        return 0

    new_count = 0
    for mailbox_email, refresh_token in mailboxes.accounts:
        new_count += await _sync_mailbox(
            user, mailbox_email, refresh_token, mailboxes.own_emails, query, db
        )

    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to flush %s for user %s.", scope, user.id)
        await db.rollback()
        return 0

    logger.info("%s for user %s: %d new interaction(s).", scope, user.id, new_count)
    return new_count


async def sync_gmail_for_user(user: User, db: AsyncSession) -> int:
    return await _sync_all_mailboxes(user, GMAIL_LOOKBACK_QUERY, db, "Gmail sync")


async def sync_contact_emails(user: User, contact: Contact, db: AsyncSession) -> int:
    if not contact.emails:
        return 0

    email_clauses = " OR ".join(f"from:{e} OR to:{e}" for e in contact.emails)
    query = f"({email_clauses}) newer_than:1y"
    return await _sync_all_mailboxes(user, query, db, f"Contact email sync for contact {contact.id}")
