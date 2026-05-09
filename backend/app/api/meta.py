"""Meta (Facebook Messenger / Instagram DM) Chrome Extension push endpoint."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_extension_or_web_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.responses import Envelope, MetaBackfillItem, MetaPushResult
from app.services.sync_utils import sync_set_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class MetaProfilePush(BaseModel):
    platform_id: str
    name: str
    username: str | None = None
    avatar_url: str | None = None


class MetaReaction(BaseModel):
    reactor_id: str
    type: str


class MetaMessagePush(BaseModel):
    message_id: str
    conversation_id: str
    platform_id: str | None = None
    sender_name: str
    direction: str  # "inbound" | "outbound"
    content_preview: str | None = None
    timestamp: str  # ISO 8601
    reactions: list[MetaReaction] = []
    read_by: list[str] = []


class MetaPushRequest(BaseModel):
    platform: str  # "facebook" | "instagram"
    profiles: list[MetaProfilePush] = Field(default=[], max_length=50)
    messages: list[MetaMessagePush] = Field(default=[], max_length=500)


# ---------------------------------------------------------------------------
# Push endpoint
# ---------------------------------------------------------------------------


@router.post("/push", response_model=Envelope[MetaPushResult])
async def push_meta_data(
    body: MetaPushRequest,
    current_user: User = Depends(get_extension_or_web_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive profile and message data from the Meta Chrome Extension."""
    platform = body.platform  # "facebook" or "instagram"
    contacts_created = 0
    contacts_updated = 0
    interactions_created = 0
    interactions_skipped = 0
    contacts_with_new_interactions: set[uuid.UUID] = set()
    touched_contacts: list[Contact] = []

    # --- Pre-load all user contacts for in-memory matching ---
    all_contacts_result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id)
    )
    all_user_contacts = list(all_contacts_result.scalars().all())

    fb_id_map: dict[str, Contact] = {}
    ig_id_map: dict[str, Contact] = {}
    name_map: dict[str, Contact] = {}

    for c in all_user_contacts:
        if c.facebook_id:
            fb_id_map[c.facebook_id] = c
        if c.instagram_id:
            ig_id_map[c.instagram_id] = c
        if c.full_name:
            name_map[c.full_name.lower()] = c

    # --- Pre-load existing interaction refs for message dedup ---
    all_refs: list[str] = []
    for msg in body.messages:
        all_refs.append(f"{platform}:{msg.message_id}")
    existing_refs: set[str] = set()
    if all_refs:
        refs_result = await db.execute(
            select(Interaction.raw_reference_id).where(
                Interaction.user_id == current_user.id,
                Interaction.raw_reference_id.in_(all_refs),
            )
        )
        existing_refs = set(refs_result.scalars().all())

    # --- Profiles ---
    for profile in body.profiles:
        # Look up by platform-specific ID
        if platform == "instagram":
            contact = ig_id_map.get(profile.platform_id)
        else:
            contact = fb_id_map.get(profile.platform_id)

        if contact:
            # Update existing contact
            sync_set_field(contact, "full_name", profile.name)
            if platform == "facebook":
                contact.facebook_name = profile.name
                if not contact.facebook_id:
                    contact.facebook_id = profile.platform_id
                if profile.avatar_url:
                    contact.facebook_avatar_url = profile.avatar_url
            else:
                contact.instagram_username = profile.username
                if not contact.instagram_id:
                    contact.instagram_id = profile.platform_id
                if profile.avatar_url:
                    contact.instagram_avatar_url = profile.avatar_url
            contacts_updated += 1
        else:
            # Create new contact
            name_parts = (profile.name or "").split(None, 1)
            contact = Contact(
                user_id=current_user.id,
                full_name=profile.name,
                given_name=name_parts[0] if name_parts else None,
                family_name=name_parts[1] if len(name_parts) > 1 else None,
            )
            if platform == "facebook":
                contact.facebook_id = profile.platform_id
                contact.facebook_name = profile.name
                if profile.avatar_url:
                    contact.facebook_avatar_url = profile.avatar_url
            else:
                contact.instagram_id = profile.platform_id
                contact.instagram_username = profile.username
                if profile.avatar_url:
                    contact.instagram_avatar_url = profile.avatar_url
            db.add(contact)
            await db.flush()
            contacts_created += 1

            # Update in-memory maps
            if platform == "facebook":
                fb_id_map[profile.platform_id] = contact
            else:
                ig_id_map[profile.platform_id] = contact
            if contact.full_name:
                name_map[contact.full_name.lower()] = contact

        touched_contacts.append(contact)

    # --- Messages ---
    for msg in body.messages:
        raw_ref = f"{platform}:{msg.message_id}"

        # Check for duplicate using pre-loaded set
        if raw_ref in existing_refs:
            interactions_skipped += 1
            continue

        # Skip messages where we can't identify the sender
        if not msg.platform_id and not msg.sender_name:
            interactions_skipped += 1
            continue

        # Find contact using in-memory maps
        contact = None
        if msg.platform_id:
            if platform == "instagram":
                contact = ig_id_map.get(msg.platform_id)
            else:
                contact = fb_id_map.get(msg.platform_id)

        # Fall back to name matching (cross-platform)
        if not contact and msg.sender_name:
            contact = name_map.get(msg.sender_name.lower())
            if contact and msg.platform_id:
                # Backfill platform ID on matched contact
                if platform == "facebook" and not contact.facebook_id:
                    contact.facebook_id = msg.platform_id
                    fb_id_map[msg.platform_id] = contact
                elif platform == "instagram" and not contact.instagram_id:
                    contact.instagram_id = msg.platform_id
                    ig_id_map[msg.platform_id] = contact

        if not contact:
            # Auto-create contact stub
            name_parts = (msg.sender_name or "").split(None, 1)
            contact = Contact(
                user_id=current_user.id,
                full_name=msg.sender_name,
                given_name=name_parts[0] if name_parts else None,
                family_name=name_parts[1] if len(name_parts) > 1 else None,
            )
            if platform == "facebook":
                contact.facebook_id = msg.platform_id
            else:
                contact.instagram_id = msg.platform_id
            db.add(contact)
            await db.flush()
            contacts_created += 1

            # Update in-memory maps
            if msg.platform_id:
                if platform == "facebook":
                    fb_id_map[msg.platform_id] = contact
                else:
                    ig_id_map[msg.platform_id] = contact
            if contact.full_name:
                name_map[contact.full_name.lower()] = contact

        touched_contacts.append(contact)

        try:
            occurred_at = datetime.fromisoformat(msg.timestamp)
        except ValueError:
            occurred_at = datetime.now(UTC)

        # Build extra_data for reactions and read receipts
        extra_data: dict | None = None
        if msg.reactions or msg.read_by:
            extra_data = {}
            if msg.reactions:
                extra_data["reactions"] = [r.model_dump() for r in msg.reactions]
            if msg.read_by:
                extra_data["read_by"] = msg.read_by

        interaction = Interaction(
            contact_id=contact.id,
            user_id=current_user.id,
            platform=platform,
            direction=msg.direction if msg.direction in ("inbound", "outbound") else "inbound",
            content_preview=msg.content_preview[:500] if msg.content_preview else None,
            raw_reference_id=raw_ref,
            occurred_at=occurred_at,
            extra_data=extra_data,
        )
        db.add(interaction)
        interactions_created += 1
        contacts_with_new_interactions.add(contact.id)

        # Update last_interaction_at
        if not contact.last_interaction_at or occurred_at > contact.last_interaction_at:
            contact.last_interaction_at = occurred_at
        contact.interaction_count = (contact.interaction_count or 0) + 1

    # Auto-dismiss only when contact.last_interaction_at is on/after the
    # suggestion's created_at — prevents backfilled old Meta messages from
    # killing fresh suggestions.
    if contacts_with_new_interactions:
        from app.services.follow_up_dismissal import dismiss_outdated_pending_suggestions
        await dismiss_outdated_pending_suggestions(
            db, list(contacts_with_new_interactions),
        )

    await db.flush()

    # Set meta_connected flag on first push
    if not current_user.meta_connected:
        current_user.meta_connected = True
        await db.flush()

    # Record sync event
    if contacts_created + contacts_updated + interactions_created > 0:
        from app.services.sync_history import record_sync_start, record_sync_complete
        sync_event = await record_sync_start(current_user.id, platform, "webhook", db)
        await record_sync_complete(
            sync_event,
            records_created=contacts_created + interactions_created,
            records_updated=contacts_updated,
            details={
                "contacts_created": contacts_created,
                "contacts_updated": contacts_updated,
                "interactions_created": interactions_created,
                "interactions_skipped": interactions_skipped,
            },
            db=db,
        )
        await db.flush()

    # Auto-merge deterministic duplicates after new contacts created
    if contacts_created > 0:
        try:
            from app.services.identity_resolution import find_deterministic_matches
            merged = await find_deterministic_matches(current_user.id, db)
            if merged:
                logger.info(
                    "meta push: auto-merged %d duplicate(s) for user %s",
                    len(merged),
                    current_user.id,
                )
        except Exception:
            logger.warning(
                "meta push: auto-merge failed for user %s",
                current_user.id,
                exc_info=True,
            )
        await db.flush()

    # Collect contacts that need backfill
    seen_ids: set[uuid.UUID] = set()
    backfill_needed: list[MetaBackfillItem] = []

    for contact in touched_contacts:
        if contact.id in seen_ids:
            continue
        seen_ids.add(contact.id)
        pid = contact.facebook_id if platform == "facebook" else contact.instagram_id
        if pid and not contact.avatar_url:
            backfill_needed.append(
                MetaBackfillItem(
                    contact_id=str(contact.id),
                    platform_id=pid,
                    platform=platform,
                )
            )

    return {
        "data": MetaPushResult(
            contacts_created=contacts_created,
            contacts_updated=contacts_updated,
            interactions_created=interactions_created,
            interactions_skipped=interactions_skipped,
            backfill_needed=backfill_needed,
        ),
        "error": None,
        "meta": None,
    }
