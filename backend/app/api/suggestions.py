import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.user import User
from app.schemas.follow_up import FollowUpResponse

router = APIRouter(prefix="/api/v1/suggestions", tags=["suggestions"])


def envelope(data: object, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _suggestion_with_contact(
    suggestion: FollowUpSuggestion, db: AsyncSession
) -> dict:
    """Attach basic contact info to a serialised suggestion."""
    contact_result = await db.execute(
        select(Contact).where(Contact.id == suggestion.contact_id)
    )
    contact = contact_result.scalar_one_or_none()

    data = FollowUpResponse.model_validate(suggestion).model_dump()
    data["contact"] = (
        {
            "id": str(contact.id),
            "full_name": contact.full_name,
            "given_name": contact.given_name,
            "family_name": contact.family_name,
            "company": contact.company,
            "title": contact.title,
            "last_interaction_at": (
                contact.last_interaction_at.isoformat()
                if contact.last_interaction_at
                else None
            ),
        }
        if contact
        else None
    )
    return data


# ---------------------------------------------------------------------------
# GET /api/v1/suggestions
# ---------------------------------------------------------------------------


@router.get("", response_model=dict)
async def list_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List pending follow-up suggestions for the current user, with contact info."""
    result = await db.execute(
        select(FollowUpSuggestion)
        .where(
            FollowUpSuggestion.user_id == current_user.id,
            FollowUpSuggestion.status == "pending",
        )
        .order_by(FollowUpSuggestion.created_at.desc())
    )
    suggestions = result.scalars().all()

    items = [await _suggestion_with_contact(s, db) for s in suggestions]
    return envelope(items, meta={"count": len(items)})


# ---------------------------------------------------------------------------
# GET /api/v1/suggestions/digest
# ---------------------------------------------------------------------------


@router.get("/digest", response_model=dict)
async def get_digest(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the weekly digest data for the current user."""
    from app.services.followup_engine import get_weekly_digest

    suggestions = await get_weekly_digest(current_user.id, db)
    items = [await _suggestion_with_contact(s, db) for s in suggestions]
    return envelope(items, meta={"count": len(items)})


# ---------------------------------------------------------------------------
# PUT /api/v1/suggestions/{suggestion_id}
# ---------------------------------------------------------------------------


class SnoozeBody(BaseModel):
    status: str
    scheduled_for: datetime | None = None
    snooze_until: datetime | None = None


@router.put("/{suggestion_id}", response_model=dict)
async def update_suggestion(
    suggestion_id: uuid.UUID,
    update_in: SnoozeBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update suggestion status.

    - **sent**: marks sent, updates contact.last_followup_at
    - **snoozed**: accepts snooze_until or scheduled_for datetime
    - **dismissed**: marks dismissed
    """
    result = await db.execute(
        select(FollowUpSuggestion).where(
            FollowUpSuggestion.id == suggestion_id,
            FollowUpSuggestion.user_id == current_user.id,
        )
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")

    allowed_statuses = {"sent", "snoozed", "dismissed", "pending"}
    if update_in.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Status must be one of: {', '.join(sorted(allowed_statuses))}",
        )

    suggestion.status = update_in.status

    if update_in.status == "snoozed":
        snooze_dt = update_in.snooze_until or update_in.scheduled_for
        if snooze_dt is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="snooze_until is required when status is 'snoozed'",
            )
        suggestion.scheduled_for = snooze_dt

    elif update_in.status == "sent":
        # Update contact's last_followup_at timestamp
        contact_result = await db.execute(
            select(Contact).where(Contact.id == suggestion.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if contact:
            from datetime import UTC

            contact.last_followup_at = datetime.now(UTC)
            await db.flush()
            await db.refresh(contact)

    elif update_in.status == "dismissed":
        pass  # No additional side effects

    await db.flush()
    await db.refresh(suggestion)
    return envelope(FollowUpResponse.model_validate(suggestion).model_dump())


# ---------------------------------------------------------------------------
# POST /api/v1/suggestions/generate
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=dict)
async def generate_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Manually trigger suggestion generation for the current user."""
    from app.services.followup_engine import generate_suggestions as _generate

    suggestions = await _generate(current_user.id, db)
    await db.commit()

    items = [FollowUpResponse.model_validate(s).model_dump() for s in suggestions]
    return envelope(items, meta={"generated": len(items)})
