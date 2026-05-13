from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter

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
from app.schemas.responses import DeletedData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])



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

    # Check email uniqueness (case-insensitive across the emails array)
    if contact_in.emails:
        from sqlalchemy import text as _sql_text
        from app.services.contact_resolver import normalize_email
        for raw_email in contact_in.emails:
            email_norm = normalize_email(raw_email)
            if not email_norm:
                continue
            dup_row = await db.execute(
                _sql_text(
                    """
                    SELECT id, full_name FROM contacts
                    WHERE user_id = :uid
                      AND EXISTS (
                        SELECT 1 FROM unnest(emails) e
                        WHERE lower(trim(e)) = :norm
                      )
                    LIMIT 1
                    """
                ),
                {"uid": current_user.id, "norm": email_norm},
            )
            row = dup_row.first()
            if row:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": f"Another contact already has email {raw_email}",
                        "conflicting_contact": {"id": str(row[0]), "full_name": row[1]},
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

    # Check twitter_handle uniqueness
    if twitter_handle_changed and update_data["twitter_handle"]:
        dup_result = await db.execute(
            select(Contact).where(
                Contact.user_id == current_user.id,
                Contact.id != contact_id,
                func.lower(Contact.twitter_handle) == update_data["twitter_handle"].lower(),
            )
        )
        dup = dup_result.scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Another contact already has this Twitter handle",
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
            suggestion.dismissed_by = "system"

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


