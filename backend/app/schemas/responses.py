"""Shared response envelope and typed payload schemas for all API endpoints.

Usage
-----
from app.schemas.responses import Envelope, SyncStartedData, ...

Each endpoint declares its response_model as Envelope[SomePayloadType].
The generic Envelope carries data / error / meta at the top level.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.schemas.contact import PaginationMeta

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generic envelope
# ---------------------------------------------------------------------------


class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    error: str | None = None
    meta: dict | None = None


# ---------------------------------------------------------------------------
# contacts.py payload types
# ---------------------------------------------------------------------------


class ContactStatsData(BaseModel):
    total: int
    strong: int
    active: int
    dormant: int
    interactions_this_week: int = 0
    interactions_last_week: int = 0
    active_last_week: int = 0


class DeletedData(BaseModel):
    id: str
    deleted: bool


class DuplicateContactData(BaseModel):
    id: str
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    emails: list[str] = []
    phones: list[str] = []
    company: str | None = None
    title: str | None = None
    twitter_handle: str | None = None
    telegram_username: str | None = None
    score: float


class MergedContactData(BaseModel):
    id: str
    full_name: str | None = None
    merged_contact_id: str


class CsvImportResult(BaseModel):
    created: list[dict]
    errors: list[str]


class LinkedInImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]


class LinkedInMessagesImportResult(BaseModel):
    new_interactions: int
    skipped: int
    unmatched: int
    unmatched_names: list[str]


class BackfillItem(BaseModel):
    contact_id: str
    linkedin_profile_id: str
    linkedin_url: str | None = None


class LinkedInPushResult(BaseModel):
    contacts_created: int
    contacts_updated: int
    interactions_created: int
    interactions_skipped: int
    backfill_needed: list[BackfillItem] = []


class SyncStartedData(BaseModel):
    status: str


class ScoresRecalculatedData(BaseModel):
    updated: int


class BioRefreshData(BaseModel):
    twitter_bio_changed: bool | None = None
    telegram_bio_changed: bool | None = None
    skipped: bool | None = None
    reason: str | None = None


class AvatarRefreshData(BaseModel):
    avatar_url: str | None = None
    changed: bool = False
    skipped: bool = False
    reason: str | None = None


class SendMessageData(BaseModel):
    sent: bool
    channel: str
    interaction_id: str | None = None


class EnrichData(BaseModel):
    fields_updated: list[str]
    source: str = "apollo"


# ---------------------------------------------------------------------------
# Auto-tagging payload types
# ---------------------------------------------------------------------------


class TaxonomyResult(BaseModel):
    categories: dict[str, list[str]]
    total_tags: int
    status: str  # "draft" | "approved"


class AutoTagResult(BaseModel):
    tags_added: list[str]
    all_tags: list[str]


class ApplyTagsResult(BaseModel):
    tagged_count: int
    task_id: str | None = None


# ---------------------------------------------------------------------------
# suggestions.py payload types
# ---------------------------------------------------------------------------


class RegenerateResult(BaseModel):
    suggested_message: str
    suggested_channel: str


# ---------------------------------------------------------------------------
# identity.py payload types
# ---------------------------------------------------------------------------


class ContactSummaryData(BaseModel):
    id: str
    full_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    emails: list[str] = []
    phones: list[str] = []
    company: str | None = None
    title: str | None = None
    twitter_handle: str | None = None
    telegram_username: str | None = None
    linkedin_url: str | None = None
    tags: list[str] = []
    notes: str | None = None
    source: str | None = None


class IdentityMatchData(BaseModel):
    id: str
    contact_a_id: str
    contact_b_id: str | None = None
    contact_a: ContactSummaryData | None = None
    contact_b: ContactSummaryData | None = None
    match_score: float | None = None
    match_method: str | None = None
    status: str
    created_at: str
    resolved_at: str | None = None


class ScanResultData(BaseModel):
    auto_merged: int
    pending_review: int
    matches_found: int


# ---------------------------------------------------------------------------
# notifications.py payload types
# ---------------------------------------------------------------------------


class NotificationData(BaseModel):
    id: str
    notification_type: str
    title: str
    body: str | None = None
    read: bool
    link: str | None = None
    created_at: str | None = None


class NotificationListResponse(BaseModel):
    data: list[NotificationData]
    error: str | None = None
    meta: PaginationMeta


class UnreadCountData(BaseModel):
    count: int


class MarkedData(BaseModel):
    marked: bool


class NotificationReadData(BaseModel):
    id: str
    read: bool


# ---------------------------------------------------------------------------
# telegram.py payload types
# ---------------------------------------------------------------------------


class TelegramConnectData(BaseModel):
    phone_code_hash: str


class TelegramVerifyData(BaseModel):
    connected: bool
    requires_2fa: bool | None = None
    username: str | None = None


class TelegramConnectedData(BaseModel):
    connected: bool
    username: str | None = None


# ---------------------------------------------------------------------------
# twitter.py payload types
# ---------------------------------------------------------------------------


class TwitterAuthUrlData(BaseModel):
    url: str
    state: str


class TwitterConnectedData(BaseModel):
    connected: bool
    username: str | None = None


# ---------------------------------------------------------------------------
# auth.py payload types
# ---------------------------------------------------------------------------


class GoogleAccountData(BaseModel):
    id: str
    email: str
    created_at: str | None = None


class UserWithAccountsData(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    created_at: datetime
    google_connected: bool = False
    google_email: str | None = None
    telegram_connected: bool = False
    telegram_username: str | None = None
    twitter_connected: bool = False
    twitter_username: str | None = None
    linkedin_extension_paired_at: datetime | None = None
    google_accounts: list[GoogleAccountData] = []


class OAuthUrlData(BaseModel):
    url: str
    state: str


class TokenData(BaseModel):
    access_token: str
    token_type: str


# ---------------------------------------------------------------------------
# MCP server payload types
# ---------------------------------------------------------------------------


class McpKeyData(BaseModel):
    key: str


class McpKeyRevokedData(BaseModel):
    revoked: bool


class McpKeyStatusData(BaseModel):
    has_key: bool
