"""Telegram MTProto integration using Telethon."""
from __future__ import annotations

import asyncio
import logging
import os
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError, SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, InputPeerUser, User as TelegramUser

from app.core.config import settings
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_MESSAGES = 50  # messages fetched per dialog per sync run
MAX_BIO_SYNC_CONTACTS = 100  # max contacts fetched per bio sync run

RATE_GATE_KEY = "tg_flood:{user_id}"


async def _check_rate_gate(user_id: str) -> int | None:
    """Return seconds remaining if user is rate-gated, else None."""
    from app.core.redis import get_redis
    r = get_redis()
    ttl = await r.ttl(RATE_GATE_KEY.format(user_id=user_id))
    return ttl if ttl > 0 else None


async def _set_rate_gate(user_id: str, seconds: int) -> None:
    """Record a FloodWait so all operations respect the cooldown."""
    from app.core.redis import get_redis
    r = get_redis()
    await r.set(RATE_GATE_KEY.format(user_id=user_id), "1", ex=seconds)


def _make_client(session_string: str | None = None) -> TelegramClient:
    """Construct a TelegramClient backed by a StringSession."""
    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
        raise RuntimeError(
            "Telegram credentials not configured: set TELEGRAM_API_ID and "
            "TELEGRAM_API_HASH environment variables."
        )
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


# Public aliases — use these instead of the private _-prefixed functions
make_client = _make_client
ensure_connected = _ensure_connected

AVATARS_DIR = Path(os.environ.get(
    "AVATARS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "static" / "avatars"),
))

import re as _re

_TWITTER_URL_RE = _re.compile(
    r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/(@?[\w]{1,15})\b",
    _re.IGNORECASE,
)
_TWITTER_MENTION_RE = _re.compile(r"@([\w]{1,15})\b")


def _extract_twitter_handle(bio: str) -> str | None:
    """Extract a Twitter/X handle from a bio string.

    Looks for twitter.com/handle or x.com/handle URLs first,
    then falls back to @handle mentions near twitter/X keywords.
    """
    # Direct URL match
    m = _TWITTER_URL_RE.search(bio)
    if m:
        handle = m.group(1).lstrip("@")
        if handle.lower() not in {"home", "search", "explore", "settings", "i"}:
            return handle

    # @handle near twitter/X keyword
    bio_lower = bio.lower()
    if any(kw in bio_lower for kw in ("twitter", "tw:", "𝕏", " x:", "x.com")):
        mentions = _TWITTER_MENTION_RE.findall(bio)
        for handle in mentions:
            if handle.lower() not in {"telegram", "email", "phone"}:
                return handle

    return None


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


