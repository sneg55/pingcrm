"""Identity Resolution API router."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.identity_match import IdentityMatch
from app.models.user import User
from app.services.identity_resolution import (
    find_deterministic_matches,
    find_probable_matches,
    merge_contacts,
)

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])


def envelope(data: Any, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


def _match_to_dict(match: IdentityMatch) -> dict:
    return {
        "id": str(match.id),
        "contact_a_id": str(match.contact_a_id),
        "contact_b_id": str(match.contact_b_id),
        "match_score": match.match_score,
        "match_method": match.match_method,
        "status": match.status,
        "created_at": match.created_at.isoformat(),
        "resolved_at": match.resolved_at.isoformat() if match.resolved_at else None,
    }


@router.get("/matches", response_model=dict)
async def list_pending_matches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List all pending identity matches for the authenticated user's contacts."""
    # Fetch contact ids belonging to this user.
    contact_ids_result = await db.execute(
        select(Contact.id).where(Contact.user_id == current_user.id)
    )
    contact_ids = set(contact_ids_result.scalars().all())

    result = await db.execute(
        select(IdentityMatch).where(IdentityMatch.status == "pending_review")
    )
    matches = result.scalars().all()

    # Filter to only matches where both contacts belong to this user.
    user_matches = [
        m for m in matches
        if m.contact_a_id in contact_ids and m.contact_b_id in contact_ids
    ]

    return envelope(
        [_match_to_dict(m) for m in user_matches],
        meta={"count": len(user_matches)},
    )


@router.post("/matches/{match_id}/merge", response_model=dict)
async def confirm_merge(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
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
    await db.delete(match)
    await db.flush()

    merged = await merge_contacts(contact_a_id, contact_b_id, db)
    await db.commit()

    return envelope(_match_to_dict(merged))


@router.post("/matches/{match_id}/reject", response_model=dict)
async def reject_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
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
    await db.commit()

    return envelope(_match_to_dict(match))


@router.post("/scan", response_model=dict)
async def trigger_scan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Trigger a full identity resolution scan for the current user's contacts."""
    deterministic = await find_deterministic_matches(current_user.id, db)
    probabilistic = await find_probable_matches(current_user.id, db)
    await db.commit()

    return envelope(
        {
            "auto_merged": len(deterministic),
            "pending_review": len(probabilistic),
        },
        meta={
            "auto_merged_ids": [str(m.id) for m in deterministic],
            "pending_review_ids": [str(m.id) for m in probabilistic],
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
