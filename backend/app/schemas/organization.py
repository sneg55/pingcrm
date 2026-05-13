"""Pydantic schemas for the organizations API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrgContact(BaseModel):
    id: str
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    title: str | None = None
    avatar_url: str | None = None
    relationship_score: int = 0
    priority_level: str = "medium"
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
    logo_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    contact_count: int = 0
    avg_relationship_score: int = 0
    total_interactions: int = 0
    last_interaction_at: datetime | None = None
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
