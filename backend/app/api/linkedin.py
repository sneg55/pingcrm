"""LinkedIn Chrome Extension push endpoint."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, UTC

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.integrations.linkedin import download_linkedin_avatar
from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.responses import Envelope, LinkedInPushResult

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
            pass  # fall through to URL download

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive profile and message data from the LinkedIn Chrome Extension."""
    contacts_created = 0
    contacts_updated = 0
    interactions_created = 0
    interactions_skipped = 0
    contacts_with_new_interactions: set[uuid.UUID] = set()

    # --- Profiles ---
    for profile in body.profiles:
        # Normalize URL for matching (strip trailing slashes)
        profile_url_normalized = profile.profile_url.rstrip("/") if profile.profile_url else ""

        result = await db.execute(
            select(Contact).where(
                Contact.user_id == current_user.id,
                Contact.linkedin_profile_id == profile.profile_id,
            )
        )
        contact = result.scalar_one_or_none()

        if not contact and profile_url_normalized:
            # Try to find by linkedin_url (with and without trailing slash)
            result = await db.execute(
                select(Contact).where(
                    Contact.user_id == current_user.id,
                    Contact.linkedin_url.in_([
                        profile_url_normalized,
                        profile_url_normalized + "/",
                    ]),
                )
            )
            contact = result.scalar_one_or_none()

        if contact:
            # Update non-empty fields
            if profile.full_name:
                contact.full_name = profile.full_name
            if profile.headline:
                contact.linkedin_headline = profile.headline
                # Extract title from headline if contact has no title
                if not contact.title:
                    # "Title @ Company" or "Title at Company" → extract title part
                    title_part = profile.headline.split(" @ ")[0].split(" at ")[0].strip()
                    if title_part and len(title_part) < 100:
                        contact.title = title_part
            if profile.company:
                contact.company = profile.company
            if profile.location:
                contact.location = profile.location
            if profile.about:
                contact.linkedin_bio = profile.about
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
            contact = Contact(
                user_id=current_user.id,
                full_name=profile.full_name,
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

    # --- Messages ---
    for msg in body.messages:
        # Use content_hash for stable dedup (timestamps are unreliable from extension)
        if msg.content_hash:
            raw_ref = f"linkedin:{msg.conversation_id}:{msg.content_hash}"
        else:
            raw_ref = f"linkedin:{msg.conversation_id}:{msg.timestamp}"

        # Check for duplicate
        existing = await db.execute(
            select(Interaction.id).where(
                Interaction.user_id == current_user.id,
                Interaction.raw_reference_id == raw_ref,
            )
        )
        if existing.scalar_one_or_none():
            interactions_skipped += 1
            continue

        # Find contact by profile_id or linkedin_url
        result = await db.execute(
            select(Contact).where(
                Contact.user_id == current_user.id,
                Contact.linkedin_profile_id == msg.profile_id,
            )
        )
        contact = result.scalar_one_or_none()

        if not contact:
            # Try matching by linkedin_url containing the profile_id slug
            msg_url = f"https://www.linkedin.com/in/{msg.profile_id}"
            result = await db.execute(
                select(Contact).where(
                    Contact.user_id == current_user.id,
                    Contact.linkedin_url.in_([msg_url, msg_url + "/"]),
                )
            )
            contact = result.scalar_one_or_none()
            if contact and not contact.linkedin_profile_id:
                contact.linkedin_profile_id = msg.profile_id

        if not contact:
            # Auto-create contact stub
            contact = Contact(
                user_id=current_user.id,
                full_name=msg.profile_name,
                linkedin_profile_id=msg.profile_id,
            )
            db.add(contact)
            await db.flush()
            contacts_created += 1

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

    return {
        "data": LinkedInPushResult(
            contacts_created=contacts_created,
            contacts_updated=contacts_updated,
            interactions_created=interactions_created,
            interactions_skipped=interactions_skipped,
        ),
        "error": None,
        "meta": None,
    }
