import uuid
from datetime import datetime

from pydantic import BaseModel


class ContactBase(BaseModel):
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    emails: list[str] = []
    phones: list[str] = []
    company: str | None = None
    title: str | None = None
    twitter_handle: str | None = None
    telegram_username: str | None = None
    tags: list[str] = []
    notes: str | None = None
    priority_level: str = "medium"
    source: str | None = None


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
    telegram_username: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    priority_level: str | None = None
    source: str | None = None


class ContactResponse(ContactBase):
    id: uuid.UUID
    user_id: uuid.UUID
    relationship_score: int
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
