from __future__ import annotations

import uuid

from fastapi import APIRouter

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
from app.schemas.responses import DuplicateContactData, MergedContactData

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


@router.get("/{contact_id}/duplicates", response_model=Envelope[list[DuplicateContactData]])
async def find_contact_duplicates(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[DuplicateContactData]]:
    """Find possible duplicates for a specific contact."""
    from app.models.identity_match import IdentityMatch
    from app.services.identity_resolution import compute_adaptive_score, build_blocking_keys

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Load rejected pairs so we can exclude them
    rejected_result = await db.execute(
        select(IdentityMatch.contact_a_id, IdentityMatch.contact_b_id).where(
            IdentityMatch.status == "rejected",
            (IdentityMatch.contact_a_id == contact_id) | (IdentityMatch.contact_b_id == contact_id),
        )
    )
    rejected_ids: set[uuid.UUID] = set()
    for row in rejected_result.all():
        other = row[1] if row[0] == contact_id else row[0]
        if other:
            rejected_ids.add(other)

    # Get all other contacts for this user
    all_result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id, Contact.id != contact_id)
    )
    others: list[Contact] = list(all_result.scalars().all())

    # Use blocking keys for efficiency
    target_keys = set(build_blocking_keys(target))

    duplicates = []
    for other in others:
        if other.id in rejected_ids:
            continue
        other_keys = set(build_blocking_keys(other))
        if not target_keys & other_keys:
            continue
        score = compute_adaptive_score(target, other)
        if score < 0.40:
            continue
        duplicates.append({
            "id": str(other.id),
            "full_name": other.full_name,
            "given_name": other.given_name,
            "family_name": other.family_name,
            "emails": other.emails or [],
            "phones": other.phones or [],
            "company": other.company,
            "title": other.title,
            "twitter_handle": other.twitter_handle,
            "telegram_username": other.telegram_username,
            "score": round(score, 2),
        })

    duplicates.sort(key=lambda d: d["score"], reverse=True)
    return envelope(duplicates[:20])


@router.post("/{contact_id}/dismiss-duplicate/{other_id}")
async def dismiss_duplicate(
    contact_id: uuid.UUID,
    other_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dismiss a duplicate pair by creating a rejected IdentityMatch."""
    from app.models.identity_match import IdentityMatch
    from datetime import datetime, UTC

    # Verify ownership
    for cid in (contact_id, other_id):
        result = await db.execute(
            select(Contact).where(Contact.id == cid, Contact.user_id == current_user.id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Check if match already exists
    a_id, b_id = sorted([contact_id, other_id])
    existing = await db.execute(
        select(IdentityMatch).where(
            IdentityMatch.contact_a_id == a_id,
            IdentityMatch.contact_b_id == b_id,
        )
    )
    match = existing.scalar_one_or_none()
    if match:
        match.status = "rejected"
        match.resolved_at = datetime.now(UTC)
    else:
        db.add(IdentityMatch(
            contact_a_id=a_id,
            contact_b_id=b_id,
            match_score=0.0,
            match_method="manual_dismiss",
            status="rejected",
            resolved_at=datetime.now(UTC),
        ))
    await db.flush()
    return envelope({"dismissed": True})


@router.post("/{contact_id}/merge/{other_id}", response_model=Envelope[MergedContactData])
async def merge_contact_pair(
    contact_id: uuid.UUID,
    other_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[MergedContactData]:
    """Merge other_id into contact_id. Returns the surviving contact."""
    from app.services.identity_resolution import merge_contacts

    # Verify both contacts belong to current user
    for cid in (contact_id, other_id):
        result = await db.execute(
            select(Contact).where(Contact.id == cid, Contact.user_id == current_user.id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {cid} not found")

    match_record = await merge_contacts(contact_id, other_id, db)
    await db.flush()

    # Re-fetch the surviving contact
    result = await db.execute(select(Contact).where(Contact.id == match_record.contact_a_id))
    surviving = result.scalar_one()

    return envelope({
        "id": str(surviving.id),
        "full_name": surviving.full_name,
        "merged_contact_id": str(other_id),
    })
