"""LinkedIn Chrome Extension push endpoint."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, UTC

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_extension_or_web_user
from app.core.database import get_db
from app.integrations.linkedin import download_linkedin_avatar
from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.responses import BackfillItem, Envelope, LinkedInPushResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/linkedin", tags=["linkedin"])


def _has_local_avatar(avatar_url: str | None) -> bool:
    """Return True when avatar_url already points to a locally stored file."""
    return bool(avatar_url and avatar_url.startswith("/static/avatars/"))


async def _save_avatar(profile: "LinkedInProfilePush", contact_id: str) -> str | None:
    """Save avatar from base64 data (preferred) or URL download (fallback).

    Returns the local path on success, None on failure.
    """
    import base64
    from pathlib import Path

    AVATARS_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "avatars"

    # Prefer base64 data URI from browser (bypasses LinkedIn CDN 403)
    if profile.avatar_data and profile.avatar_data.startswith("data:image"):
        try:
            # data:image/jpeg;base64,/9j/4AAQ...
            header, b64 = profile.avatar_data.split(",", 1)
            image_bytes = base64.b64decode(b64)
            if len(image_bytes) > 5_000_000:  # 5MB cap
                return None
            AVATARS_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{contact_id}.jpg"
            filepath = AVATARS_DIR / filename
            filepath.write_bytes(image_bytes)
            return f"/static/avatars/{filename}"
        except Exception:
            logger.exception("_save_avatar: base64 decode failed for contact %s", contact_id)
            # fall through to URL download

    # Fallback: server-side download (may fail with 403 on LinkedIn CDN)
    if profile.avatar_url:
        return await download_linkedin_avatar(profile.avatar_url, contact_id)

    return None


class LinkedInProfilePush(BaseModel):
    profile_id: str
    profile_url: str
    full_name: str
    headline: str | None = None
    company: str | None = None
    location: str | None = None
    about: str | None = None
    avatar_url: str | None = None
    avatar_data: str | None = None  # base64 data URI from browser (data:image/...;base64,...)


class LinkedInMessagePush(BaseModel):
    profile_id: str
    profile_name: str
    direction: str  # "inbound" | "outbound"
    content_preview: str
    timestamp: str  # ISO 8601
    conversation_id: str
    content_hash: str | None = None  # stable hash for dedup


class LinkedInPushRequest(BaseModel):
    profiles: list[LinkedInProfilePush] = Field(default=[], max_length=50)
    messages: list[LinkedInMessagePush] = Field(default=[], max_length=500)


@router.post("/push", response_model=Envelope[LinkedInPushResult])
async def push_linkedin_data(
    body: LinkedInPushRequest,
    current_user: User = Depends(get_extension_or_web_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive profile and message data from the LinkedIn Chrome Extension."""
    contacts_created = 0
    contacts_updated = 0
    interactions_created = 0
    interactions_skipped = 0
    contacts_with_new_interactions: set[uuid.UUID] = set()
    touched_contacts: list[Contact] = []

    # --- Pre-load all user's LinkedIn contacts for in-memory matching ---
    # Load all user contacts for in-memory matching (profile_id, url, name)
    all_contacts_result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id)
    )
    all_user_contacts = list(all_contacts_result.scalars().all())
    profile_id_map: dict[str, Contact] = {}
    url_map: dict[str, Contact] = {}
    name_map: dict[str, Contact] = {}
    for c in all_user_contacts:
        if c.linkedin_profile_id:
            profile_id_map[c.linkedin_profile_id] = c
        if c.linkedin_url:
            url_map[c.linkedin_url.rstrip("/")] = c
            # Backfill missing linkedin_profile_id from URL slug
            if not c.linkedin_profile_id:
                import re
                slug_match = re.search(r"/in/([^/?]+)", c.linkedin_url)
                if slug_match:
                    slug = slug_match.group(1)
                    c.linkedin_profile_id = slug
                    profile_id_map[slug] = c
        if c.full_name:
            name_map[c.full_name.lower()] = c

    # --- Pre-load existing interaction refs for message dedup ---
    all_refs: list[str] = []
    for msg in body.messages:
        if msg.content_hash:
            all_refs.append(f"linkedin:{msg.conversation_id}:{msg.content_hash}")
        else:
            all_refs.append(f"linkedin:{msg.conversation_id}:{msg.timestamp}")
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
    from app.services.sync_utils import sync_set_field
    for profile in body.profiles:
        profile_url_normalized = profile.profile_url.rstrip("/") if profile.profile_url else ""

        # In-memory lookup (no DB query per profile)
        contact = profile_id_map.get(profile.profile_id)
        if not contact and profile_url_normalized:
            contact = url_map.get(profile_url_normalized)

        if contact:
            # Update fields — respect user-edited field protection
            sync_set_field(contact, "full_name", profile.full_name)
            if profile.headline:
                contact.linkedin_headline = profile.headline  # platform-owned
                # Extract title from headline if contact has no title
                title_part = profile.headline.split(" @ ")[0].split(" at ")[0].strip()
                if title_part and len(title_part) < 100:
                    sync_set_field(contact, "title", title_part)
            sync_set_field(contact, "company", profile.company)
            sync_set_field(contact, "location", profile.location)
            if profile.about:
                contact.linkedin_bio = profile.about  # platform-owned
            if profile.profile_url:
                contact.linkedin_url = profile_url_normalized
            if not contact.linkedin_profile_id:
                contact.linkedin_profile_id = profile.profile_id
            # Clear broken remote LinkedIn URLs (403 from servers, can't be displayed)
            if contact.avatar_url and not _has_local_avatar(contact.avatar_url):
                contact.avatar_url = None
            # Save avatar: always overwrite when base64 data is present (fresh photo from browser)
            # Otherwise only download if no local avatar exists
            if profile.avatar_data or not _has_local_avatar(contact.avatar_url):
                local_path = await _save_avatar(profile, str(contact.id))
                if local_path:
                    contact.avatar_url = local_path
            contacts_updated += 1
        else:
            name_parts = (profile.full_name or "").split(None, 1)
            contact = Contact(
                user_id=current_user.id,
                full_name=profile.full_name,
                given_name=name_parts[0] if name_parts else None,
                family_name=name_parts[1] if len(name_parts) > 1 else None,
                linkedin_profile_id=profile.profile_id,
                linkedin_url=profile_url_normalized,
                linkedin_headline=profile.headline,
                linkedin_bio=profile.about,
                company=profile.company,
                location=profile.location,
            )
            db.add(contact)
            await db.flush()
            contacts_created += 1
            # Save avatar for the newly created contact
            local_path = await _save_avatar(profile, str(contact.id))
            if local_path:
                contact.avatar_url = local_path
            # Update in-memory maps for message matching
            if profile.profile_id:
                profile_id_map[profile.profile_id] = contact
            if profile_url_normalized:
                url_map[profile_url_normalized] = contact
            if contact.full_name:
                name_map[contact.full_name.lower()] = contact
        touched_contacts.append(contact)

    # --- Messages ---
    for msg in body.messages:
        # Use content_hash for stable dedup (timestamps are unreliable from extension)
        if msg.content_hash:
            raw_ref = f"linkedin:{msg.conversation_id}:{msg.content_hash}"
        else:
            raw_ref = f"linkedin:{msg.conversation_id}:{msg.timestamp}"

        # Check for duplicate using pre-loaded set (no DB query)
        if raw_ref in existing_refs:
            interactions_skipped += 1
            continue

        # Find contact using in-memory maps (no DB query)
        contact = profile_id_map.get(msg.profile_id)

        if not contact:
            msg_url = f"https://www.linkedin.com/in/{msg.profile_id}"
            contact = url_map.get(msg_url)
            if contact and not contact.linkedin_profile_id:
                contact.linkedin_profile_id = msg.profile_id
                profile_id_map[msg.profile_id] = contact

        if not contact and msg.profile_name:
            contact = name_map.get(msg.profile_name.lower())
            if contact and not contact.linkedin_profile_id:
                contact.linkedin_profile_id = msg.profile_id
                profile_id_map[msg.profile_id] = contact

        if not contact:
            # Auto-create contact stub — split full name into given/family
            name_parts = (msg.profile_name or "").split(None, 1)
            contact = Contact(
                user_id=current_user.id,
                full_name=msg.profile_name,
                given_name=name_parts[0] if name_parts else None,
                family_name=name_parts[1] if len(name_parts) > 1 else None,
                linkedin_profile_id=msg.profile_id,
                linkedin_url=f"https://www.linkedin.com/in/{msg.profile_id}" if msg.profile_id else None,
            )
            db.add(contact)
            await db.flush()
            contacts_created += 1
            # Update in-memory maps
            if msg.profile_id:
                profile_id_map[msg.profile_id] = contact
            if contact.full_name:
                name_map[contact.full_name.lower()] = contact

        touched_contacts.append(contact)

        try:
            occurred_at = datetime.fromisoformat(msg.timestamp)
        except ValueError:
            occurred_at = datetime.now(UTC)

        interaction = Interaction(
            contact_id=contact.id,
            user_id=current_user.id,
            platform="linkedin",
            direction=msg.direction if msg.direction in ("inbound", "outbound") else "inbound",
            content_preview=msg.content_preview[:500] if msg.content_preview else None,
            raw_reference_id=raw_ref,
            occurred_at=occurred_at,
        )
        db.add(interaction)
        interactions_created += 1
        contacts_with_new_interactions.add(contact.id)

        # Update last_interaction_at
        if not contact.last_interaction_at or occurred_at > contact.last_interaction_at:
            contact.last_interaction_at = occurred_at
        contact.interaction_count = (contact.interaction_count or 0) + 1

    # Auto-dismiss pending suggestions for contacts that just received new interactions
    if contacts_with_new_interactions:
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(FollowUpSuggestion)
            .where(FollowUpSuggestion.contact_id.in_(list(contacts_with_new_interactions)), FollowUpSuggestion.status == "pending")
            .values(status="dismissed")
        )

    await db.flush()

    # Record sync event for LinkedIn push
    if contacts_created + contacts_updated + interactions_created > 0:
        from app.services.sync_history import record_sync_start, record_sync_complete
        sync_event = await record_sync_start(current_user.id, "linkedin", "webhook", db)
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
                logger.info("linkedin push: auto-merged %d duplicate(s) for user %s", len(merged), current_user.id)
        except Exception:
            logger.warning("linkedin push: auto-merge failed for user %s", current_user.id, exc_info=True)
        await db.flush()

    # Collect contacts that need backfill: have a linkedin_profile_id but are
    # missing avatar_url (or title/company). Check touched contacts first,
    # then query for any other contacts missing avatars (up to 10 total).
    seen_ids: set[uuid.UUID] = set()
    backfill_needed: list[BackfillItem] = []

    for contact in touched_contacts:
        if contact.id in seen_ids:
            continue
        seen_ids.add(contact.id)
        if contact.linkedin_profile_id and (
            not contact.title or not contact.company or not contact.avatar_url
        ):
            backfill_needed.append(
                BackfillItem(
                    contact_id=str(contact.id),
                    linkedin_profile_id=contact.linkedin_profile_id,
                    linkedin_url=contact.linkedin_url,
                )
            )

    # Also include contacts not touched in this push but missing avatar
    # Include contacts with either slug-format profile_id OR a linkedin_url
    if len(backfill_needed) < 10:
        filters = [
            Contact.user_id == current_user.id,
            Contact.linkedin_profile_id.isnot(None),
            or_(
                ~Contact.linkedin_profile_id.like("ACo%"),  # slug-format profile_id
                Contact.linkedin_url.isnot(None),           # OR has a usable URL
            ),
            Contact.avatar_url.is_(None),
        ]
        if seen_ids:
            filters.append(Contact.id.notin_(seen_ids))
        missing_avatar_result = await db.execute(
            select(Contact).where(*filters).limit(10 - len(backfill_needed))
        )
        for c in missing_avatar_result.scalars().all():
            backfill_needed.append(
                BackfillItem(
                    contact_id=str(c.id),
                    linkedin_profile_id=c.linkedin_profile_id,
                    linkedin_url=c.linkedin_url,
                )
            )

    return {
        "data": LinkedInPushResult(
            contacts_created=contacts_created,
            contacts_updated=contacts_updated,
            interactions_created=interactions_created,
            interactions_skipped=interactions_skipped,
            backfill_needed=backfill_needed,
        ),
        "error": None,
        "meta": None,
    }
