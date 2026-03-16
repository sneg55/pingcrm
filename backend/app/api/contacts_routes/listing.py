from __future__ import annotations

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
from app.schemas.contact import ContactListResponse, ContactResponse
from app.schemas.responses import ContactStatsData

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    tag: str | None = Query(None),
    source: str | None = Query(None),
    score: str | None = Query(None, description="Filter by score tier: strong (8-10), active (4-7), dormant (0-3)"),
    date_from: str | None = Query(None, description="Filter contacts created on or after this date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Filter contacts created on or before this date (YYYY-MM-DD)"),
    has_interactions: bool | None = Query(None, description="Filter to contacts with (true) or without (false) interactions"),
    interaction_days: int | None = Query(None, ge=1, le=365, description="Filter to contacts with last interaction within N days"),
    has_birthday: bool | None = Query(None, description="Filter to contacts with (true) or without (false) a birthday set"),
    priority: str | None = Query(None, description="Filter by priority level: high, medium, low"),
    archived_only: bool = Query(False, description="Return only archived contacts"),
    sort: str = Query("score", pattern="^(score|created|interaction|birthday|company|activity|overdue)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactListResponse:
    from app.services.contact_search import list_contacts_paginated

    return await list_contacts_paginated(
        db,
        current_user.id,
        page=page,
        page_size=page_size,
        search=search,
        tag=tag,
        source=source,
        score=score,
        priority=priority,
        date_from=date_from,
        date_to=date_to,
        has_interactions=has_interactions,
        interaction_days=interaction_days,
        has_birthday=has_birthday,
        archived_only=archived_only,
        sort_by=sort,
    )


@router.get("/ids", response_model=Envelope[list[str]])
async def list_contact_ids(
    search: str | None = Query(None),
    tag: str | None = Query(None),
    source: str | None = Query(None),
    score: str | None = Query(None),
    priority: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    has_interactions: bool | None = Query(None),
    interaction_days: int | None = Query(None, ge=1, le=365),
    has_birthday: bool | None = Query(None),
    archived_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[str]]:
    """Return all matching contact IDs (no pagination) for bulk select-all."""
    from app.services.contact_search import build_contact_filter_query

    query = build_contact_filter_query(
        current_user.id,
        search=search,
        tag=tag,
        source=source,
        score=score,
        priority=priority,
        date_from=date_from,
        date_to=date_to,
        has_interactions=has_interactions,
        interaction_days=interaction_days,
        has_birthday=has_birthday,
        archived_only=archived_only,
    )
    # Select only IDs for efficiency
    id_query = query.with_only_columns(Contact.id)
    result = await db.execute(id_query)
    ids = [str(row[0]) for row in result.all()]
    return envelope(ids)


@router.get("/stats", response_model=Envelope[ContactStatsData])
async def contact_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactStatsData]:
    """Return aggregate contact stats for the dashboard."""
    from datetime import UTC, datetime, timedelta

    from app.models.interaction import Interaction

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Contact.relationship_score >= 8).label("strong"),
            func.count().filter(
                Contact.relationship_score >= 4,
                Contact.relationship_score < 8,
            ).label("active"),
            func.count().filter(Contact.relationship_score < 4).label("dormant"),
        ).where(
            Contact.user_id == current_user.id,
            Contact.priority_level != "archived",
        )
    )
    row = result.one()

    week_ago = datetime.now(UTC) - timedelta(days=7)
    interactions_result = await db.execute(
        select(func.count()).where(
            Interaction.user_id == current_user.id,
            Interaction.occurred_at >= week_ago,
        )
    )
    interactions_this_week = interactions_result.scalar_one()

    return {
        "data": {
            "total": row.total,
            "strong": row.strong,
            "active": row.active,
            "dormant": row.dormant,
            "interactions_this_week": interactions_this_week,
        },
        "error": None,
    }


@router.get("/birthdays")
async def get_upcoming_birthdays(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return contacts with birthdays in the next 7 days."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    today = now.date()
    upcoming_mmdd = [(today + timedelta(days=d)).strftime("%m-%d") for d in range(7)]
    upcoming_set = set(upcoming_mmdd)

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == current_user.id,
            Contact.priority_level != "archived",
            Contact.birthday.isnot(None),
        )
    )
    contacts = result.scalars().all()

    matches = []
    for contact in contacts:
        bday = contact.birthday.strip()
        mmdd = bday[-5:]  # supports "MM-DD" and "YYYY-MM-DD"
        if mmdd not in upcoming_set:
            continue
        days_away = upcoming_mmdd.index(mmdd)
        matches.append((days_away, contact))

    matches.sort(key=lambda x: x[0])
    matches = matches[:10]

    return envelope(
        [
            {
                **ContactResponse.model_validate(c).model_dump(),
                "days_until_birthday": days,
            }
            for days, c in matches
        ]
    )


@router.get("/overdue")
async def get_overdue_contacts(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return contacts that have exceeded their follow-up threshold, sorted by most overdue first."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    default_thresholds = {"high": 30, "medium": 60, "low": 180}
    thresholds: dict = current_user.priority_settings or default_thresholds

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == current_user.id,
            Contact.priority_level != "archived",
            Contact.last_interaction_at.isnot(None),
        )
    )
    contacts = result.scalars().all()

    overdue: list[tuple[int, Contact]] = []
    for contact in contacts:
        priority = contact.priority_level or "medium"
        threshold_days = thresholds.get(priority, default_thresholds.get(priority, 60))
        last = contact.last_interaction_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        days_since = (now - last).days
        days_overdue = days_since - threshold_days
        if days_overdue > 0:
            overdue.append((days_overdue, contact))

    overdue.sort(key=lambda x: x[0], reverse=True)
    overdue = overdue[:limit]

    return envelope(
        [
            {
                **ContactResponse.model_validate(c).model_dump(),
                "days_overdue": days,
            }
            for days, c in overdue
        ]
    )


@router.get("/tags", response_model=Envelope[list[str]])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[str]]:
    """Return all unique tags used across the user's contacts (case-insensitive dedup)."""
    result = await db.execute(
        select(func.unnest(Contact.tags)).where(
            Contact.user_id == current_user.id,
            Contact.tags.isnot(None),
        ).distinct()
    )
    # Case-insensitive dedup: keep first seen form, sort lowercased
    seen: set[str] = set()
    unique: list[str] = []
    for (raw_tag,) in result.all():
        lower = raw_tag.lower()
        if lower not in seen:
            seen.add(lower)
            unique.append(lower)
    return {"data": sorted(unique), "error": None}
