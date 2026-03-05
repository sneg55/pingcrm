import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction


async def calculate_score(contact_id: uuid.UUID, db: AsyncSession) -> int:
    """
    Calculate relationship score for a contact (0-10 scale).

    Spec signals:
    - +5 for having messages exchanged in last 30 days
    - +3 if any reply was sent within 48 hours
    - +2 if any introduction was made
    - -2 per month of silence (no interactions at all)
    - Capped at 0-10
    """
    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)

    # Count interactions in last 30 days
    count_result = await db.execute(
        select(func.count())
        .select_from(Interaction)
        .where(
            Interaction.contact_id == contact_id,
            Interaction.occurred_at >= thirty_days_ago,
        )
    )
    recent_count = count_result.scalar_one()

    # Get all interactions for reply speed and intro analysis
    result = await db.execute(
        select(Interaction)
        .where(Interaction.contact_id == contact_id)
        .order_by(Interaction.occurred_at.asc())
    )
    interactions = result.scalars().all()

    # Check for quick replies (inbound followed by outbound within 48h)
    has_quick_reply = False
    for i in range(1, len(interactions)):
        prev = interactions[i - 1]
        curr = interactions[i]
        prev_at = prev.occurred_at
        curr_at = curr.occurred_at
        if prev_at and prev_at.tzinfo is None:
            prev_at = prev_at.replace(tzinfo=UTC)
        if curr_at and curr_at.tzinfo is None:
            curr_at = curr_at.replace(tzinfo=UTC)
        if (
            prev.direction == "inbound"
            and curr.direction == "outbound"
            and prev_at
            and curr_at
            and (curr_at - prev_at) <= timedelta(hours=48)
        ):
            has_quick_reply = True
            break

    # Check for introductions
    has_intro = False
    for interaction in interactions:
        preview = (interaction.content_preview or "").lower()
        if "intro" in preview or "introduction" in preview:
            has_intro = True
            break

    # Calculate months of silence since last interaction
    silence_months = 0
    if interactions:
        last_at = interactions[-1].occurred_at
        if last_at and last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=UTC)
        if last_at:
            days_since = (now - last_at).days
            silence_months = max(0, days_since // 30)
    else:
        silence_months = 3  # No interactions ever

    # Calculate score using spec formula
    score = 0
    if recent_count > 0:
        score += 5  # +5 for messages in last 30 days
    if has_quick_reply:
        score += 3  # +3 for responsive replies
    if has_intro:
        score += 2  # +2 for introductions
    score -= silence_months * 2  # -2 per month of silence

    score = max(0, min(10, score))

    # Persist updated score
    contact_result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = contact_result.scalar_one_or_none()
    if contact:
        contact.relationship_score = score
        await db.flush()

    return score
