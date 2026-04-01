"""MCP tools for follow-up suggestions."""

import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from mcp_server.server import mcp_app
from mcp_server.db import get_session

_current_user_id = None


def set_user_id(uid):
    global _current_user_id
    _current_user_id = uid


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


@mcp_app.tool()
async def get_suggestions(limit: int = 10) -> str:
    """Get pending follow-up suggestions — contacts you should reach out to."""
    async with get_session() as db:
        return await _get_suggestions(_current_user_id, db, limit=limit)
