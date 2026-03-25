"""MCP tools for follow-up suggestions."""
from __future__ import annotations

import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion


async def _get_suggestions(
    user_id: _uuid.UUID,
    db: AsyncSession,
    *,
    limit: int = 10,
) -> str:
    """Return pending follow-up suggestions with contact names."""
    stmt = (
        select(FollowUpSuggestion)
        .where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "pending",
        )
        .order_by(FollowUpSuggestion.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    suggestions = result.scalars().all()

    if not suggestions:
        return "No pending follow-up suggestions."

    # Batch-load contact names
    contact_ids = list({s.contact_id for s in suggestions})
    contact_result = await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
    )
    contacts = contact_result.scalars().all()
    name_map = {c.id: c.full_name or "(unnamed)" for c in contacts}

    lines = []
    for s in suggestions:
        contact_name = name_map.get(s.contact_id, "(unknown)")
        date_str = s.created_at.strftime("%Y-%m-%d") if s.created_at else "—"
        lines.append(
            f"- **{contact_name}** ({s.trigger_type}, {date_str}): {s.suggested_message}"
        )

    return "\n".join(lines)
