"""Telegram chat sync: dialog scan + per-contact + batch sync.

Split from telegram.py to keep file under the 500-line limit. Public callers
import these via app.integrations.telegram for backwards compatibility.
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import cast, func, Integer as SAInteger, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import MessageActionPhoneCall, User as TelegramUser

from app.integrations.telegram_helpers import (
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
)
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_MESSAGES = 50  # messages fetched per dialog per sync run


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
    # Tracks per-contact the latest interaction occurred_at observed in this
    # sync. Passed to dismiss_suggestions_for_contacts so a backfilled
    # historical message can't kill a freshly-created suggestion.
    affected_max_occurred_at: dict[str, datetime] = {}
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
                # Auto-create contact from Telegram entity (race-safe: serializes
                # against concurrent telegram syncs on the same user_id+telegram_user_id).
                from app.services.contact_resolver import (
                    find_or_create_contact_by_telegram_user_id,
                )
                first_name = getattr(entity, "first_name", None) or ""
                last_name = getattr(entity, "last_name", None) or ""
                full = f"{first_name} {last_name}".strip() or entity.username or str(entity.id)
                contact, created = await find_or_create_contact_by_telegram_user_id(
                    db, user.id, str(entity.id),
                    defaults=dict(
                        given_name=first_name or entity.username or str(entity.id),
                        family_name=last_name or None,
                        full_name=full,
                        telegram_username=entity.username or None,
                        phones=[entity.phone] if entity.phone else [],
                        source="telegram",
                    ),
                )
                if created:
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
                                    cid_str = str(contact.id)
                                    prev = affected_max_occurred_at.get(cid_str)
                                    if prev is None or prev < occurred_at:
                                        affected_max_occurred_at[cid_str] = occurred_at
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
                        cid_str = str(contact.id)
                        prev = affected_max_occurred_at.get(cid_str)
                        if prev is None or prev < occurred_at:
                            affected_max_occurred_at[cid_str] = occurred_at

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
        "affected_contact_ids": list(affected_max_occurred_at.keys()),
        "affected_contact_max_occurred_at": {
            cid: ts.isoformat() for cid, ts in affected_max_occurred_at.items()
        },
    }

