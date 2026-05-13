"""Telegram batch + contact-specific message sync.

Split from telegram.py. Public callers import via app.integrations.telegram.
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime
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

MAX_MESSAGES = 50


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
    affected_max_occurred_at: dict[str, datetime] = {}
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
                    from app.services.contact_resolver import (
                        find_or_create_contact_by_telegram_user_id,
                    )
                    full = f"{first_name} {last_name}".strip() or username or str(eid)
                    contact, created = await find_or_create_contact_by_telegram_user_id(
                        db, user.id, str(eid),
                        defaults=dict(
                            given_name=first_name or username or str(eid),
                            family_name=last_name or None,
                            full_name=full,
                            telegram_username=username or None,
                            phones=[phone] if phone else [],
                            source="telegram",
                        ),
                    )
                    if created:
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
                                    cid_str = str(contact.id)
                                    prev = affected_max_occurred_at.get(cid_str)
                                    if prev is None or prev < occurred_at:
                                        affected_max_occurred_at[cid_str] = occurred_at
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
                        cid_str = str(contact.id)
                        prev = affected_max_occurred_at.get(cid_str)
                        if prev is None or prev < occurred_at:
                            affected_max_occurred_at[cid_str] = occurred_at

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
        "affected_contact_ids": list(affected_max_occurred_at.keys()),
        "affected_contact_max_occurred_at": {
            cid: ts.isoformat() for cid, ts in affected_max_occurred_at.items()
        },
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


