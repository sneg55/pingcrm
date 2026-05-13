"""Organization CRUD + list + merge + stats endpoints."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.contact import Contact
from app.models.organization import Organization
from app.models.user import User
from app.schemas.responses import Envelope
from app.services.org_identity_resolution import merge_org_pair
from app.schemas.organization import (
    MergeOrganizationsRequest,
    MergeOrganizationsResult,
    OrgContact,
    OrgStatsResponse,
    OrganizationCreate,
    OrganizationListMeta,
    OrganizationResponse,
    OrganizationUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


def _envelope(data: Any, meta: dict | None = None) -> dict:
    return {"data": data, "error": None, "meta": meta}


def _org_to_dict(org: Organization, stats: dict | None = None) -> dict:
    """Convert Organization model + optional stats to response dict."""
    d = {
        "id": str(org.id),
        "name": org.name,
        "domain": org.domain,
        "industry": org.industry,
        "location": org.location,
        "website": org.website,
        "linkedin_url": org.linkedin_url,
        "twitter_handle": org.twitter_handle,
        "notes": org.notes,
        "logo_url": org.logo_url,
        "created_at": org.created_at,
        "updated_at": org.updated_at,
        "contact_count": 0,
        "avg_relationship_score": 0,
        "total_interactions": 0,
        "last_interaction_at": None,
    }
    if stats:
        d.update(stats)
    return d


async def _get_org_stats_map(db: AsyncSession, org_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Fetch stats from materialized view for given org IDs."""
    if not org_ids:
        return {}
    try:
        # Use a SAVEPOINT so a missing mat-view error doesn't poison the outer
        # transaction (PostgreSQL marks the whole txn as aborted on any error).
        async with db.begin_nested():
            result = await db.execute(
                text(
                    "SELECT organization_id, contact_count, avg_relationship_score, "
                    "total_interactions, last_interaction_at "
                    "FROM organization_stats_mv WHERE organization_id = ANY(:ids)"
                ),
                {"ids": org_ids},
            )
            stats_map = {}
            for row in result.mappings().all():
                stats_map[row["organization_id"]] = {
                    "contact_count": row["contact_count"],
                    "avg_relationship_score": row["avg_relationship_score"],
                    "total_interactions": row["total_interactions"],
                    "last_interaction_at": row["last_interaction_at"],
                }
            return stats_map
    except Exception:
        logger.warning(
            "organization_stats_mv not available, returning empty stats",
            exc_info=True,
        )
        # Mat view may not exist yet (migration not run); SAVEPOINT ensures the
        # outer transaction is still usable after this failure.
        return {}


# ---------------------------------------------------------------------------
# POST /api/v1/organizations — Create
# ---------------------------------------------------------------------------


