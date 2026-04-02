"""Telegram MTProto integration using Telethon."""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.errors import FloodWaitError, RPCError, SessionPasswordNeededError
from telethon.tl.types import Channel, Chat, InputPeerUser, MessageActionPhoneCall, User as TelegramUser

from app.integrations.telegram_helpers import (
    _extract_twitter_handle,
    _find_contact_by_phone,
    _find_contact_by_telegram_user_id,
    _find_contact_by_username,
    _upsert_interaction,
)
from app.integrations.telegram_transport import (
    _check_rate_gate,
    _download_avatar,
    _ensure_connected,
    _make_client,
    _set_rate_gate,
    ensure_connected,
    make_client,
)
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_MESSAGES = 50  # messages fetched per dialog per sync run
MAX_BIO_SYNC_CONTACTS = 100  # max contacts fetched per bio sync run


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
        logger.warning("connect_telegram: error during send_code_request for user %s", user.id, exc_info=True)
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
        logger.warning("verify_telegram: sign_in failed for user %s", user.id, exc_info=True)
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
        logger.warning("verify_telegram_2fa: sign_in failed for user %s", user.id, exc_info=True)
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

            # Extract read receipt cursor — highest msg ID the recipient has read
            read_outbox_max_id: int | None = getattr(
                getattr(dialog, "dialog", None), "read_outbox_max_id", None
            )

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

            # Store read receipt cursor and retroactively update existing interactions
            if read_outbox_max_id is not None and contact:
                contact.telegram_read_outbox_max_id = read_outbox_max_id
                # Bulk-update existing outbound interactions that are now read
                from sqlalchemy import update, cast, Integer as SAInteger
                update_result = await db.execute(
                    update(Interaction)
                    .where(
                        Interaction.contact_id == contact.id,
                        Interaction.user_id == user.id,
                        Interaction.platform == "telegram",
                        Interaction.direction == "outbound",
                        Interaction.is_read_by_recipient.is_not(True),
                        Interaction.raw_reference_id.isnot(None),
                        cast(func.split_part(Interaction.raw_reference_id, ":", 2), SAInteger) <= read_outbox_max_id,
                    )
                    .values(is_read_by_recipient=True)
                )
                if update_result.rowcount > 0:
                    logger.info(
                        "read_receipts: marked %d interaction(s) as read for contact %s (read_outbox_max_id=%d)",
                        update_result.rowcount, contact.id, read_outbox_max_id,
                        extra={"provider": "telegram", "contact_id": str(contact.id)},
                    )
            elif contact:
                logger.debug(
                    "read_receipts: no read_outbox_max_id for contact %s (dialog.dialog=%r)",
                    contact.id, getattr(dialog, "dialog", None),
                    extra={"provider": "telegram", "contact_id": str(contact.id)},
                )

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
                        # Check for phone/video calls
                        if hasattr(message, 'action') and isinstance(message.action, MessageActionPhoneCall):
                            direction = "outbound" if message.out else "inbound"
                            is_video = getattr(message.action, 'video', False)
                            call_type = "Video call" if is_video else "Phone call"
                            duration = getattr(message.action, 'duration', None)
                            preview = f"{call_type}" + (f" ({duration}s)" if duration else "")
                            message_id = f"{entity.id}:{message.id}"
                            if message_id not in existing_refs:
                                occurred_at = message.date.replace(tzinfo=UTC) if message.date.tzinfo is None else message.date
                                _interaction, is_new = await _upsert_interaction(
                                    contact=contact,
                                    user_id=user.id,
                                    message_id=message_id,
                                    direction=direction,
                                    content_preview=preview,
                                    occurred_at=occurred_at,
                                    db=db,
                                )
                                if is_new:
                                    new_count += 1
                                    affected_contact_ids.add(str(contact.id))
                                if (
                                    contact.last_interaction_at is None
                                    or contact.last_interaction_at < occurred_at
                                ):
                                    contact.last_interaction_at = occurred_at
                        continue  # skip other service messages

                    direction = "outbound" if message.sender_id == my_id else "inbound"
                    message_id = f"{entity.id}:{message.id}"

                    if message_id in existing_refs:
                        continue  # already stored, skip DB write

                    occurred_at = message.date.replace(tzinfo=UTC) if message.date.tzinfo is None else message.date

                    # Determine read status for outbound messages
                    _read = None
                    if direction == "outbound" and read_outbox_max_id is not None:
                        _read = message.id <= read_outbox_max_id

                    _interaction, is_new = await _upsert_interaction(
                        contact=contact,
                        user_id=user.id,
                        message_id=message_id,
                        direction=direction,
                        content_preview=message.message,
                        occurred_at=occurred_at,
                        db=db,
                        is_read_by_recipient=_read,
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
                        # Check for phone/video calls
                        if hasattr(message, 'action') and isinstance(message.action, MessageActionPhoneCall):
                            direction = "outbound" if message.out else "inbound"
                            is_video = getattr(message.action, 'video', False)
                            call_type = "Video call" if is_video else "Phone call"
                            duration = getattr(message.action, 'duration', None)
                            preview = f"{call_type}" + (f" ({duration}s)" if duration else "")
                            message_id = f"{eid}:{message.id}"
                            if message_id not in existing_refs:
                                occurred_at = message.date.replace(tzinfo=UTC) if message.date.tzinfo is None else message.date
                                _interaction, is_new = await _upsert_interaction(
                                    contact=contact,
                                    user_id=user.id,
                                    message_id=message_id,
                                    direction=direction,
                                    content_preview=preview,
                                    occurred_at=occurred_at,
                                    db=db,
                                )
                                if is_new:
                                    new_count += 1
                                    affected_contact_ids.add(str(contact.id))
                                if contact.last_interaction_at is None or contact.last_interaction_at < occurred_at:
                                    contact.last_interaction_at = occurred_at
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


# Group member sync lives in telegram_groups.py
from app.integrations.telegram_groups import sync_telegram_group_members  # noqa: F401


async def fetch_common_groups(
    user: User, telegram_username: str | None = None, telegram_user_id: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return groups/channels in common between *user* and a target.

    The target can be identified by *telegram_username* or *telegram_user_id*.
    Returns a tuple of (groups_list, resolved_user_id).
    """
    if not user.telegram_session:
        return [], None
    if not telegram_username and not telegram_user_id:
        return [], None

    from telethon.tl.functions.messages import GetCommonChatsRequest

    client = _make_client(user.telegram_session)
    await _ensure_connected(client)

    resolved_user_id: str | None = None

    try:
        # Resolve target — prefer cached numeric ID to avoid rate-limited ResolveUsernameRequest
        if telegram_user_id:
            target = await client.get_input_entity(int(telegram_user_id))
        elif telegram_username:
            # get_entity does a full ResolveUsername — more reliable than
            # get_input_entity which may fail on usernames not in the
            # StringSession's entity cache.
            handle = telegram_username.lstrip("@")
            entity = await client.get_entity(handle)
            target = InputPeerUser(entity.id, entity.access_hash or 0)
            resolved_user_id = str(entity.id)
        else:
            return [], None
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
    except FloodWaitError as e:
        logger.warning(
            "fetch_common_groups: FloodWait %ds for user %s / @%s",
            e.seconds, user.id, telegram_username,
        )
        await _set_rate_gate(str(user.id), e.seconds)
        return [], None
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

            # Extract last seen status from user object
            from app.integrations.telegram_helpers import _extract_last_seen
            tg_user = full.users[0] if full.users else None
            last_seen = _extract_last_seen(tg_user) if tg_user else None
            if last_seen:
                contact.telegram_last_seen_at = last_seen

            # Extract birthday if available and not already set
            from app.services.sync_utils import sync_set_field
            if not contact.birthday:
                bday = getattr(full.full_user, "birthday", None)
                if bday:
                    day = getattr(bday, "day", None)
                    month = getattr(bday, "month", None)
                    year = getattr(bday, "year", None)
                    if day and month:
                        bday_str = (
                            f"{year}-{month:02d}-{day:02d}" if year
                            else f"{month:02d}-{day:02d}"
                        )
                        sync_set_field(contact, "birthday", bday_str)

            # Extract Twitter handle from bio if not already set
            if current_bio:
                twitter_handle = _extract_twitter_handle(current_bio)
                if twitter_handle:
                    sync_set_field(contact, "twitter_handle", twitter_handle)

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
