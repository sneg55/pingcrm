from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.api.contacts_routes.shared import (
    Contact,
    Depends,
    Envelope,
    HTTPException,
    Query,
    AsyncSession,
    User,
    envelope,
    func,
    get_current_user,
    get_db,
    select,
    status,
)
from app.schemas.contact import (
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    _normalize_tags,
)
from app.schemas.responses import DeletedData, EnrichData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])

VALID_PRIORITY_LEVELS = {"low", "medium", "high", "archived"}


class BulkUpdateBody(BaseModel):
    contact_ids: list[uuid.UUID] = Field(max_length=500)
    add_tags: list[str] | None = Field(default=None, max_length=50)
    remove_tags: list[str] | None = Field(default=None, max_length=50)
    priority_level: str | None = None
    company: str | None = None

    @field_validator("add_tags", "remove_tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _normalize_tags(v)


@router.post("", response_model=Envelope[ContactResponse], status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_in: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactResponse]:
    # Check telegram_username uniqueness
    if contact_in.telegram_username:
        dup_result = await db.execute(
            select(Contact).where(
                Contact.user_id == current_user.id,
                func.lower(Contact.telegram_username) == contact_in.telegram_username.lower(),
            )
        )
        dup = dup_result.scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Another contact already has this Telegram username",
                    "conflicting_contact": {"id": str(dup.id), "full_name": dup.full_name},
                },
            )

    contact = Contact(**contact_in.model_dump(), user_id=current_user.id)
    db.add(contact)
    await db.flush()

    # Auto-assign to organization by company name
    from app.services.organization_service import auto_create_organization
    await auto_create_organization(contact, current_user.id, db)

    await db.refresh(contact)
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.post("/bulk-update", response_model=Envelope[dict])
async def bulk_update_contacts(
    body: BulkUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Bulk update tags and/or priority level for a set of contacts."""
    result = await db.execute(
        select(Contact).where(
            Contact.id.in_(body.contact_ids),
            Contact.user_id == current_user.id,
        )
    )
    contacts = result.scalars().all()

    if body.priority_level is not None and body.priority_level not in VALID_PRIORITY_LEVELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid priority_level. Must be one of: {', '.join(sorted(VALID_PRIORITY_LEVELS))}")

    archive_contact_ids: list[uuid.UUID] = []
    for contact in contacts:
        if body.add_tags:
            existing = set(contact.tags or [])
            contact.tags = list(existing | set(body.add_tags))
        if body.remove_tags:
            existing = set(contact.tags or [])
            contact.tags = list(existing - set(body.remove_tags))
        if body.company is not None:
            contact.company = body.company
        if body.priority_level is not None:
            contact.priority_level = body.priority_level
            if body.priority_level == "archived":
                archive_contact_ids.append(contact.id)

    if archive_contact_ids:
        from app.models.follow_up import FollowUpSuggestion
        pending_result = await db.execute(
            select(FollowUpSuggestion).where(
                FollowUpSuggestion.contact_id.in_(archive_contact_ids),
                FollowUpSuggestion.status == "pending",
            )
        )
        for suggestion in pending_result.scalars().all():
            suggestion.status = "dismissed"

    await db.flush()
    return envelope({"updated": len(contacts)})


@router.delete("/2nd-tier", response_model=Envelope[dict])
async def delete_2nd_tier_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Delete all contacts tagged as '2nd tier' for the current user."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == current_user.id,
            Contact.tags.contains(["2nd tier"]),
        )
    )
    contacts = result.scalars().all()

    if not contacts:
        return envelope({"deleted_count": 0})

    # DB cascade (ondelete="CASCADE") on all child tables handles related rows
    # (interactions, follow_up_suggestions, detected_events, etc.) automatically.
    for contact in contacts:
        await db.delete(contact)

    await db.flush()
    return envelope({"deleted_count": len(contacts)})


@router.get("/2nd-tier/count", response_model=Envelope[dict])
async def count_2nd_tier_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Count contacts tagged as '2nd tier' for the current user."""
    from sqlalchemy import func as sa_func

    result = await db.execute(
        select(sa_func.count()).select_from(Contact).where(
            Contact.user_id == current_user.id,
            Contact.tags.contains(["2nd tier"]),
        )
    )
    count = result.scalar() or 0
    return envelope({"count": count})


@router.get("/{contact_id}", response_model=Envelope[ContactResponse])
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactResponse]:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.put("/{contact_id}", response_model=Envelope[ContactResponse])
async def update_contact(
    contact_id: uuid.UUID,
    contact_in: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactResponse]:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    update_data = contact_in.model_dump(exclude_unset=True)
    company_changed = "company" in update_data and update_data["company"] != contact.company
    telegram_username_changed = (
        "telegram_username" in update_data
        and update_data["telegram_username"] != contact.telegram_username
    )
    twitter_handle_changed = (
        "twitter_handle" in update_data
        and update_data["twitter_handle"] != contact.twitter_handle
        and update_data["twitter_handle"]  # not clearing
    )

    # Check telegram_username uniqueness
    if telegram_username_changed and update_data["telegram_username"]:
        dup_result = await db.execute(
            select(Contact).where(
                Contact.user_id == current_user.id,
                Contact.id != contact_id,
                func.lower(Contact.telegram_username) == update_data["telegram_username"].lower(),
            )
        )
        dup = dup_result.scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Another contact already has this Telegram username",
                    "conflicting_contact": {"id": str(dup.id), "full_name": dup.full_name},
                },
            )

    # Clear stale telegram_user_id when username changes
    if telegram_username_changed:
        update_data["telegram_user_id"] = None

    # Validate organization_id belongs to current user (prevent cross-tenant linkage)
    if "organization_id" in update_data and update_data["organization_id"] is not None:
        from app.models.organization import Organization
        org_check = await db.execute(
            select(Organization.id).where(
                Organization.id == update_data["organization_id"],
                Organization.user_id == current_user.id,
            )
        )
        if not org_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization does not belong to this user",
            )

    for field, value in update_data.items():
        setattr(contact, field, value)

    # Track user-edited fields for sync protection
    from app.services.sync_utils import PROTECTABLE_FIELDS
    edited = set(contact.user_edited_fields or [])
    for field in update_data:
        if field in PROTECTABLE_FIELDS:
            edited.add(field)
    contact.user_edited_fields = sorted(edited)

    # Re-assign organization if company name changed
    if company_changed:
        contact.organization_id = None  # clear old assignment
        from app.services.organization_service import auto_create_organization
        await auto_create_organization(contact, current_user.id, db)

    # When archiving, dismiss any pending follow-up suggestions
    if contact.priority_level == "archived":
        from app.models.follow_up import FollowUpSuggestion
        pending_result = await db.execute(
            select(FollowUpSuggestion).where(
                FollowUpSuggestion.contact_id == contact_id,
                FollowUpSuggestion.status == "pending",
            )
        )
        for suggestion in pending_result.scalars().all():
            suggestion.status = "dismissed"

    # Clear stale twitter_user_id when handle changes
    if twitter_handle_changed:
        contact.twitter_user_id = None
        contact.twitter_bio = None

    await db.flush()
    await db.refresh(contact)

    # Clear bio-refresh rate-limit so the frontend can immediately re-fetch
    if twitter_handle_changed:
        try:
            import redis.asyncio as aioredis
            from app.core.config import settings
            r = aioredis.from_url(settings.REDIS_URL)
            await r.delete(f"bio_check:{contact_id}")
            await r.aclose()
        except Exception:
            logger.warning("Failed to clear bio_refresh cache for contact %s", contact_id, exc_info=True)

    # Trigger background refresh when Twitter handle is added/changed
    if twitter_handle_changed:
        try:
            from app.services.task_jobs.twitter import poll_twitter_activity
            poll_twitter_activity.apply_async(args=[str(current_user.id)], countdown=3)
        except Exception:
            logger.warning("Failed to dispatch poll_twitter_activity for user %s", current_user.id, exc_info=True)
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.delete("/{contact_id}", response_model=Envelope[DeletedData])
async def delete_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[DeletedData]:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    await db.delete(contact)
    return envelope({"id": str(contact_id), "deleted": True})


