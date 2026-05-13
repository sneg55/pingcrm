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



# Sync functions live in companion modules to keep this file under the
# 500-line limit. Re-export for backwards compatibility.
from app.integrations.telegram_chat_sync import sync_telegram_chats  # noqa: E402,F401
from app.integrations.telegram_chat_batch import (  # noqa: E402,F401
    sync_telegram_chats_batch,
    sync_telegram_contact_messages,
)
from app.integrations.telegram_bio_sync import (  # noqa: E402,F401
    fetch_common_groups,
    match_telegram_contacts,
    sync_telegram_bios,
)