@router.post("", response_model=Envelope[OrganizationResponse], status_code=status.HTTP_201_CREATED)
async def create_organization(
    org_in: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    org = Organization(
        user_id=current_user.id,
        **org_in.model_dump(),
    )
    db.add(org)
    await db.flush()

    # Auto-assign contacts by domain if provided
    if org.domain:
        from app.services.organization_service import auto_assign_by_domain
        assigned = await auto_assign_by_domain(org, db)
        logger.info("create_organization: auto-assigned %d contacts by domain %s", assigned, org.domain)

    # Download logo from website or domain
    logo_source = org.website or org.domain
    if logo_source:
        from app.services.organization_service import download_org_logo
        logo_url = await download_org_logo(logo_source, org.id)
        if logo_url:
            org.logo_url = logo_url

    await db.refresh(org)
    return _envelope(_org_to_dict(org))


# ---------------------------------------------------------------------------
# GET /api/v1/organizations — List
# ---------------------------------------------------------------------------


@router.get("", response_model=Envelope[list[OrganizationResponse]])
async def list_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, description="Filter by name (case-insensitive)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return organizations with stats from materialized view.

    Excludes orgs that have zero active (non-archived) contacts.
    """
    # Subquery: orgs that have at least one non-archived contact
    active_org_ids = (
        select(Contact.organization_id)
        .where(
            Contact.organization_id.isnot(None),
            Contact.priority_level != "archived",
        )
        .group_by(Contact.organization_id)
        .correlate(None)
        .scalar_subquery()
    )

    stmt = (
        select(Organization)
        .where(
            Organization.user_id == current_user.id,
            Organization.id.in_(active_org_ids),
        )
        .order_by(Organization.name)
    )

    if search:
        stmt = stmt.where(Organization.name.ilike(f"%{search}%"))

    # Get total count
    count_stmt = (
        select(func.count())
        .select_from(Organization)
        .where(
            Organization.user_id == current_user.id,
            Organization.id.in_(active_org_ids),
        )
    )
    if search:
        count_stmt = count_stmt.where(Organization.name.ilike(f"%{search}%"))
    total = (await db.execute(count_stmt)).scalar() or 0
    total_pages = max(1, (total + page_size - 1) // page_size)

    # Paginate
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    orgs = list(result.scalars().all())

    # Fetch stats
    stats_map = await _get_org_stats_map(db, [o.id for o in orgs])

    data = [_org_to_dict(org, stats_map.get(org.id)) for org in orgs]

    return _envelope(
        data,
        meta={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    )


# ---------------------------------------------------------------------------
# POST /api/v1/organizations/merge  (must be before /{org_id} routes)
# POST /api/v1/organizations/backfill-logos  (must be before /{org_id} routes)
# ---------------------------------------------------------------------------


@router.post("/merge", response_model=Envelope[MergeOrganizationsResult])
async def merge_organizations(
    payload: MergeOrganizationsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Merge source organizations into the target organization.

    Moves all contacts from source orgs to target, then deletes sources.
    """
    source_ids = [uuid.UUID(sid) for sid in payload.source_ids if sid != payload.target_id]
    target_id = uuid.UUID(payload.target_id)

    if not source_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_ids must contain at least one ID different from target_id",
        )

    # Verify target exists and belongs to user
    result = await db.execute(
        select(Organization).where(
            Organization.id == target_id, Organization.user_id == current_user.id
        )
    )
    target_org = result.scalar_one_or_none()
    if not target_org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target organization not found")

    total_moved = 0
    sources_merged = 0
    for source_id in source_ids:
        source_result = await db.execute(
            select(Organization).where(
                Organization.id == source_id,
                Organization.user_id == current_user.id,
            )
        )
        source_org = source_result.scalar_one_or_none()
        if source_org is None:
            continue
        moved = await merge_org_pair(target_org, source_org, db)
        total_moved += moved
        sources_merged += 1

    return _envelope({
        "target_id": str(target_id),
        "target_name": target_org.name,
        "contacts_updated": total_moved,
        "source_organizations_merged": sources_merged,
    })