async def send_telegram_message(
    user: User,
    username: str,
    message: str,
    *,
    telegram_user_id: int | str | None = None,
    scheduled_for: object | None = None,
) -> dict:
    """Send a Telegram message to *username* using the user's session.

    If *telegram_user_id* is provided, uses it directly to avoid a
    ResolveUsernameRequest call (which is heavily rate-limited by Telegram).

    If *scheduled_for* is a datetime, the message is scheduled for future
    delivery using Telegram's native scheduled-message feature.

    Returns dict with ``message_id``, ``sent`` status, ``scheduled``,
    and ``resolved_user_id`` (for caller to cache).
    """
    if not user.telegram_session:
        raise RuntimeError("No Telegram session. Please connect your account first.")

    # Check rate gate before connecting
    gate_ttl = await _check_rate_gate(str(user.id))
    if gate_ttl:
        raise RuntimeError(
            f"Telegram rate limit: please wait {gate_ttl // 60}m before sending messages.",
            gate_ttl,
        )

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)
    try:
        # Use cached user ID to avoid rate-limited username resolution
        resolved_id = None
        if telegram_user_id:
            uid = int(telegram_user_id)
            try:
                entity = await client.get_input_entity(uid)
            except (ValueError, TypeError):
                logger.debug("Cached user_id %s invalid, falling back to username", uid)
                entity = await client.get_input_entity(username)
                resolved_id = getattr(entity, "user_id", None)
        else:
            entity = await client.get_input_entity(username)
            resolved_id = getattr(entity, "user_id", None)

        kwargs: dict = {}
        if scheduled_for is not None:
            kwargs["schedule"] = scheduled_for
        result = await client.send_message(entity, message, **kwargs)
        return {
            "sent": True,
            "message_id": result.id,
            "scheduled": scheduled_for is not None,
            "resolved_user_id": resolved_id,
        }
    except FloodWaitError as e:
        await _set_rate_gate(str(user.id), e.seconds)
        wait_hours = e.seconds // 3600
        wait_minutes = (e.seconds % 3600) // 60
        if wait_hours > 0:
            wait_str = f"{wait_hours}h {wait_minutes}m"
        else:
            wait_str = f"{wait_minutes}m"
        raise RuntimeError(
            f"Telegram rate limit: please wait {wait_str} before sending messages.",
            e.seconds,
        ) from e
    finally:
        await client.disconnect()


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
    try:
        result = await client.send_code_request(phone)
        phone_code_hash: str = result.phone_code_hash

        # Persist interim session so the verify step can reuse it.
        user.telegram_session = client.session.save()
        await db.flush()

        await client.disconnect()
        return phone_code_hash
    except Exception:
        await client.disconnect()
        raise


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
        logger.exception("Failed to fetch Telegram username for user %s", user.id)
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
        logger.exception("Failed to fetch Telegram username after 2FA for user %s", user.id)
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


async def _find_contact_by_telegram_user_id(
    tg_user_id: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Locate a Contact belonging to *user_id* whose telegram_user_id matches."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.telegram_user_id == tg_user_id,
        ).limit(1)
    )
    return result.scalar_one_or_none()


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


async def collect_dialog_ids(user: User) -> list[dict[str, Any]]:
    """Collect all DM dialog entity info without fetching messages.

    Returns a list of dicts: ``[{"entity_id": int, "username": str|None}, ...]``
    Filters out bots and non-user dialogs (channels, groups).
    Typically completes in <60s even for 1000+ dialogs.
    """
    if not user.telegram_session:
        return []

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    dialogs: list[dict[str, Any]] = []
    try:
        if not await client.is_user_authorized():
            return []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, TelegramUser):
                continue
            if getattr(entity, "bot", False):
                continue
            dialogs.append({
                "entity_id": entity.id,
                "username": getattr(entity, "username", None),
                "first_name": getattr(entity, "first_name", None) or "",
                "last_name": getattr(entity, "last_name", None) or "",
                "phone": getattr(entity, "phone", None),
            })
    finally:
        await client.disconnect()

    logger.info("collect_dialog_ids: found %d user dialogs for user %s.", len(dialogs), user.id)
    return dialogs


