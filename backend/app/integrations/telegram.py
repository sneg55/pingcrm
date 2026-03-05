"""Telegram MTProto integration using Telethon."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User as TelegramUser

from app.core.config import settings
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_MESSAGES = 100  # messages fetched per dialog per sync run


def _make_client(session_string: str | None = None) -> TelegramClient:
    """Construct a TelegramClient backed by a StringSession."""
    session = StringSession(session_string or "")
    return TelegramClient(
        session,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )


async def connect_telegram(user: User, phone: str, db: AsyncSession) -> str:
    """
    Initiate a Telegram login by sending an OTP to *phone*.

    Creates a TelegramClient, connects it, and requests the verification code.
    The interim session string (before sign-in is complete) is stored on the
    User model so the verify step can reuse the same session.

    Returns the phone_code_hash required by the verify step.
    """
    client = _make_client(user.telegram_session)
    await client.connect()

    result = await client.send_code_request(phone)
    phone_code_hash: str = result.phone_code_hash

    # Persist interim session so the verify step can reuse it.
    session_str: str = client.session.save()
    user.telegram_session = session_str
    await db.flush()

    await client.disconnect()
    return phone_code_hash


async def verify_telegram(
    user: User, phone: str, code: str, phone_code_hash: str, db: AsyncSession
) -> bool:
    """
    Complete Telegram sign-in with the OTP *code*.

    On success the finalised session string is saved to user.telegram_session.
    Returns True on success, raises on failure.
    """
    client = _make_client(user.telegram_session)
    await client.connect()

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    finally:
        session_str: str = client.session.save()
        user.telegram_session = session_str
        await db.flush()
        await client.disconnect()

    return True


async def fetch_telegram_dialogs(user: User) -> list[dict[str, Any]]:
    """
    Return metadata for all direct-message dialogs visible to *user*.

    Each element is a dict with keys: ``entity``, ``title``, ``username``,
    ``unread_count``.
    """
    if not user.telegram_session:
        logger.warning("User %s has no telegram_session; skipping dialog fetch.", user.id)
        return []

    client = _make_client(user.telegram_session)
    await client.connect()

    dialogs: list[dict[str, Any]] = []
    try:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            # Only consider private conversations (other users, not groups/channels)
            if not isinstance(entity, TelegramUser):
                continue
            dialogs.append(
                {
                    "entity": entity,
                    "title": dialog.title,
                    "username": entity.username,
                    "unread_count": dialog.unread_count,
                }
            )
    finally:
        await client.disconnect()

    return dialogs


async def _find_contact_by_username(
    username: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Locate a Contact belonging to *user_id* whose telegram_username matches."""
    username_lower = username.lower().lstrip("@")
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.telegram_username == username_lower,
        )
    )
    return result.scalar_one_or_none()


async def _find_contact_by_phone(
    phone: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Locate a Contact belonging to *user_id* whose phones list contains *phone*."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.phones.contains([phone]),
        )
    )
    return result.scalar_one_or_none()


async def _upsert_interaction(
    *,
    contact: Contact,
    user_id: uuid.UUID,
    message_id: str,
    direction: str,
    content_preview: str | None,
    occurred_at: datetime,
    db: AsyncSession,
) -> tuple[Interaction, bool]:
    """
    Create an Interaction for *message_id* if it doesn't exist yet.

    Returns a (Interaction, is_new) tuple.
    """
    result = await db.execute(
        select(Interaction).where(
            Interaction.raw_reference_id == message_id,
            Interaction.contact_id == contact.id,
            Interaction.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user_id,
        platform="telegram",
        direction=direction,
        content_preview=content_preview[:500] if content_preview else None,
        raw_reference_id=message_id,
        occurred_at=occurred_at,
    )
    db.add(interaction)
    return interaction, True


async def sync_telegram_chats(user: User, db: AsyncSession) -> int:
    """
    Sync Telegram DM conversations for *user* as Interaction records.

    For each dialog:
    - Fetches the last MAX_MESSAGES messages.
    - Matches the counterpart to a Contact by telegram_username.
    - Creates Interaction records (platform="telegram").
    - Updates contact.last_interaction_at when appropriate.

    Returns the number of new interactions created.
    """
    if not user.telegram_session:
        logger.warning("User %s has no telegram_session; skipping Telegram sync.", user.id)
        return 0

    client = _make_client(user.telegram_session)
    await client.connect()

    me = await client.get_me()
    my_id: int = me.id

    new_count = 0

    try:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, TelegramUser):
                continue

            # Resolve the contact in our database
            contact: Contact | None = None
            if entity.username:
                contact = await _find_contact_by_username(entity.username, user.id, db)
            if contact is None and entity.phone:
                contact = await _find_contact_by_phone(entity.phone, user.id, db)

            if contact is None:
                continue

            # Iterate recent messages for this dialog
            async for message in client.iter_messages(entity, limit=MAX_MESSAGES):
                if message.message is None:
                    continue  # skip service messages

                direction = "outbound" if message.sender_id == my_id else "inbound"
                message_id = f"{entity.id}:{message.id}"
                occurred_at = message.date.replace(tzinfo=UTC) if message.date.tzinfo is None else message.date

                _interaction, is_new = await _upsert_interaction(
                    contact=contact,
                    user_id=user.id,
                    message_id=message_id,
                    direction=direction,
                    content_preview=message.message,
                    occurred_at=occurred_at,
                    db=db,
                )
                if is_new:
                    new_count += 1

                # Keep last_interaction_at up-to-date
                if (
                    contact.last_interaction_at is None
                    or contact.last_interaction_at < occurred_at
                ):
                    contact.last_interaction_at = occurred_at

    finally:
        await client.disconnect()

    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to flush Telegram interactions for user %s.", user.id)
        await db.rollback()
        return 0

    logger.info("Telegram sync for user %s: %d new interaction(s).", user.id, new_count)
    return new_count


async def match_telegram_contacts(user: User, db: AsyncSession) -> int:
    """
    Cross-reference Telegram contacts with existing Contact records.

    Matches by phone number first, then by username.  When a match is found
    and the contact does not yet have telegram_username set, it is populated.

    Returns the number of contacts updated.
    """
    if not user.telegram_session:
        logger.warning(
            "User %s has no telegram_session; skipping Telegram contact match.", user.id
        )
        return 0

    client = _make_client(user.telegram_session)
    await client.connect()

    updated = 0
    try:
        result = await client.get_contacts()
        tg_contacts: list[TelegramUser] = result.users  # type: ignore[attr-defined]

        for tg_user in tg_contacts:
            contact: Contact | None = None

            # 1. Try phone match
            if tg_user.phone:
                contact = await _find_contact_by_phone(tg_user.phone, user.id, db)

            # 2. Try username match
            if contact is None and tg_user.username:
                contact = await _find_contact_by_username(tg_user.username, user.id, db)

            if contact is None:
                continue

            if tg_user.username and contact.telegram_username != tg_user.username.lower():
                contact.telegram_username = tg_user.username.lower().lstrip("@")
                updated += 1

    finally:
        await client.disconnect()

    if updated:
        try:
            await db.flush()
        except Exception:
            logger.exception("Failed to flush Telegram contact matches for user %s.", user.id)
            await db.rollback()
            return 0

    logger.info("Telegram contact match for user %s: %d contact(s) updated.", user.id, updated)
    return updated
