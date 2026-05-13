"""Pydantic schemas for the org dedup endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrgSummary(BaseModel):
    """Compact org representation for the duplicate-pair card."""
    id: str
    name: str
    domain: str | None = None
    logo_url: str | None = None
    linkedin_url: str | None = None
    website: str | None = None
    twitter_handle: str | None = None
    contact_count: int = 0


class OrgIdentityMatchData(BaseModel):
    id: str
    match_score: float
    match_method: str
    status: str
    org_a: OrgSummary
    org_b: OrgSummary
    created_at: datetime


class ScanOrgsResult(BaseModel):
    matches_found: int
    auto_merged: int
    pending_review: int


class MergeOrgMatchRequest(BaseModel):
    target_id: str  # must equal org_a_id or org_b_id on the match


class MergeOrgMatchResult(BaseModel):
    merged: bool
    target_id: str
    contacts_moved: int


class DismissOrgMatchResult(BaseModel):
    dismissed: bool