async def sync_telegram_chats(user: User, db: AsyncSession, *, max_dialogs: int = 0) -> int:
    """
    Sync Telegram DM conversations for *user* as Interaction records.

    Args:
        max_dialogs: If >0, stop after processing this many dialogs (for
            incremental syncs). 0 means no limit (full sync).

    For each dialog:
    - Fetches the last MAX_MESSAGES messages.
    - Matches the counterpart to a Contact by telegram_username.
    - Creates Interaction records (platform="telegram").
    - Updates contact.last_interaction_at when appropriate.

    Returns a dict with new_interactions, new_contacts, affected_contact_ids.
    """
    if not user.telegram_session:
        logger.warning("User %s has no telegram_session; skipping Telegram sync.", user.id)
        return {"new_interactions": 0, "new_contacts": 0, "affected_contact_ids": []}

    # Bail early if rate-gated
    gate_ttl = await _check_rate_gate(str(user.id))
    if gate_ttl:
        logger.info("sync_telegram_chats: user %s is rate-gated (%ds remaining), skipping.", user.id, gate_ttl)
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
    dialogs_skipped = 0
    created_contacts = 0
    affected_contact_ids: set[str] = set()
    avatar_queue: list[tuple[object, Contact]] = []  # (entity, contact) pairs needing avatars

    try:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, TelegramUser):
                continue
            if getattr(entity, "bot", False):
                continue
            dialogs_checked += 1

            if max_dialogs > 0 and dialogs_checked > max_dialogs:
                logger.info("sync_telegram_chats: hit max_dialogs=%d, stopping.", max_dialogs)
                break

            # Resolve the contact in our database
            contact: Contact | None = None
            # Check telegram_user_id first (survives username changes and parallel sync)
            contact = await _find_contact_by_telegram_user_id(str(entity.id), user.id, db)
            if contact is None and entity.username:
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

            # Queue avatar download for after main sync loop
            if not contact.avatar_url:
                avatar_queue.append((entity, contact))

            # Skip dialog if the latest message is already in our DB
            last_msg = dialog.message
            if last_msg and contact:
                latest_ref = f"{entity.id}:{last_msg.id}"
                existing = await db.execute(
                    select(Interaction.id).where(
                        Interaction.raw_reference_id == latest_ref,
                        Interaction.user_id == user.id,
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    dialogs_skipped += 1
                    continue  # No new messages, skip this dialog entirely

            # Pre-load existing raw_reference_ids for this contact to avoid per-message SELECTs
            existing_result = await db.execute(
                select(Interaction.raw_reference_id)
                .where(Interaction.contact_id == contact.id, Interaction.raw_reference_id.isnot(None))
            )
            existing_refs: set[str] = set(existing_result.scalars().all())

            # Iterate recent messages for this dialog
            try:
                async for message in client.iter_messages(entity, limit=MAX_MESSAGES):
                    if message.message is None:
                        continue  # skip service messages

                    direction = "outbound" if message.sender_id == my_id else "inbound"
                    message_id = f"{entity.id}:{message.id}"

                    if message_id in existing_refs:
                        continue  # already stored, skip DB write

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
            except FloodWaitError as e:
                await _set_rate_gate(str(user.id), e.seconds)
                logger.warning("FloodWaitError in sync_telegram_chats: waiting %d seconds", e.seconds)
                raise

            # Throttle between dialogs to avoid Telegram rate limits
            await asyncio.sleep(random.uniform(0.5, 1.0))

        # Download avatars after all dialogs are processed
        for av_entity, av_contact in avatar_queue:
            try:
                avatar_path = await _download_avatar(client, av_entity, av_contact.id)
                if avatar_path:
                    av_contact.avatar_url = avatar_path
            except Exception:
                logger.debug("Avatar download failed for contact %s", av_contact.id)

    finally:
        await client.disconnect()

    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to flush Telegram interactions for user %s.", user.id)
        await db.rollback()
        return {"new_interactions": 0, "new_contacts": 0, "affected_contact_ids": []}

    logger.info(
        "Telegram sync for user %s: %d new interaction(s), %d new contacts, %d dialogs checked, %d skipped (unchanged).",
        user.id, new_count, created_contacts, dialogs_checked, dialogs_skipped,
    )
    return {
        "new_interactions": new_count,
        "new_contacts": created_contacts,
        "affected_contact_ids": list(affected_contact_ids),
    }


async def sync_telegram_chats_batch(
    user: User, entity_ids: list[int], db: AsyncSession
) -> dict[str, Any]:
    """Sync Telegram DMs for a specific batch of entity IDs.

    This processes a fixed list of dialogs (by numeric Telegram user ID),
    used for chunked initial sync. Same logic as sync_telegram_chats inner
    loop but only for the given entities.

    Returns ``{"new_interactions": N, "new_contacts": N, "affected_contact_ids": [...]}``.
    """
    if not user.telegram_session or not entity_ids:
        return {"new_interactions": 0, "new_contacts": 0, "affected_contact_ids": []}

    gate_ttl = await _check_rate_gate(str(user.id))
    if gate_ttl:
        logger.info("sync_telegram_chats_batch: user %s is rate-gated (%ds remaining), skipping.", user.id, gate_ttl)
        return {"new_interactions": 0, "new_contacts": 0, "affected_contact_ids": []}

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session expired.")

    me = await client.get_me()
    my_id: int = me.id

    new_count = 0
    created_contacts = 0
    affected_contact_ids: set[str] = set()
    avatar_queue: list[tuple[object, Contact]] = []

    try:
        for eid in entity_ids:
            try:
                entity = await client.get_input_entity(eid)
            except Exception:
                logger.debug("sync_telegram_chats_batch: could not resolve entity %d", eid)
                continue

            # Resolve contact
            contact: Contact | None = await _find_contact_by_telegram_user_id(str(eid), user.id, db)
            if contact is None:
                # Try to get full entity for name/username
                try:
                    full_entity = await client.get_entity(eid)
                    username = getattr(full_entity, "username", None)
                    first_name = getattr(full_entity, "first_name", None) or ""
                    last_name = getattr(full_entity, "last_name", None) or ""
                    phone = getattr(full_entity, "phone", None)
                except Exception:
                    logger.debug("sync_telegram_chats_batch: failed to fetch full entity for %d, using defaults", eid)
                    username, first_name, last_name, phone = None, str(eid), "", None

                if username:
                    contact = await _find_contact_by_username(username, user.id, db)
                if contact is None and phone:
                    contact = await _find_contact_by_phone(phone, user.id, db)

                if contact is None:
                    full = f"{first_name} {last_name}".strip() or username or str(eid)
                    contact = Contact(
                        user_id=user.id,
                        given_name=first_name or username or str(eid),
                        family_name=last_name or None,
                        full_name=full,
                        telegram_username=(username or "").lower().lstrip("@") or None,
                        telegram_user_id=str(eid),
                        phones=[phone] if phone else [],
                        source="telegram",
                    )
                    db.add(contact)
                    await db.flush()
                    created_contacts += 1
                else:
                    if not contact.telegram_user_id:
                        contact.telegram_user_id = str(eid)

            if not contact.avatar_url:
                avatar_queue.append((entity, contact))

            # Skip entity if latest message already synced
            try:
                latest_msgs = await client.get_messages(entity, limit=1)
                if latest_msgs and contact:
                    top_msg = latest_msgs[0]
                    if top_msg and top_msg.id:
                        latest_ref = f"{eid}:{top_msg.id}"
                        existing = await db.execute(
                            select(Interaction.id).where(
                                Interaction.raw_reference_id == latest_ref,
                                Interaction.user_id == user.id,
                            ).limit(1)
                        )
                        if existing.scalar_one_or_none():
                            continue
            except Exception:
                logger.debug("sync_telegram_chats_batch: skip-check failed for entity %d, falling through to full sync", eid)

            # Pre-load existing raw_reference_ids for this contact to avoid per-message SELECTs
            existing_result = await db.execute(
                select(Interaction.raw_reference_id)
                .where(Interaction.contact_id == contact.id, Interaction.raw_reference_id.isnot(None))
            )
            existing_refs: set[str] = set(existing_result.scalars().all())

            try:
                async for message in client.iter_messages(entity, limit=MAX_MESSAGES):
                    if message.message is None:
                        continue
                    direction = "outbound" if message.sender_id == my_id else "inbound"
                    message_id = f"{eid}:{message.id}"

                    if message_id in existing_refs:
                        continue  # already stored, skip DB write

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

                    if contact.last_interaction_at is None or contact.last_interaction_at < occurred_at:
                        contact.last_interaction_at = occurred_at
            except FloodWaitError as e:
                await _set_rate_gate(str(user.id), e.seconds)
                logger.warning("FloodWaitError in sync_telegram_chats_batch: waiting %d seconds", e.seconds)
                raise

            await asyncio.sleep(random.uniform(0.5, 1.0))

        # Batch avatar downloads
        for av_entity, av_contact in avatar_queue:
            try:
                avatar_path = await _download_avatar(client, av_entity, av_contact.id)
                if avatar_path:
                    av_contact.avatar_url = avatar_path
            except Exception:
                logger.debug("Avatar download failed for contact %s", av_contact.id)

    finally:
        await client.disconnect()

    await db.flush()
    logger.info(
        "sync_telegram_chats_batch: user %s — %d entities, %d new interactions, %d new contacts.",
        user.id, len(entity_ids), new_count, created_contacts,
    )
    return {
        "new_interactions": new_count,
        "new_contacts": created_contacts,
        "affected_contact_ids": list(affected_contact_ids),
    }


async def sync_telegram_contact_messages(
    user: User, contact: Contact, db: AsyncSession
) -> dict[str, Any]:
    """Sync Telegram DMs for a single *contact*.

    Connects via MTProto, resolves entity by telegram_user_id (fallback to
    username), fetches last MAX_MESSAGES messages, deduplicates via
    _upsert_interaction, and updates last_interaction_at.

    Returns ``{"new_interactions": N}``.
    """
    if not user.telegram_session:
        return {"new_interactions": 0, "skipped": True, "reason": "telegram_not_connected"}

    tg_user_id = contact.telegram_user_id
    tg_username = (contact.telegram_username or "").lstrip("@").strip()
    if not tg_user_id and not tg_username:
        return {"new_interactions": 0, "skipped": True, "reason": "no_telegram_identifier"}

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    try:
        if not await client.is_user_authorized():
            return {"new_interactions": 0, "skipped": True, "reason": "session_expired"}

        me = await client.get_me()
        my_id: int = me.id

        # Resolve entity: prefer numeric ID to avoid ResolveUsernameRequest
        if tg_user_id:
            entity = await client.get_input_entity(int(tg_user_id))
        else:
            entity = await client.get_input_entity(tg_username)

        # Extract numeric ID from resolved entity and normalise entity_id
        resolved_id = getattr(entity, "id", None) or getattr(entity, "user_id", None)
        entity_id = tg_user_id or (str(resolved_id) if resolved_id else tg_username)

        # Backfill telegram_user_id if it was missing
        if not contact.telegram_user_id and resolved_id:
            contact.telegram_user_id = str(resolved_id)

        new_count = 0
        try:
            async for message in client.iter_messages(entity, limit=MAX_MESSAGES):
                if message.message is None:
                    continue

                direction = "outbound" if message.sender_id == my_id else "inbound"
                message_id = f"{entity_id}:{message.id}"
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

                if contact.last_interaction_at is None or contact.last_interaction_at < occurred_at:
                    contact.last_interaction_at = occurred_at
        except FloodWaitError as e:
            await _set_rate_gate(str(user.id), e.seconds)
            logger.warning("FloodWaitError in sync_telegram_contact_messages: waiting %d seconds", e.seconds)
            await asyncio.sleep(e.seconds + 5)

        await db.flush()
    finally:
        await client.disconnect()

    logger.info(
        "sync_telegram_contact_messages: contact %s — %d new interaction(s).",
        contact.id, new_count,
    )
    return {"new_interactions": new_count}


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

    gate_ttl = await _check_rate_gate(str(user.id))
    if gate_ttl:
        logger.info("sync_telegram_group_members: user %s is rate-gated (%ds remaining), skipping.", user.id, gate_ttl)
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

    # Track which groups each contact was found in (contact_id → [group_info])
    contact_groups: dict[uuid.UUID, list[dict[str, Any]]] = {}

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
            group_username = getattr(entity, "username", None)
            group_info = {
                "id": entity.id,
                "title": group_title,
                "username": group_username,
                "link": f"https://t.me/{group_username}" if group_username else None,
                "participants_count": getattr(entity, "participants_count", None),
            }
            logger.debug("Scanning group '%s' (id=%s) for members.", group_title, entity.id)

            try:
                participants = await client.get_participants(entity, limit=MAX_MEMBERS_PER_GROUP)
            except FloodWaitError as e:
                await _set_rate_gate(str(user.id), e.seconds)
                logger.warning("FloodWaitError in sync_telegram_group_members: waiting %d seconds", e.seconds)
                await asyncio.sleep(e.seconds + 5)
                try:
                    participants = await client.get_participants(entity, limit=MAX_MEMBERS_PER_GROUP)
                except Exception:
                    logger.debug(
                        "Cannot fetch participants for group '%s' (id=%s) after FloodWait, skipping.",
                        group_title, entity.id,
                    )
                    continue
            except Exception:
                logger.debug(
                    "Cannot fetch participants for group '%s' (id=%s), skipping.",
                    group_title, entity.id,
                )
                await asyncio.sleep(random.uniform(0.5, 1.0))
                continue

            # Throttle between groups to avoid Telegram rate limits
            await asyncio.sleep(random.uniform(0.5, 1.0))

            for member in participants:
                if not isinstance(member, TelegramUser):
                    continue
                if getattr(member, "bot", False):
                    continue
                if member.id == my_id:
                    continue

                # Try to find existing contact
                contact: Contact | None = None
                # Check telegram_user_id first (survives username changes and parallel sync)
                contact = await _find_contact_by_telegram_user_id(str(member.id), user.id, db)
                if contact is None and member.username:
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
                        pass  # skip tagging — already has direct conversations
                    else:
                        current_tags = list(contact.tags or [])
                        if tag_label not in current_tags:
                            current_tags.append(tag_label)
                            contact.tags = current_tags
                            updated_contacts += 1

                # Record which group this contact was found in
                if contact.id not in contact_groups:
                    contact_groups[contact.id] = []
                # Avoid duplicate group entries (contact seen twice in same group)
                if not any(g["id"] == group_info["id"] for g in contact_groups[contact.id]):
                    contact_groups[contact.id].append(group_info)

                # Download avatar if missing
                if not contact.avatar_url:
                    avatar_path = await _download_avatar(client, member, contact.id)
                    if avatar_path:
                        contact.avatar_url = avatar_path

        # Persist common groups for all contacts found during sync
        now = datetime.now(UTC)
        for cid, groups in contact_groups.items():
            contact_result = await db.execute(
                select(Contact).where(Contact.id == cid)
            )
            c = contact_result.scalar_one_or_none()
            if c is not None:
                # Merge with any existing groups (from previous syncs or API calls)
                existing = list(c.telegram_common_groups or [])
                existing_ids = {g["id"] for g in existing}
                for g in groups:
                    if g["id"] not in existing_ids:
                        existing.append(g)
                c.telegram_common_groups = existing
                c.telegram_groups_fetched_at = now

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

    resolved_user_id: str | None = None

    try:
        # Resolve target — prefer cached numeric ID to avoid rate-limited ResolveUsernameRequest
        if telegram_user_id:
            target = await client.get_input_entity(int(telegram_user_id))
        elif telegram_username:
            target = await client.get_input_entity(telegram_username)
            # Cache the resolved numeric ID for future calls
            resolved_user_id = str(getattr(target, "user_id", None) or "")
        else:
            return []
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
        return groups, resolved_user_id
    except Exception as exc:
        logger.exception(
            "fetch_common_groups: failed for user %s / @%s: %s",
            user.id, telegram_username, exc,
        )
        return [], None
    finally:
        await client.disconnect()


async def sync_telegram_bios(
    user: User, db: AsyncSession, *, exclude_2nd_tier: bool = False, stale_days: int = 7,
) -> dict[str, int]:
    """Fetch and store Telegram bios for contacts with a telegram username/ID.

    Creates notifications for bio changes. Returns counts.

    Args:
        exclude_2nd_tier: If True, skip contacts tagged "2nd tier".
        stale_days: Only recheck contacts whose bio was last checked more than this many days ago.
    """
    from app.models.notification import Notification
    from telethon.tl.functions.users import GetFullUserRequest

    if not user.telegram_session:
        return {"bios_updated": 0, "bio_changes": 0}

    gate_ttl = await _check_rate_gate(str(user.id))
    if gate_ttl:
        logger.info("sync_telegram_bios: user %s is rate-gated (%ds remaining), skipping.", user.id, gate_ttl)
        return {"bios_updated": 0, "bio_changes": 0}

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    bio_stale_cutoff = datetime.now(UTC) - timedelta(days=stale_days)
    filters = [
        Contact.user_id == user.id,
        or_(
            Contact.telegram_username.isnot(None),
            Contact.telegram_user_id.isnot(None),
        ),
        or_(
            Contact.telegram_bio_checked_at.is_(None),
            Contact.telegram_bio_checked_at < bio_stale_cutoff,
        ),
    ]
    if exclude_2nd_tier:
        filters.append(or_(Contact.tags.is_(None), ~Contact.tags.contains(["2nd tier"])))

    result = await db.execute(
        select(Contact).where(*filters).order_by(
            Contact.avatar_url.isnot(None).asc(),
        ).limit(MAX_BIO_SYNC_CONTACTS)
    )
    contacts: list[Contact] = list(result.scalars().all())

    updated = 0
    bio_changes = 0

    try:
        for contact in contacts:
            username = (contact.telegram_username or "").lstrip("@").strip()
            # Need at least a username or a numeric ID to look up the contact
            if not username and not contact.telegram_user_id:
                continue

            try:
                # Use cached numeric ID to avoid rate-limited ResolveUsernameRequest
                if contact.telegram_user_id:
                    input_user = await client.get_input_entity(int(contact.telegram_user_id))
                else:
                    input_user = await client.get_input_entity(username)
                full = await client(GetFullUserRequest(input_user))
                current_bio = getattr(full.full_user, "about", None) or ""
            except FloodWaitError as e:
                await _set_rate_gate(str(user.id), e.seconds)
                logger.warning("FloodWaitError in sync_telegram_bios: waiting %d seconds", e.seconds)
                contact.telegram_bio_checked_at = datetime.now(UTC)
                await asyncio.sleep(e.seconds + 5)
                continue
            except RPCError:
                logger.debug("sync_telegram_bios: Telegram RPC error fetching bio for @%s", username)
                contact.telegram_bio_checked_at = datetime.now(UTC)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                continue
            except Exception:
                logger.exception("sync_telegram_bios: unexpected error fetching bio for contact %s", contact.id)
                contact.telegram_bio_checked_at = datetime.now(UTC)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                continue

            # Throttle between Telegram API calls to avoid rate limits
            await asyncio.sleep(random.uniform(0.5, 1.0))

            # Mark bio as checked regardless of whether it changed
            contact.telegram_bio_checked_at = datetime.now(UTC)

            # Download avatar if missing
            if not contact.avatar_url:
                avatar_path = await _download_avatar(client, input_user, contact.id)
                if avatar_path:
                    contact.avatar_url = avatar_path

            # Extract birthday if available and not already set
            if not contact.birthday:
                bday = getattr(full.full_user, "birthday", None)
                if bday:
                    day = getattr(bday, "day", None)
                    month = getattr(bday, "month", None)
                    year = getattr(bday, "year", None)
                    if day and month:
                        contact.birthday = (
                            f"{year}-{month:02d}-{day:02d}" if year
                            else f"{month:02d}-{day:02d}"
                        )

            # Extract Twitter handle from bio if not already set
            if not contact.twitter_handle and current_bio:
                twitter_handle = _extract_twitter_handle(current_bio)
                if twitter_handle:
                    contact.twitter_handle = twitter_handle

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
                db.add(Interaction(
                    contact_id=contact.id,
                    user_id=user.id,
                    platform="telegram",
                    direction="event",
                    content_preview=f"Bio updated: {current_bio[:500]}",
                    raw_reference_id=f"bio_change:telegram:{contact.id}:{datetime.now(UTC).isoformat()}",
                    occurred_at=datetime.now(UTC),
                ))
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
