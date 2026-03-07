"""Telegram MTProto integration using Telethon."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User as TelegramUser

from app.core.config import settings
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_MESSAGES = 50  # messages fetched per dialog per sync run
MAX_DIALOGS = 30  # max dialogs processed per sync run
MAX_BIO_SYNC_CONTACTS = 100  # max contacts fetched per bio sync run


def _make_client(session_string: str | None = None) -> TelegramClient:
    """Construct a TelegramClient backed by a StringSession."""
    session = StringSession(session_string or "")
    return TelegramClient(
        session,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )


async def _ensure_connected(client: TelegramClient) -> None:
    """Connect the client, retrying once if the first attempt silently fails."""
    await client.connect()
    if not client.is_connected():
        await client.connect()
    if not client.is_connected():
        raise RuntimeError("Failed to establish connection to Telegram servers")


AVATARS_DIR = Path(os.environ.get("AVATARS_DIR", "static/avatars"))


async def _download_avatar(
    client: TelegramClient, entity: TelegramUser, contact_id: uuid.UUID
) -> str | None:
    """Download a Telegram user's profile photo and return the relative URL path."""
    try:
        AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{contact_id}.jpg"
        filepath = AVATARS_DIR / filename
        result = await client.download_profile_photo(
            entity, file=str(filepath), download_big=False,
        )
        if result:
            return f"/static/avatars/{filename}"
    except Exception:
        logger.debug("Failed to download avatar for entity %s", entity.id)
    return None


async def connect_telegram(user: User, phone: str, db: AsyncSession) -> str:
    """
    Initiate a Telegram login by sending an OTP to *phone*.

    Creates a TelegramClient, connects it, and requests the verification code.
    The interim session string (before sign-in is complete) is stored on the
    User model so the verify step can reuse the same session.

    Returns the phone_code_hash required by the verify step.
    """
    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    result = await client.send_code_request(phone)
    phone_code_hash: str = result.phone_code_hash

    # Persist interim session so the verify step can reuse it.
    user.telegram_session = client.session.save()
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
    await _ensure_connected(client)

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        # Save session so the 2FA step can resume from it.
        user.telegram_session = client.session.save()
        await db.flush()
        await client.disconnect()
        raise
    except Exception:
        await client.disconnect()
        raise

    # Save the finalised (fully authenticated) session and username
    user.telegram_session = client.session.save()
    try:
        me = await client.get_me()
        if me and me.username:
            user.telegram_username = me.username
    except Exception:
        pass
    await db.flush()
    await client.disconnect()

    return True


async def verify_telegram_2fa(user: User, password: str, db: AsyncSession) -> bool:
    """
    Complete Telegram sign-in for accounts with two-step verification.

    Called after verify_telegram raises SessionPasswordNeededError.
    The session must already be in the post-code state.
    """
    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    try:
        await client.sign_in(password=password)
    except Exception:
        await client.disconnect()
        raise

    # Save the finalised session and username
    user.telegram_session = client.session.save()
    try:
        me = await client.get_me()
        if me and me.username:
            user.telegram_username = me.username
    except Exception:
        pass
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
    await _ensure_connected(client)

    dialogs: list[dict[str, Any]] = []
    try:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            # Only consider private conversations with real users (not groups/channels/bots)
            if not isinstance(entity, TelegramUser):
                continue
            if getattr(entity, "bot", False):
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
        ).limit(1)
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
        ).limit(1)
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
        ).limit(1)
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
        return {"new_interactions": 0, "new_contacts": 0, "affected_contact_ids": []}

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    if not await client.is_user_authorized():
        logger.warning("Telegram session for user %s is not authorized. Clearing session.", user.id)
        user.telegram_session = None
        user.telegram_username = None
        await db.flush()
        await client.disconnect()
        raise RuntimeError("Telegram session expired. Please reconnect your account.")

    me = await client.get_me()
    my_id: int = me.id

    new_count = 0
    dialogs_checked = 0
    created_contacts = 0
    affected_contact_ids: set[str] = set()

    try:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, TelegramUser):
                continue
            if getattr(entity, "bot", False):
                continue
            dialogs_checked += 1
            if dialogs_checked > MAX_DIALOGS:
                logger.info("Reached MAX_DIALOGS (%d) for user %s, stopping.", MAX_DIALOGS, user.id)
                break

            # Resolve the contact in our database
            contact: Contact | None = None
            if entity.username:
                contact = await _find_contact_by_username(entity.username, user.id, db)
            if contact is None and entity.phone:
                contact = await _find_contact_by_phone(entity.phone, user.id, db)

            if contact is None:
                # Auto-create contact from Telegram entity
                first_name = getattr(entity, "first_name", None) or ""
                last_name = getattr(entity, "last_name", None) or ""
                full = f"{first_name} {last_name}".strip() or entity.username or str(entity.id)
                contact = Contact(
                    user_id=user.id,
                    given_name=first_name or entity.username or str(entity.id),
                    family_name=last_name or None,
                    full_name=full,
                    telegram_username=(entity.username or "").lower().lstrip("@") or None,
                    telegram_user_id=str(entity.id),
                    phones=[entity.phone] if entity.phone else [],
                    source="telegram",
                )
                db.add(contact)
                await db.flush()
                created_contacts += 1
            else:
                # Backfill telegram_user_id if missing
                if not contact.telegram_user_id:
                    contact.telegram_user_id = str(entity.id)

            # Download avatar if missing
            if not contact.avatar_url:
                avatar_path = await _download_avatar(client, entity, contact.id)
                if avatar_path:
                    contact.avatar_url = avatar_path

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
                    affected_contact_ids.add(str(contact.id))

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
        return {"new_interactions": 0, "new_contacts": 0, "affected_contact_ids": []}

    logger.info(
        "Telegram sync for user %s: %d new interaction(s), %d new contacts, %d dialogs checked.",
        user.id, new_count, created_contacts, dialogs_checked,
    )
    return {
        "new_interactions": new_count,
        "new_contacts": created_contacts,
        "affected_contact_ids": list(affected_contact_ids),
    }