@router.post("/backfill-logos", response_model=Envelope[dict])
async def backfill_org_logos_endpoint(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Dispatch a background task to backfill logos for orgs that have none.

    Returns immediately; the actual work happens asynchronously in Celery.
    """
    from app.services.tasks import backfill_org_logos_task
    backfill_org_logos_task.delay()
    return _envelope({"queued": True})


# ---------------------------------------------------------------------------
# GET /api/v1/organizations/{id} — Detail
# ---------------------------------------------------------------------------


@router.get("/{org_id}", response_model=Envelope[OrganizationResponse])
async def get_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id, Organization.user_id == current_user.id
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Get stats
    stats_map = await _get_org_stats_map(db, [org.id])
    org_dict = _org_to_dict(org, stats_map.get(org.id))

    # Fetch contacts (capped to avoid unbounded response size).
    # Active contacts first (active-first grouping is stable across the 200-cap),
    # then archived; within each group, order by relationship_score desc.
    archived_flag = (Contact.priority_level == "archived")
    contacts_result = await db.execute(
        select(Contact)
        .where(Contact.organization_id == org.id, Contact.user_id == current_user.id)
        .order_by(archived_flag.asc(), Contact.relationship_score.desc())
        .limit(200)
    )
    org_dict["contacts"] = [
        {
            "id": str(c.id),
            "full_name": c.full_name,
            "given_name": c.given_name,
            "family_name": c.family_name,
            "title": c.title,
            "avatar_url": c.avatar_url,
            "relationship_score": c.relationship_score,
            "priority_level": c.priority_level,
            "last_interaction_at": c.last_interaction_at,
        }
        for c in contacts_result.scalars().all()
    ]

    return _envelope(org_dict)


# ---------------------------------------------------------------------------
# GET /api/v1/organizations/{id}/stats — Stats from mat view
# ---------------------------------------------------------------------------


@router.get("/{org_id}/stats", response_model=Envelope[OrgStatsResponse])
async def get_organization_stats(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Verify org belongs to user
    result = await db.execute(
        select(Organization.id).where(
            Organization.id == org_id, Organization.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    stats_map = await _get_org_stats_map(db, [org_id])
    stats = stats_map.get(org_id, {
        "contact_count": 0,
        "avg_relationship_score": 0,
        "total_interactions": 0,
        "last_interaction_at": None,
    })

    return _envelope({"organization_id": str(org_id), **stats})


# ---------------------------------------------------------------------------
# PATCH /api/v1/organizations/{id} — Update
# ---------------------------------------------------------------------------


@router.patch("/{org_id}", response_model=Envelope[OrganizationResponse])
async def update_organization(
    org_id: uuid.UUID,
    org_in: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id, Organization.user_id == current_user.id
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    update_data = org_in.model_dump(exclude_unset=True)
    domain_changed = "domain" in update_data and update_data["domain"] != org.domain
    website_changed = "website" in update_data and update_data["website"] != org.website

    for field, value in update_data.items():
        setattr(org, field, value)

    # If name changed, update company field on all linked contacts
    if "name" in update_data:
        await db.execute(
            update(Contact)
            .where(Contact.organization_id == org.id, Contact.user_id == current_user.id)
            .values(company=org.name)
        )

    # If domain changed, auto-assign unlinked contacts
    if domain_changed and org.domain:
        from app.services.organization_service import auto_assign_by_domain
        await auto_assign_by_domain(org, db)

    # Re-download logo if website or domain changed
    if website_changed or domain_changed:
        logo_source = org.website or org.domain
        if logo_source:
            from app.services.organization_service import download_org_logo
            logo_url = await download_org_logo(logo_source, org.id)
            if logo_url:
                org.logo_url = logo_url

    await db.flush()
    await db.refresh(org)
    return _envelope(_org_to_dict(org))


# ---------------------------------------------------------------------------
# DELETE /api/v1/organizations/{id}
# ---------------------------------------------------------------------------


@router.delete("/{org_id}", response_model=Envelope[dict])
async def delete_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id, Organization.user_id == current_user.id
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Clear organization_id on linked contacts (FK is SET NULL, but be explicit)
    await db.execute(
        update(Contact).where(Contact.organization_id == org.id).values(organization_id=None)
    )
    await db.execute(delete(Organization).where(Organization.id == org.id))

    return _envelope({"id": str(org_id), "deleted": True})


# ---------------------------------------------------------------------------
# POST /api/v1/organizations/{id}/refresh-logo
# ---------------------------------------------------------------------------

_LOGO_REFRESH_TTL = 3600  # 1 hour


@router.post("/{org_id}/refresh-logo", response_model=Envelope[dict])
async def refresh_org_logo(
    org_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 1h rate limit"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Re-download the organization favicon/logo. Rate-limited to once per hour per org."""
    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id, Organization.user_id == current_user.id
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    r = get_redis()
    cache_key = f"org_logo_refresh:{org_id}"
    if not force and await r.exists(cache_key):
        return _envelope({"logo_url": org.logo_url, "refreshed": False, "skipped": True, "reason": "refreshed_recently"})

    logo_source = org.website or org.domain
    if not logo_source:
        return _envelope({"logo_url": org.logo_url, "refreshed": False, "skipped": True, "reason": "no_domain_or_website"})

    from app.services.organization_service import download_org_logo
    logo_url = await download_org_logo(logo_source, org.id)
    if logo_url:
        org.logo_url = logo_url
        await db.flush()

    await r.setex(cache_key, _LOGO_REFRESH_TTL, "1")
    return _envelope({"logo_url": org.logo_url, "refreshed": True})


