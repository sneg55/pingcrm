"""MCP tools for interaction history."""

import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import Interaction
from mcp_server.server import mcp_app
from mcp_server.db import get_session

_current_user_id = None


def set_user_id(uid):
    global _current_user_id
    _current_user_id = uid


async def _get_interactions(
    user_id: _uuid.UUID,
    db: AsyncSession,
    *,
    contact_id: str,
    limit: int = 20,
    platform: str | None = None,
) -> str:
    """Return recent interactions for a contact, ordered by date descending."""
    try:
        cid = _uuid.UUID(contact_id)
    except (ValueError, AttributeError):
        return "Invalid contact ID — expected a UUID."

    stmt = (
        select(Interaction)
        .where(Interaction.contact_id == cid, Interaction.user_id == user_id)
        .order_by(Interaction.occurred_at.desc())
    )

    if platform:
        stmt = stmt.where(Interaction.platform == platform)

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    interactions = result.scalars().all()

    if not interactions:
        return "No interactions found for this contact."

    lines = []
    for ix in interactions:
        date_str = ix.occurred_at.strftime("%Y-%m-%d %H:%M")
        direction = ix.direction or "—"
        preview = ix.content_preview or "—"

        # Read receipts for outbound messages
        receipt = ""
        if ix.direction == "outbound":
            if ix.is_read_by_recipient is True:
                receipt = " ✓✓"
            elif ix.is_read_by_recipient is False:
                receipt = " ✓"

        lines.append(
            f"- **{date_str}** [{ix.platform}] ({direction}){receipt}: {preview}"
        )

    return "\n".join(lines)


@mcp_app.tool()
async def get_interactions(contact_id: str = "", limit: int = 10, platform: str = "") -> str:
    """Get recent interactions with a contact. Optionally filter by platform (telegram/email/twitter/linkedin)."""
    async with get_session() as db:
        return await _get_interactions(_current_user_id, db, contact_id=contact_id, limit=limit, platform=platform or None)
