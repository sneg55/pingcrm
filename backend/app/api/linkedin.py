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
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.responses import Envelope, LinkedInPushResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/linkedin", tags=["linkedin"])


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
            if profile.avatar_url:
                contact.avatar_url = profile.avatar_url
            if profile.profile_url:
                contact.linkedin_url = profile_url_normalized
            if not contact.linkedin_profile_id:
                contact.linkedin_profile_id = profile.profile_id
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
                avatar_url=profile.avatar_url,
                source="linkedin-extension",
            )
            db.add(contact)
            await db.flush()
            contacts_created += 1

    # --- Messages ---
    for msg in body.messages:
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
                source="linkedin-extension",
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

        # Update last_interaction_at
        if not contact.last_interaction_at or occurred_at > contact.last_interaction_at:
            contact.last_interaction_at = occurred_at
        contact.interaction_count = (contact.interaction_count or 0) + 1

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
