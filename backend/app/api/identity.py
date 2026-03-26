"""Identity Resolution API router."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.identity_match import IdentityMatch
from app.models.user import User
from app.schemas.responses import (
    Envelope,
    IdentityMatchData,
    ScanResultData,
)
from app.services.identity_resolution import (
    find_deterministic_matches,
    find_probabilistic_matches,
    merge_contacts,
)

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])


def envelope(data: Any, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


def _contact_to_dict(contact: Contact) -> dict:
    return {
        "id": str(contact.id),
        "full_name": contact.full_name,
        "given_name": contact.given_name,
        "family_name": contact.family_name,
        "emails": contact.emails or [],
        "phones": contact.phones or [],
        "company": contact.company,
        "title": contact.title,
        "twitter_handle": contact.twitter_handle,
        "telegram_username": contact.telegram_username,
        "linkedin_url": contact.linkedin_url,
        "tags": contact.tags or [],
        "notes": contact.notes,
        "source": contact.source,
    }


async def _match_to_dict(match: IdentityMatch, db: AsyncSession) -> dict:
    # Load both contacts to include full data in the response
    res_a = await db.execute(select(Contact).where(Contact.id == match.contact_a_id))
    contact_a = res_a.scalar_one_or_none()

    contact_b = None
    if match.contact_b_id is not None:
        res_b = await db.execute(select(Contact).where(Contact.id == match.contact_b_id))
        contact_b = res_b.scalar_one_or_none()

    return {
        "id": str(match.id),
        "contact_a_id": str(match.contact_a_id),
        "contact_b_id": str(match.contact_b_id) if match.contact_b_id else None,
        "contact_a": _contact_to_dict(contact_a) if contact_a else None,
        "contact_b": _contact_to_dict(contact_b) if contact_b else None,
        "match_score": match.match_score,
        "match_method": match.match_method,
        "status": match.status,
        "created_at": match.created_at.isoformat(),
        "resolved_at": match.resolved_at.isoformat() if match.resolved_at else None,
    }


async def _batch_matches_to_dicts(matches: list[IdentityMatch], db: AsyncSession) -> list[dict]:
    """Serialize matches with batch-loaded contacts (avoids N+1)."""
    if not matches:
        return []
    contact_ids: set[uuid.UUID] = set()
    for m in matches:
        contact_ids.add(m.contact_a_id)
        if m.contact_b_id is not None:
            contact_ids.add(m.contact_b_id)

    result = await db.execute(select(Contact).where(Contact.id.in_(list(contact_ids))))
    contacts_by_id = {c.id: c for c in result.scalars().all()}

    items = []
    for match in matches:
        contact_a = contacts_by_id.get(match.contact_a_id)
        contact_b = contacts_by_id.get(match.contact_b_id) if match.contact_b_id else None
        items.append({
            "id": str(match.id),
            "contact_a_id": str(match.contact_a_id),
            "contact_b_id": str(match.contact_b_id) if match.contact_b_id else None,
            "contact_a": _contact_to_dict(contact_a) if contact_a else None,
            "contact_b": _contact_to_dict(contact_b) if contact_b else None,
            "match_score": match.match_score,
            "match_method": match.match_method,
            "status": match.status,
            "created_at": match.created_at.isoformat(),
            "resolved_at": match.resolved_at.isoformat() if match.resolved_at else None,
        })
    return items


@router.get("/matches", response_model=Envelope[list[IdentityMatchData]])
async def list_pending_matches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[IdentityMatchData]]:
    """List all pending identity matches for the authenticated user's contacts."""
    non_archived_sq = select(Contact.id).where(
        Contact.user_id == current_user.id,
        Contact.priority_level != "archived",
    )

    result = await db.execute(
        select(IdentityMatch).where(
            IdentityMatch.status == "pending_review",
            IdentityMatch.contact_a_id.in_(non_archived_sq),
            IdentityMatch.contact_b_id.isnot(None),
            IdentityMatch.contact_b_id.in_(non_archived_sq),
        )
    )
    user_matches = result.scalars().all()

    return envelope(
        await _batch_matches_to_dicts(user_matches, db),
        meta={"count": len(user_matches)},
    )


@router.post("/matches/{match_id}/merge", response_model=Envelope[IdentityMatchData])
async def confirm_merge(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[IdentityMatchData]:
    """Confirm and execute a pending identity match merge."""
    result = await db.execute(
        select(IdentityMatch).where(IdentityMatch.id == match_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    if match.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Match is not pending review (status={match.status})",
        )

    # Capture IDs before deletion.
    contact_a_id = match.contact_a_id
    contact_b_id = match.contact_b_id

    # Verify ownership.
    await _assert_contact_ownership(contact_a_id, current_user.id, db)
    await _assert_contact_ownership(contact_b_id, current_user.id, db)

    # Delete the pending match and re-merge via the service (which creates a
    # new "merged" IdentityMatch record).
    try:
        await db.delete(match)
        await db.flush()
        merged = await merge_contacts(contact_a_id, contact_b_id, db)
    except Exception:
        logger.exception(
            "confirm_merge failed for match %s (contacts %s, %s)",
            match_id, contact_a_id, contact_b_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Merge failed — check server logs for details",
        )

    return envelope(await _match_to_dict(merged, db))


@router.post("/matches/{match_id}/reject", response_model=Envelope[IdentityMatchData])
async def reject_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[IdentityMatchData]:
    """Reject a pending identity match (mark as rejected)."""
    result = await db.execute(
        select(IdentityMatch).where(IdentityMatch.id == match_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    if match.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Match is not pending review (status={match.status})",
        )

    await _assert_contact_ownership(match.contact_a_id, current_user.id, db)
    await _assert_contact_ownership(match.contact_b_id, current_user.id, db)

    match.status = "rejected"
    match.resolved_at = datetime.now(UTC)
    await db.flush()

    return envelope(await _match_to_dict(match, db))


@router.post("/scan", response_model=Envelope[ScanResultData])
async def trigger_scan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ScanResultData]:
    """Trigger a full identity resolution scan for the current user's contacts."""
    deterministic = await find_deterministic_matches(current_user.id, db)
    probabilistic = await find_probabilistic_matches(current_user.id, db)
    await db.flush()

    pending = [m for m in probabilistic if m.status == "pending_review"]
    auto = [m for m in probabilistic if m.status == "merged"]

    return envelope(
        {
            "auto_merged": len(deterministic) + len(auto),
            "pending_review": len(pending),
            "matches_found": len(deterministic) + len(probabilistic),
        },
        meta={
            "auto_merged_ids": [str(m.id) for m in deterministic + auto],
            "pending_review_ids": [str(m.id) for m in pending],
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _assert_contact_ownership(
    contact_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Contact {contact_id} does not belong to the current user",
        )
