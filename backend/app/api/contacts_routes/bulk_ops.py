"""Bulk update and 2nd-tier deletion endpoints for contacts.

Kept separate from crud.py because these endpoints are STATIC routes
(/bulk-update, /2nd-tier, /2nd-tier/count) and must be registered before
any parameterized /{contact_id} routes — see contacts.py for the include order.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.api.contacts_routes.shared import (
    Contact,
    Depends,
    Envelope,
    HTTPException,
    AsyncSession,
    User,
    envelope,
    get_current_user,
    get_db,
    select,
    status,
)
from app.schemas.contact import _normalize_tags

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])

VALID_PRIORITY_LEVELS = {"low", "medium", "high", "archived"}


class BulkUpdateBody(BaseModel):
    contact_ids: list[uuid.UUID] = Field(max_length=500)
    add_tags: list[str] | None = Field(default=None, max_length=50)
    remove_tags: list[str] | None = Field(default=None, max_length=50)
    priority_level: str | None = None
    company: str | None = None

    @field_validator("add_tags", "remove_tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _normalize_tags(v)


@router.post("/bulk-update", response_model=Envelope[dict])
async def bulk_update_contacts(
    body: BulkUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Bulk update tags and/or priority level for a set of contacts."""
    result = await db.execute(
        select(Contact).where(
            Contact.id.in_(body.contact_ids),
            Contact.user_id == current_user.id,
        )
    )
    contacts = result.scalars().all()

    if body.priority_level is not None and body.priority_level not in VALID_PRIORITY_LEVELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid priority_level. Must be one of: {', '.join(sorted(VALID_PRIORITY_LEVELS))}")

    archive_contact_ids: list[uuid.UUID] = []
    for contact in contacts:
        if body.add_tags:
            existing = set(contact.tags or [])
            contact.tags = list(existing | set(body.add_tags))
        if body.remove_tags:
            existing = set(contact.tags or [])
            contact.tags = list(existing - set(body.remove_tags))
        if body.company is not None:
            contact.company = body.company
        if body.priority_level is not None:
            contact.priority_level = body.priority_level
            if body.priority_level == "archived":
                archive_contact_ids.append(contact.id)

    if archive_contact_ids:
        from app.models.follow_up import FollowUpSuggestion
        pending_result = await db.execute(
            select(FollowUpSuggestion).where(
                FollowUpSuggestion.contact_id.in_(archive_contact_ids),
                FollowUpSuggestion.status == "pending",
            )
        )
        for suggestion in pending_result.scalars().all():
            suggestion.status = "dismissed"
            suggestion.dismissed_by = "system"

    await db.flush()
    return envelope({"updated": len(contacts)})


@router.delete("/2nd-tier", response_model=Envelope[dict])
async def delete_2nd_tier_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Delete all contacts tagged as '2nd tier' for the current user."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == current_user.id,
            Contact.tags.contains(["2nd tier"]),
        )
    )
    contacts = result.scalars().all()

    if not contacts:
        return envelope({"deleted_count": 0})

    for contact in contacts:
        await db.delete(contact)

    await db.flush()
    return envelope({"deleted_count": len(contacts)})


@router.get("/2nd-tier/count", response_model=Envelope[dict])
async def count_2nd_tier_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Count contacts tagged as '2nd tier' for the current user."""
    from sqlalchemy import func as sa_func

    result = await db.execute(
        select(sa_func.count()).select_from(Contact).where(
            Contact.user_id == current_user.id,
            Contact.tags.contains(["2nd tier"]),
        )
    )
    count = result.scalar() or 0
    return envelope({"count": count})