MAX_GROUPS = 20  # max private groups to scan for members
MAX_MEMBERS_PER_GROUP = 200  # max members fetched per group


async def sync_telegram_group_members(user: User, db: AsyncSession) -> dict[str, int]:
    """
    Pull members from private Telegram groups/supergroups where *user* is a
    member or admin.  Each member is upserted as a Contact with the tag
    "2nd Tier".

    Public groups and channels are skipped.  Bots are excluded.

    Returns counts of new and existing contacts processed.
    """
    if not user.telegram_session:
        logger.warning("User %s has no telegram_session; skipping group member sync.", user.id)
        return {"new_contacts": 0, "updated_contacts": 0, "groups_scanned": 0}

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session expired. Please reconnect your account.")

    me = await client.get_me()
    my_id: int = me.id

    new_contacts = 0
    updated_contacts = 0
    groups_scanned = 0
    tag_label = "2nd Tier"

    try:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity

            # Only consider groups / supergroups (not channels, not DMs)
            is_group = isinstance(entity, Chat)
            is_supergroup = isinstance(entity, Channel) and getattr(entity, "megagroup", False)
            if not (is_group or is_supergroup):
                continue

            # Skip public groups (those with a username are public)
            if getattr(entity, "username", None):
                continue

            groups_scanned += 1
            if groups_scanned > MAX_GROUPS:
                logger.info(
                    "Reached MAX_GROUPS (%d) for user %s, stopping.", MAX_GROUPS, user.id
                )
                break

            group_title = getattr(entity, "title", None) or str(entity.id)
            logger.debug("Scanning group '%s' (id=%s) for members.", group_title, entity.id)

            try:
                participants = await client.get_participants(entity, limit=MAX_MEMBERS_PER_GROUP)
            except Exception:
                logger.debug(
                    "Cannot fetch participants for group '%s' (id=%s), skipping.",
                    group_title, entity.id,
                )
                continue

            for member in participants:
                if not isinstance(member, TelegramUser):
                    continue
                if getattr(member, "bot", False):
                    continue
                if member.id == my_id:
                    continue

                # Try to find existing contact
                contact: Contact | None = None
                if member.username:
                    contact = await _find_contact_by_username(member.username, user.id, db)
                if contact is None and member.phone:
                    contact = await _find_contact_by_phone(member.phone, user.id, db)

                tg_username = (member.username or "").lower().lstrip("@") or None
                tg_user_id = str(member.id)

                if contact is None:
                    first_name = getattr(member, "first_name", None) or ""
                    last_name = getattr(member, "last_name", None) or ""
                    full = f"{first_name} {last_name}".strip() or member.username or tg_user_id
                    contact = Contact(
                        user_id=user.id,
                        given_name=first_name or member.username or tg_user_id,
                        family_name=last_name or None,
                        full_name=full,
                        telegram_username=tg_username,
                        telegram_user_id=tg_user_id,
                        phones=[member.phone] if member.phone else [],
                        source="telegram",
                        tags=[tag_label],
                    )
                    db.add(contact)
                    await db.flush()
                    new_contacts += 1
                else:
                    # Backfill telegram info if missing
                    if tg_username and not contact.telegram_username:
                        contact.telegram_username = tg_username
                    if not contact.telegram_user_id:
                        contact.telegram_user_id = tg_user_id

                    # Only tag as "2nd Tier" if this contact has no direct interactions
                    has_interactions = await db.execute(
                        select(Interaction.id).where(
                            Interaction.contact_id == contact.id,
                            Interaction.user_id == user.id,
                        ).limit(1)
                    )
                    if has_interactions.scalar_one_or_none() is not None:
                        continue  # skip — already has direct conversations

                    current_tags = list(contact.tags or [])
                    if tag_label not in current_tags:
                        current_tags.append(tag_label)
                        contact.tags = current_tags
                        updated_contacts += 1

    finally:
        await client.disconnect()

    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to flush group member contacts for user %s.", user.id)
        await db.rollback()
        return {"new_contacts": 0, "updated_contacts": 0, "groups_scanned": 0}

    logger.info(
        "Telegram group member sync for user %s: %d new, %d updated, %d groups scanned.",
        user.id, new_contacts, updated_contacts, groups_scanned,
    )
    return {
        "new_contacts": new_contacts,
        "updated_contacts": updated_contacts,
        "groups_scanned": groups_scanned,
    }


