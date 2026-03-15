from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

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
)
from app.schemas.responses import DeletedData, EnrichData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])

VALID_PRIORITY_LEVELS = {"low", "normal", "high", "archived"}


class BulkUpdateBody(BaseModel):
    contact_ids: list[uuid.UUID] = Field(max_length=500)
    add_tags: list[str] | None = Field(default=None, max_length=50)
    remove_tags: list[str] | None = Field(default=None, max_length=50)
    priority_level: str | None = None
    company: str | None = None


@router.post("", response_model=Envelope[ContactResponse], status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_in: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactResponse]:
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

    await db.flush()
    await db.refresh(contact)
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


@router.get("/{contact_id}/activity")
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


@router.get("/{contact_id}/related")
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

    from app.integrations.apollo import enrich_person

    # Prefer email over LinkedIn URL for higher match quality
    enriched = await enrich_person(
        email=contact.emails[0] if contact.emails else None,
        linkedin_url=contact.linkedin_url if not contact.emails else None,
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
