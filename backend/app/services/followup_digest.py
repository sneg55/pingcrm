"""Weekly digest reader: fetch pending follow-up suggestions for a user."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.follow_up import FollowUpSuggestion


async def get_weekly_digest(user_id: uuid.UUID, db: AsyncSession) -> list[FollowUpSuggestion]:
    """Fetch pending suggestions for a user ordered by creation date (most recent first)."""
    result = await db.execute(
        select(FollowUpSuggestion)
        .where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "pending",
        )
        .order_by(FollowUpSuggestion.created_at.desc())
    )
    return list(result.scalars().all())
