"""Contact search and filter query builder."""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.schemas.contact import ContactListResponse, ContactResponse, PaginationMeta


def build_contact_filter_query(
    user_id: object,
    *,
    search: str | None = None,
    tag: str | None = None,
    source: str | None = None,
    score: str | None = None,
    priority: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    has_interactions: bool | None = None,
    interaction_days: int | None = None,
    has_birthday: bool | None = None,
    archived_only: bool = False,
) -> object:
    """Build a SQLAlchemy select query for contacts with optional filters.

    Args:
        user_id: The authenticated user's UUID.
        search: Full-text search string (matched against multiple fields).
        tag: Filter to contacts that have this tag.
        source: Filter to contacts from this source.
        score: Score tier filter: 'strong' (8-10), 'active' (4-7), 'dormant' (0-3).
        date_from: ISO date string (YYYY-MM-DD) — include contacts created on/after.
        date_to: ISO date string (YYYY-MM-DD) — include contacts created on/before.
        has_interactions: Filter to contacts with (True) or without (False) any interactions.
        interaction_days: Filter to contacts with last_interaction_at within N days.

    Returns:
        A SQLAlchemy select statement (not yet executed).
    """
    base_query = select(Contact).where(Contact.user_id == user_id)
    if archived_only:
        base_query = base_query.where(Contact.priority_level == "archived")
    else:
        base_query = base_query.where(Contact.priority_level != "archived")

    if search:
        # Escape SQL LIKE wildcards to prevent wildcard injection
        safe_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe_search}%"
        interaction_match = exists(
            select(Interaction.id).where(
                Interaction.contact_id == Contact.id,
                Interaction.content_preview.ilike(pattern),
            )
        )
        base_query = base_query.where(
            or_(
                Contact.full_name.ilike(pattern),
                Contact.given_name.ilike(pattern),
                Contact.family_name.ilike(pattern),
                func.concat(func.coalesce(Contact.given_name, ""), " ", func.coalesce(Contact.family_name, "")).ilike(pattern),
                Contact.company.ilike(pattern),
                Contact.title.ilike(pattern),
                Contact.twitter_handle.ilike(pattern),
                Contact.telegram_username.ilike(pattern),
                Contact.twitter_bio.ilike(pattern),
                Contact.telegram_bio.ilike(pattern),
                Contact.notes.ilike(pattern),
                Contact.source.ilike(pattern),
                cast(Contact.emails, String).ilike(pattern),
                cast(Contact.phones, String).ilike(pattern),
                interaction_match,
            )
        )

    if tag:
        base_query = base_query.where(Contact.tags.any(tag.lower()))

    if source:
        base_query = base_query.where(Contact.source == source)

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=UTC)
            base_query = base_query.where(Contact.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
            base_query = base_query.where(Contact.created_at < dt_to)
        except ValueError:
            pass

    if has_interactions is True:
        base_query = base_query.where(Contact.last_interaction_at.isnot(None))
    elif has_interactions is False:
        base_query = base_query.where(Contact.last_interaction_at.is_(None))

    if interaction_days is not None and interaction_days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=interaction_days)
        base_query = base_query.where(Contact.last_interaction_at >= cutoff)

    if has_birthday is True:
        base_query = base_query.where(
            Contact.birthday.isnot(None),
            Contact.birthday != "",
        )
    elif has_birthday is False:
        base_query = base_query.where(
            or_(Contact.birthday.is_(None), Contact.birthday == ""),
        )

    if score == "strong":
        base_query = base_query.where(Contact.relationship_score >= 8)
    elif score == "active":
        base_query = base_query.where(
            Contact.relationship_score >= 4, Contact.relationship_score <= 7
        )
    elif score == "dormant":
        base_query = base_query.where(Contact.relationship_score <= 3)

    if priority and priority in ("high", "medium", "low"):
        base_query = base_query.where(Contact.priority_level == priority)

    return base_query


async def list_contacts_paginated(
    db: AsyncSession,
    user_id: object,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    tag: str | None = None,
    source: str | None = None,
    score: str | None = None,
    priority: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    has_interactions: bool | None = None,
    interaction_days: int | None = None,
    has_birthday: bool | None = None,
    archived_only: bool = False,
    sort_by: str = "score",
) -> ContactListResponse:
    """Execute a filtered, paginated contact query and return the response model."""
    base_query = build_contact_filter_query(
        user_id,
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

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    if sort_by == "created":
        order_clause = [Contact.created_at.desc()]
    elif sort_by == "interaction":
        order_clause = [Contact.last_interaction_at.desc().nullslast()]
    elif sort_by == "activity":
        order_clause = [Contact.interaction_count.desc(), Contact.created_at.desc()]
    elif sort_by == "company":
        order_clause = [Contact.company.is_(None).asc(), Contact.company.asc(), Contact.created_at.desc()]
    elif sort_by == "birthday":
        # Sort by days until next birthday using MM-DD suffix.
        # birthday is stored as "MM-DD" or "YYYY-MM-DD"; right(birthday, 5) extracts "MM-DD".
        # Compare to today's MM-DD: if >= today, birthday is upcoming this year;
        # if < today, it already passed and wraps to next year (add 366 offset).
        from sqlalchemy import case
        today_mmdd = datetime.now(UTC).strftime("%m-%d")
        bday_mmdd = func.right(Contact.birthday, 5)
        days_proxy = case(
            (bday_mmdd >= today_mmdd, bday_mmdd),
            else_=func.concat("z", bday_mmdd),  # 'z' > any MM-DD, so past dates sort last
        )
        order_clause = [Contact.birthday.is_(None).asc(), days_proxy.asc()]
    elif sort_by == "overdue":
        # Sort by how long since last interaction (most overdue first)
        order_clause = [Contact.last_interaction_at.asc().nullsfirst(), Contact.relationship_score.asc()]
    else:
        order_clause = [Contact.relationship_score.desc(), Contact.created_at.desc()]

    offset = (page - 1) * page_size
    result = await db.execute(
        base_query.order_by(*order_clause).offset(offset).limit(page_size)
    )
    contacts = result.scalars().all()

    return ContactListResponse(
        data=[ContactResponse.model_validate(c) for c in contacts],
        error=None,
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total > 0 else 1,
        ),
    )
