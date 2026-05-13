"""Telegram bio sync, common groups, and contact matching.

Split from telegram.py. Public callers import via app.integrations.telegram.
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import Channel, Chat, InputPeerUser, User as TelegramUser

from app.integrations.telegram_helpers import (
    _extract_twitter_handle,
    _find_contact_by_phone,
    _find_contact_by_telegram_user_id,
    _find_contact_by_username,
)
from app.integrations.telegram_transport import (
    _check_rate_gate,
    _download_avatar,
    _ensure_connected,
    _make_client,
    _set_rate_gate,
)
from app.models.contact import Contact
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_BIO_SYNC_CONTACTS = 100


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

    try:
        client = _make_client(user.telegram_session)
    except ValueError:
        logger.warning(
            "fetch_common_groups: StringSession decode failed",
            extra={"provider": "telegram", "user_id": str(user.id)},
        )
        return [], None
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
