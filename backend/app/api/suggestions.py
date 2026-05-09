import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, get_extension_or_web_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.user import User
from app.schemas.follow_up import FollowUpResponse, FollowUpUpdate
from app.schemas.responses import Envelope, RegenerateResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/suggestions", tags=["suggestions"])


def envelope(data: object, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _enrich_suggestions_with_contacts(
    suggestions: list[FollowUpSuggestion], db: AsyncSession
) -> list[dict]:
    """Batch-load contacts and attach to serialised suggestions."""
    if not suggestions:
        return []
    contact_ids = list({s.contact_id for s in suggestions})
    result = await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
    )
    contacts_by_id = {c.id: c for c in result.scalars().all()}

    items = []
    for s in suggestions:
        data = FollowUpResponse.model_validate(s).model_dump()
        contact = contacts_by_id.get(s.contact_id)
        data["contact"] = (
            {
                "id": str(contact.id),
                "full_name": contact.full_name,
                "given_name": contact.given_name,
                "family_name": contact.family_name,
                "company": contact.company,
                "title": contact.title,
                "avatar_url": contact.avatar_url,
                "telegram_username": contact.telegram_username,
                "twitter_handle": contact.twitter_handle,
                "linkedin_profile_id": contact.linkedin_profile_id,
                "linkedin_url": contact.linkedin_url,
                "last_interaction_at": (
                    contact.last_interaction_at.isoformat()
                    if contact.last_interaction_at
                    else None
                ),
            }
            if contact
            else None
        )
        items.append(data)
    return items


# ---------------------------------------------------------------------------
# GET /api/v1/suggestions
# ---------------------------------------------------------------------------


@router.get("", response_model=Envelope[list[dict]])
async def list_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_extension_or_web_user),
) -> Envelope[list[dict]]:
    """List pending follow-up suggestions for the current user, with contact info."""
    # Auto-dismiss stale suggestions where the contact interacted after creation.
    # Tagged 'system' so the engine's 30-day cooldown doesn't apply.
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(FollowUpSuggestion)
        .where(
            FollowUpSuggestion.user_id == current_user.id,
            FollowUpSuggestion.status == "pending",
            FollowUpSuggestion.contact_id.in_(
                select(Contact.id).where(
                    Contact.last_interaction_at > FollowUpSuggestion.created_at
                )
            ),
        )
        .values(status="dismissed", dismissed_by="system")
    )
    await db.flush()

    result = await db.execute(
        select(FollowUpSuggestion)
        .join(Contact, FollowUpSuggestion.contact_id == Contact.id)
        .where(
            FollowUpSuggestion.user_id == current_user.id,
            FollowUpSuggestion.status == "pending",
            or_(Contact.tags.is_(None), ~Contact.tags.contains(["2nd tier"])),
            or_(
                func.coalesce(func.array_length(Contact.emails, 1), 0) > 0,
                Contact.twitter_handle.isnot(None),
                Contact.telegram_username.isnot(None),
                Contact.linkedin_url.isnot(None),
            ),
        )
        .order_by(FollowUpSuggestion.created_at.desc())
    )
    suggestions = result.scalars().all()

    items = await _enrich_suggestions_with_contacts(suggestions, db)
    return envelope(items, meta={"count": len(items)})


# ---------------------------------------------------------------------------
# GET /api/v1/suggestions/digest
# ---------------------------------------------------------------------------


@router.get("/digest", response_model=Envelope[list[dict]])
async def get_digest(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[dict]]:
    """Return the weekly digest data for the current user."""
    from app.services.followup_engine import get_weekly_digest

    suggestions = await get_weekly_digest(current_user.id, db)
    items = await _enrich_suggestions_with_contacts(suggestions, db)
    return envelope(items, meta={"count": len(items)})


# ---------------------------------------------------------------------------
# PUT /api/v1/suggestions/{suggestion_id}
# ---------------------------------------------------------------------------


class SuggestionUpdateBody(BaseModel):
    status: str
    scheduled_for: datetime | None = None
    snooze_until: datetime | None = None
    suggested_message: str | None = None
    suggested_channel: str | None = None


@router.put("/{suggestion_id}", response_model=Envelope[FollowUpResponse])
async def update_suggestion(
    suggestion_id: uuid.UUID,
    update_in: SuggestionUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[FollowUpResponse]:
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

    # Tag user-driven dismissals so the engine's 30-day cooldown applies.
    # System dismissals (sync paths) leave dismissed_by='system' and bypass cooldown.
    if update_in.status == "dismissed":
        suggestion.dismissed_by = "user"

    # Persist edited message/channel if provided
    if update_in.suggested_message is not None:
        suggestion.suggested_message = update_in.suggested_message
    if update_in.suggested_channel is not None:
        suggestion.suggested_channel = update_in.suggested_channel

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


@router.post("/generate", response_model=Envelope[list[FollowUpResponse]])
async def generate_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[FollowUpResponse]]:
    """Manually trigger suggestion generation for the current user.

    If no contacts have been scored yet, runs score recalculation first
    so the engine has data to work with.
    """
    from app.services.followup_engine import generate_suggestions as _generate
    from app.services.scoring import calculate_score

    # Check if scores exist — if all are 0, recalculate first
    scored_count = await db.execute(
        select(func.count()).where(
            Contact.user_id == current_user.id,
            Contact.relationship_score > 0,
        )
    )
    if scored_count.scalar() == 0:
        contact_ids = await db.execute(
            select(Contact.id).where(
                Contact.user_id == current_user.id,
                Contact.last_interaction_at.isnot(None),
            )
        )
        for (cid,) in contact_ids.all():
            try:
                await calculate_score(cid, db)
            except Exception:
                logger.exception("Score recalculation failed for contact %s", cid)
        await db.flush()

    from app.services.user_settings import get_priority_settings
    priority_settings = get_priority_settings(current_user)
    suggestions = await _generate(current_user.id, db, priority_settings=priority_settings)
    await db.flush()

    items = [FollowUpResponse.model_validate(s).model_dump() for s in suggestions]
    return envelope(items, meta={"generated": len(items)})


# ---------------------------------------------------------------------------
# POST /api/v1/suggestions/{suggestion_id}/regenerate
# ---------------------------------------------------------------------------


class RegenerateBody(BaseModel):
    channel: str | None = None


@router.post("/{suggestion_id}/regenerate", response_model=Envelope[RegenerateResult])
async def regenerate_suggestion(
    suggestion_id: uuid.UUID,
    body: RegenerateBody | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_extension_or_web_user),
) -> Envelope[RegenerateResult]:
    """Re-generate the AI-drafted message for an existing suggestion."""
    result = await db.execute(
        select(FollowUpSuggestion).where(
            FollowUpSuggestion.id == suggestion_id,
            FollowUpSuggestion.user_id == current_user.id,
        )
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")

    channel = (body.channel if body and body.channel else suggestion.suggested_channel)

    from app.services.message_composer import compose_followup_message

    new_message = await compose_followup_message(
        contact_id=suggestion.contact_id,
        trigger_type=suggestion.trigger_type,
        event_summary=None,
        db=db,
        revival_context=(suggestion.pool == "B"),
        user=current_user,
    )

    suggestion.suggested_message = new_message
    suggestion.suggested_channel = channel
    await db.flush()
    await db.refresh(suggestion)

    return envelope({"suggested_message": new_message, "suggested_channel": channel})
