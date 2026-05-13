"""Endpoints for organization deduplication."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.org_identity_match import OrgIdentityMatch
from app.models.organization import Organization
from app.models.user import User
from app.schemas.org_identity_match import (
    DismissOrgMatchResult,
    MergeOrgMatchRequest,
    MergeOrgMatchResult,
    OrgIdentityMatchData,
    OrgSummary,
    ScanOrgsResult,
)
from app.schemas.responses import Envelope
from app.services.org_identity_resolution import merge_org_pair, scan_org_duplicates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


@router.post("/scan-duplicates", response_model=Envelope[ScanOrgsResult])
async def scan_duplicates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ScanOrgsResult]:
    """Run a fresh duplicate scan over the current user's orgs."""
    summary = await scan_org_duplicates(current_user.id, db)
    return {"data": summary, "error": None}


async def _org_summary(org: Organization, db: AsyncSession) -> OrgSummary:
    count_result = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.organization_id == org.id)
    )
    contact_count = count_result.scalar() or 0
    return OrgSummary(
        id=str(org.id),
        name=org.name,
        domain=org.domain,
        logo_url=org.logo_url,
        linkedin_url=org.linkedin_url,
        website=org.website,
        twitter_handle=org.twitter_handle,
        contact_count=contact_count,
    )


@router.get("/duplicates", response_model=Envelope[list[OrgIdentityMatchData]])
async def list_duplicates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[OrgIdentityMatchData]]:
    """Return all pending_review match pairs for the current user."""
    result = await db.execute(
        select(OrgIdentityMatch)
        .where(
            OrgIdentityMatch.user_id == current_user.id,
            OrgIdentityMatch.status == "pending_review",
        )
        .order_by(OrgIdentityMatch.match_score.desc())
    )
    matches = list(result.scalars().all())

    if not matches:
        return {"data": [], "error": None}

    org_ids = {m.org_a_id for m in matches} | {m.org_b_id for m in matches}
    orgs_result = await db.execute(
        select(Organization).where(Organization.id.in_(org_ids))
    )
    org_by_id = {o.id: o for o in orgs_result.scalars().all()}

    data: list[OrgIdentityMatchData] = []
    for m in matches:
        org_a = org_by_id.get(m.org_a_id)
        org_b = org_by_id.get(m.org_b_id)
        if org_a is None or org_b is None:
            continue
        data.append(OrgIdentityMatchData(
            id=str(m.id),
            match_score=m.match_score,
            match_method=m.match_method,
            status=m.status,
            org_a=await _org_summary(org_a, db),
            org_b=await _org_summary(org_b, db),
            created_at=m.created_at,
        ))

    return {"data": data, "error": None}


@router.post(
    "/duplicates/{match_id}/merge",
    response_model=Envelope[MergeOrgMatchResult],
)
async def merge_match(
    match_id: uuid.UUID,
    payload: MergeOrgMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[MergeOrgMatchResult]:
    """User confirms a match: merge source -> target."""
    result = await db.execute(
        select(OrgIdentityMatch).where(
            OrgIdentityMatch.id == match_id,
            OrgIdentityMatch.user_id == current_user.id,
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    target_id = uuid.UUID(payload.target_id)
    if target_id not in (match.org_a_id, match.org_b_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_id must be one of the orgs in this match",
        )

    source_id = match.org_b_id if target_id == match.org_a_id else match.org_a_id

    target_res = await db.execute(
        select(Organization).where(
            Organization.id == target_id,
            Organization.user_id == current_user.id,
        )
    )
    target = target_res.scalar_one_or_none()
    source_res = await db.execute(
        select(Organization).where(
            Organization.id == source_id,
            Organization.user_id == current_user.id,
        )
    )
    source = source_res.scalar_one_or_none()
    if target is None or source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Update match row BEFORE the merge — merge_org_pair deletes the source
    # org which cascades to delete this match row via FK ON DELETE CASCADE.
    match.status = "merged"
    match.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    moved = await merge_org_pair(target, source, db)
    await db.flush()

    return {
        "data": MergeOrgMatchResult(
            merged=True, target_id=str(target_id), contacts_moved=moved,
        ),
        "error": None,
    }
