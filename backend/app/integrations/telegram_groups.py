"""Telegram group member sync — discovers 2nd Tier contacts from shared groups."""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel, Chat, User as TelegramUser

from app.integrations.telegram_helpers import (
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
from app.models.interaction import Interaction
from app.models.user import User

logger = logging.getLogger(__name__)

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

    if not user.sync_2nd_tier:
        logger.info("User %s has sync_2nd_tier=False; skipping group member sync.", user.id)
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
                contact = await _find_contact_by_telegram_user_id(str(member.id), user.id, db)
                if contact is None and member.username:
                    contact = await _find_contact_by_username(member.username, user.id, db)
                if contact is None and member.phone:
                    contact = await _find_contact_by_phone(member.phone, user.id, db)

                tg_username = (member.username or "").lower().lstrip("@") or None
                tg_user_id = str(member.id)

                if contact is None:
                    from app.services.contact_resolver import (
                        find_or_create_contact_by_telegram_user_id,
                    )
                    first_name = getattr(member, "first_name", None) or ""
                    last_name = getattr(member, "last_name", None) or ""
                    full = f"{first_name} {last_name}".strip() or member.username or tg_user_id
                    contact, created = await find_or_create_contact_by_telegram_user_id(
                        db, user.id, tg_user_id,
                        defaults=dict(
                            given_name=first_name or member.username or tg_user_id,
                            family_name=last_name or None,
                            full_name=full,
                            telegram_username=member.username or None,
                            phones=[member.phone] if member.phone else [],
                            source="telegram",
                            tags=[tag_label],
                        ),
                    )
                    if created:
                        new_contacts += 1
                else:
                    # Backfill telegram info if missing
                    if tg_username and not contact.telegram_username:
                        contact.telegram_username = tg_username
                    if not contact.telegram_user_id:
                        contact.telegram_user_id = tg_user_id

                    # Tag as "2nd Tier" only if no direct interactions;
                    # remove the tag if interactions have appeared since last sync
                    has_interactions = await db.execute(
                        select(Interaction.id).where(
                            Interaction.contact_id == contact.id,
                            Interaction.user_id == user.id,
                        ).limit(1)
                    )
                    if has_interactions.scalar_one_or_none() is not None:
                        current_tags = list(contact.tags or [])
                        if tag_label in current_tags:
                            current_tags.remove(tag_label)
                            contact.tags = current_tags
                            updated_contacts += 1
                    else:
                        current_tags = list(contact.tags or [])
                        if tag_label not in current_tags:
                            current_tags.append(tag_label)
                            contact.tags = current_tags
                            updated_contacts += 1

                # Record which group this contact was found in
                if contact.id not in contact_groups:
                    contact_groups[contact.id] = []
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
