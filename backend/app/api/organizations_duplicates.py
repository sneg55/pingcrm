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
