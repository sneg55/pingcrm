import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


def _normalize_tags(tags: list[str]) -> list[str]:
    """Lowercase, strip, deduplicate tags while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        normalized = t.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


class ContactBase(BaseModel):
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    emails: list[str] = []
    phones: list[str] = []
    company: str | None = None
    title: str | None = None
    twitter_handle: str | None = None
    twitter_bio: str | None = None
    telegram_username: str | None = None
    telegram_bio: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    linkedin_profile_id: str | None = None
    linkedin_headline: str | None = None
    linkedin_bio: str | None = None
    avatar_url: str | None = None
    birthday: str | None = None
    tags: list[str] = []
    notes: str | None = None
    priority_level: str = "medium"
    source: str | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        return _normalize_tags(v)


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    emails: list[str] | None = None
    phones: list[str] | None = None
    company: str | None = None
    title: str | None = None
    twitter_handle: str | None = None
    twitter_bio: str | None = None
    telegram_username: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    linkedin_profile_id: str | None = None
    linkedin_headline: str | None = None
    linkedin_bio: str | None = None
    birthday: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    priority_level: str | None = None
    source: str | None = None
    organization_id: uuid.UUID | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _normalize_tags(v)


class ContactResponse(ContactBase):
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID | None = None
    relationship_score: int
    interaction_count: int = 0
    last_interaction_at: datetime | None = None
    last_followup_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class ContactListResponse(BaseModel):
    data: list[ContactResponse]
    error: str | None = None
    meta: PaginationMeta
