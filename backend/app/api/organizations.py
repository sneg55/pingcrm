"""Organization CRUD + list + merge + stats endpoints."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.organization import Organization
from app.models.user import User
from app.schemas.responses import Envelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OrgContact(BaseModel):
    id: str
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    title: str | None = None
    avatar_url: str | None = None
    relationship_score: int = 0
    last_interaction_at: datetime | None = None


class OrganizationResponse(BaseModel):
    id: str
    name: str
    domain: str | None = None
    industry: str | None = None
    location: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Populated from mat view when listing
    contact_count: int = 0
    avg_relationship_score: int = 0
    total_interactions: int = 0
    last_interaction_at: datetime | None = None
    # Populated when detail is requested
    contacts: list[OrgContact] | None = None


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1)
    domain: str | None = None
    industry: str | None = None
    location: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    notes: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    industry: str | None = None
    location: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    notes: str | None = None


class OrganizationListMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class MergeOrganizationsRequest(BaseModel):
    source_ids: list[str] = Field(..., min_length=1, description="Organization IDs to merge away")
    target_id: str = Field(..., description="Organization ID to keep")


class MergeOrganizationsResult(BaseModel):
    target_id: str
    target_name: str
    contacts_updated: int
    source_organizations_merged: int


class OrgStatsResponse(BaseModel):
    organization_id: str
    contact_count: int = 0
    avg_relationship_score: int = 0
    total_interactions: int = 0
    last_interaction_at: datetime | None = None


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
        # Mat view may not exist yet (migration not run)
        logger.warning("organization_stats_mv not available, returning empty stats")
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

    # Move contacts from sources to target
    move_result = await db.execute(
        update(Contact)
        .where(
            Contact.organization_id.in_(source_ids),
            Contact.user_id == current_user.id,
        )
        .values(organization_id=target_id, company=target_org.name)
    )

    # Delete source organizations
    delete_result = await db.execute(
        delete(Organization).where(
            Organization.id.in_(source_ids),
            Organization.user_id == current_user.id,
        )
    )

    return _envelope({
        "target_id": str(target_id),
        "target_name": target_org.name,
        "contacts_updated": move_result.rowcount,
        "source_organizations_merged": delete_result.rowcount,
    })


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

    # Fetch contacts (capped to avoid unbounded response size)
    contacts_result = await db.execute(
        select(Contact)
        .where(Contact.organization_id == org.id, Contact.user_id == current_user.id, Contact.priority_level != "archived")
        .order_by(Contact.relationship_score.desc())
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


