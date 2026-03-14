"""LinkedIn Chrome Extension push endpoint."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, UTC

from fastapi import APIRouter, Depends
from pydantic import BaseModel
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


class LinkedInProfilePush(BaseModel):
    profile_id: str
    profile_url: str
    full_name: str
    headline: str | None = None
    company: str | None = None
    location: str | None = None
    about: str | None = None
    avatar_url: str | None = None


class LinkedInMessagePush(BaseModel):
    profile_id: str
    profile_name: str
    direction: str  # "inbound" | "outbound"
    content_preview: str
    timestamp: str  # ISO 8601
    conversation_id: str
    content_hash: str | None = None  # stable hash for dedup


class LinkedInPushRequest(BaseModel):
    profiles: list[LinkedInProfilePush] = []
    messages: list[LinkedInMessagePush] = []


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
            # Download avatar only when the contact does not already have a local copy
            if profile.avatar_url and not _has_local_avatar(contact.avatar_url):
                local_path = await download_linkedin_avatar(
                    profile.avatar_url, str(contact.id)
                )
                if local_path:
                    contact.avatar_url = local_path
                elif not contact.avatar_url:
                    # Fall back to the remote URL only when there is nothing stored yet
                    contact.avatar_url = profile.avatar_url
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
            # Download avatar for the newly created contact
            if profile.avatar_url:
                local_path = await download_linkedin_avatar(
                    profile.avatar_url, str(contact.id)
                )
                contact.avatar_url = local_path or profile.avatar_url

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

    await db.commit()

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