@router.get("/{contact_id}/activity", response_model=Envelope[dict])
async def get_contact_activity(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return activity score breakdown and monthly interaction trend for a contact."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func

    from app.models.interaction import Interaction
    from app.services.scoring import calculate_score_breakdown

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    breakdown = await calculate_score_breakdown(contact_id, db)

    # Earliest interaction date
    from sqlalchemy import func as sa_func
    first_interaction_result = await db.execute(
        select(sa_func.min(Interaction.occurred_at))
        .where(Interaction.contact_id == contact_id)
    )
    first_interaction_at = first_interaction_result.scalar_one_or_none()

    # Monthly trend: last 6 months
    six_months_ago = datetime.now(UTC) - timedelta(days=183)
    month_col = func.date_trunc("month", Interaction.occurred_at).label("month")
    trend_result = await db.execute(
        select(month_col, func.count().label("count"))
        .where(
            Interaction.contact_id == contact_id,
            Interaction.occurred_at >= six_months_ago,
        )
        .group_by(month_col)
        .order_by(month_col)
    )
    monthly_trend = [
        {"month": row.month.strftime("%Y-%m"), "count": row.count}
        for row in trend_result.all()
    ]

    return envelope({
        "score": breakdown.total,
        "dimensions": {
            "reciprocity": {"value": breakdown.reciprocity, "max": 4},
            "recency": {"value": breakdown.recency, "max": 3},
            "frequency": {"value": breakdown.frequency, "max": 2},
            "breadth": {"value": breakdown.breadth, "max": 1},
            "tenure": {"value": breakdown.tenure, "max": 2},
        },
        "stats": {
            "inbound_365d": breakdown.inbound_365d,
            "outbound_365d": breakdown.outbound_365d,
            "count_30d": breakdown.count_30d,
            "count_90d": breakdown.count_90d,
            "platforms": breakdown.platforms,
            "interaction_count": breakdown.interaction_count,
            "first_interaction_at": first_interaction_at.isoformat() if first_interaction_at else None,
        },
        "monthly_trend": monthly_trend,
    })


@router.get("/{contact_id}/related", response_model=Envelope[list])
async def get_related_contacts(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return up to 5 contacts related to the given contact by org, company, or shared tags."""
    from sqlalchemy import or_

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    conditions = []
    if contact.organization_id:
        conditions.append(Contact.organization_id == contact.organization_id)
    if contact.company:
        conditions.append(func.lower(Contact.company) == contact.company.lower())
    if contact.tags:
        conditions.append(Contact.tags.overlap(contact.tags))

    if not conditions:
        return envelope([])

    related_result = await db.execute(
        select(Contact).where(
            Contact.user_id == current_user.id,
            Contact.id != contact_id,
            Contact.priority_level != "archived",
            or_(*conditions),
        ).order_by(Contact.relationship_score.desc().nullslast())
        .limit(5)
    )
    related_contacts = list(related_result.scalars().all())

    items = []
    for c in related_contacts:
        reasons: list[str] = []
        if contact.organization_id and c.organization_id == contact.organization_id:
            reasons.append("Same org")
        if contact.company and c.company and c.company.lower() == contact.company.lower():
            reasons.append("Same company")
        if contact.tags and c.tags:
            for tag in contact.tags:
                if tag in c.tags:
                    reasons.append(f"Shared tag: {tag}")
        items.append({
            "id": str(c.id),
            "full_name": c.full_name,
            "title": c.title,
            "company": c.company,
            "avatar_url": c.avatar_url,
            "relationship_score": c.relationship_score,
            "reasons": reasons,
        })

    return envelope(items)


@router.post("/{contact_id}/enrich", response_model=Envelope[EnrichData])
async def enrich_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[EnrichData]:
    """Enrich a contact using the Apollo People Enrichment API.

    Only fills in fields that are currently empty/null on the contact.
    """
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.emails and not contact.linkedin_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact has no email or LinkedIn URL. At least one is required for enrichment.",
        )

    from app.integrations.apollo import ApolloError, enrich_person

    # Prefer email over LinkedIn URL for higher match quality
    try:
        enriched = await enrich_person(
            email=contact.emails[0] if contact.emails else None,
            linkedin_url=contact.linkedin_url if not contact.emails else None,
        )
    except ApolloError as exc:
        logger.warning(
            "enrich_contact: Apollo failed for contact %s: %s",
            contact_id,
            exc,
            extra={"provider": "apollo", "contact_id": str(contact_id)},
        )
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    if not enriched:
        return envelope({"fields_updated": [], "source": "apollo"})

    # Simple string/scalar fields — only update if contact field is empty
    fields_updated: list[str] = []
    scalar_fields = [
        "given_name", "family_name", "full_name", "title", "company",
        "location", "linkedin_url", "twitter_handle", "avatar_url",
    ]
    for field in scalar_fields:
        if field in enriched and not getattr(contact, field, None):
            setattr(contact, field, enriched[field])
            fields_updated.append(field)

    # List fields — append new values
    if "phones" in enriched:
        existing_phones = set(contact.phones or [])
        new_phones = [p for p in enriched["phones"] if p not in existing_phones]
        if new_phones:
            contact.phones = list(existing_phones | set(new_phones))
            fields_updated.append("phones")

    if "emails" in enriched:
        existing_emails = set(contact.emails or [])
        new_emails = [e for e in enriched["emails"] if e not in existing_emails]
        if new_emails:
            contact.emails = list(existing_emails | set(new_emails))
            fields_updated.append("emails")

    if fields_updated:
        await db.flush()
        await db.refresh(contact)

    return envelope({"fields_updated": fields_updated, "source": "apollo"})


@router.post("/{contact_id}/extract-bio", response_model=Envelope[EnrichData])
async def extract_bio(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[EnrichData]:
    """Extract structured data from contact bios using AI.

    Parses twitter_bio, telegram_bio, linkedin_bio/headline and the contact's
    name fields through Haiku to extract title, company, website, and
    normalize name fields (e.g. "Anders | LoopFi" -> first: Anders, company: LoopFi).
    Also updates the linked Organization record with extracted company details.
    """
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    has_bios = any([
        contact.twitter_bio, contact.telegram_bio,
        contact.linkedin_bio, contact.linkedin_headline,
    ])
    if not has_bios and not contact.full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact has no bios or name to extract from.",
        )

    from app.services.bio_extractor import extract_from_bios

    extracted = await extract_from_bios(
        full_name=contact.full_name,
        given_name=contact.given_name,
        family_name=contact.family_name,
        title=contact.title,
        company=contact.company,
        twitter_bio=contact.twitter_bio,
        telegram_bio=contact.telegram_bio,
        linkedin_bio=contact.linkedin_bio,
        linkedin_headline=contact.linkedin_headline,
    )

    if not extracted:
        return envelope({"fields_updated": [], "source": "ai_bio"})

    # Apply contact-level fields (only if currently empty OR if name was normalized)
    fields_updated: list[str] = []
    contact_fields = ["given_name", "family_name", "title", "company"]
    for field in contact_fields:
        new_val = extracted.get(field)
        if not new_val:
            continue
        old_val = getattr(contact, field, None) or ""
        # Always apply name fields (normalization), others only if empty
        if field in ("given_name", "family_name") or not old_val:
            if new_val != old_val:
                setattr(contact, field, new_val)
                fields_updated.append(field)

    # Update full_name if name fields changed
    if "given_name" in fields_updated or "family_name" in fields_updated:
        new_full = " ".join(
            filter(None, [contact.given_name, contact.family_name])
        ) or contact.full_name
        if new_full != contact.full_name:
            contact.full_name = new_full
            if "full_name" not in fields_updated:
                fields_updated.append("full_name")

    # Update or create Organization with extracted company details
    if extracted.get("company"):
        from app.services.organization_service import auto_create_organization

        org = await auto_create_organization(contact, current_user.id, db)
        if org:
            org_updated = False
            if extracted.get("company_website") and not org.website:
                org.website = extracted["company_website"]
                org_updated = True
                fields_updated.append("company_website")
            if extracted.get("company_industry") and not org.industry:
                org.industry = extracted["company_industry"]
                org_updated = True
                fields_updated.append("company_industry")
            if extracted.get("company_location") and not org.location:
                org.location = extracted["company_location"]
                org_updated = True
                fields_updated.append("company_location")
            # Download logo if we got a website and org has no logo yet
            if org_updated and org.website and not org.logo_url:
                from app.services.organization_service import download_org_logo
                logo_url = await download_org_logo(org.website, org.id)
                if logo_url:
                    org.logo_url = logo_url

    if fields_updated:
        await db.flush()
        await db.refresh(contact)

    return envelope({"fields_updated": fields_updated, "source": "ai_bio"})


@router.post("/{contact_id}/promote", response_model=Envelope[dict])
async def promote_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Remove '2nd Tier' tag from a contact, promoting it to 1st Tier."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    tags = list(contact.tags or [])
    # Case-insensitive removal of "2nd Tier" tag
    new_tags = [t for t in tags if t.lower() != "2nd tier"]
    if len(new_tags) == len(tags):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact is not a 2nd Tier contact",
        )

    contact.tags = new_tags
    await db.flush()
    return envelope({"promoted": True, "id": str(contact_id)})