async def fetch_common_groups(
    user: User, telegram_username: str | None = None, telegram_user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return groups/channels in common between *user* and a target.

    The target can be identified by *telegram_username* or *telegram_user_id*.
    Each element is a dict with ``id``, ``title``, and ``participants_count``.
    """
    if not user.telegram_session:
        return []
    if not telegram_username and not telegram_user_id:
        return []

    from telethon.tl.functions.messages import GetCommonChatsRequest

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    try:
        # Resolve target — prefer username, fall back to numeric user ID
        if telegram_username:
            target = await client.get_input_entity(telegram_username)
        else:
            target = await client.get_input_entity(int(telegram_user_id))
        result = await client(GetCommonChatsRequest(
            user_id=target,
            max_id=0,
            limit=100,
        ))
        groups: list[dict[str, Any]] = []
        for chat in result.chats:
            username = getattr(chat, "username", None)
            link = f"https://t.me/{username}" if username else None
            groups.append({
                "id": chat.id,
                "title": getattr(chat, "title", None) or str(chat.id),
                "username": username,
                "link": link,
                "participants_count": getattr(chat, "participants_count", None),
            })
        return groups
    except Exception:
        logger.warning(
            "fetch_common_groups: failed for user %s / @%s",
            user.id, telegram_username,
        )
        return []
    finally:
        await client.disconnect()


async def sync_telegram_bios(user: User, db: AsyncSession) -> dict[str, int]:
    """Fetch and store Telegram bios for all contacts with a telegram_username.

    Creates notifications for bio changes. Returns counts.
    """
    from app.models.notification import Notification
    from telethon.tl.functions.users import GetFullUserRequest

    if not user.telegram_session:
        return {"bios_updated": 0, "bio_changes": 0}

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user.id,
            Contact.telegram_username.isnot(None),
        ).limit(MAX_BIO_SYNC_CONTACTS)
    )
    contacts: list[Contact] = list(result.scalars().all())

    updated = 0
    bio_changes = 0

    try:
        for contact in contacts:
            username = (contact.telegram_username or "").lstrip("@").strip()
            if not username:
                continue

            try:
                input_user = await client.get_input_entity(username)
                full = await client(GetFullUserRequest(input_user))
                current_bio = getattr(full.full_user, "about", None) or ""
            except Exception:
                logger.debug("sync_telegram_bios: failed to fetch bio for @%s", username)
                continue

            if not current_bio:
                continue

            stored_bio = contact.telegram_bio or ""
            if current_bio == stored_bio:
                continue

            had_previous = bool(stored_bio)
            contact.telegram_bio = current_bio
            updated += 1

            if had_previous:
                bio_changes += 1
                display_name = contact.full_name or username
                notif = Notification(
                    user_id=user.id,
                    notification_type="bio_change",
                    title=f"@{username} updated their Telegram bio",
                    body=f"{display_name} changed their bio to: {current_bio[:200]}",
                    link=f"/contacts/{contact.id}",
                )
                db.add(notif)
    finally:
        await client.disconnect()

    if updated:
        await db.flush()

    logger.info(
        "sync_telegram_bios for user %s: %d updated, %d bio changes.",
        user.id, updated, bio_changes,
    )
    return {"bios_updated": updated, "bio_changes": bio_changes}


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
    await _ensure_connected(client)

    updated = 0
    try:
        result = await client.get_contacts()
        tg_contacts: list[TelegramUser] = result.users  # type: ignore[attr-defined]

        for tg_user in tg_contacts:
            if getattr(tg_user, "bot", False):
                continue
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
