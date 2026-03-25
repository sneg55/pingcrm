"""MCP tools for notifications."""
from __future__ import annotations

import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def _get_notifications(
    user_id: _uuid.UUID,
    db: AsyncSession,
    *,
    unread_only: bool = True,
    limit: int = 20,
) -> str:
    """Return recent notifications, optionally filtered to unread only."""
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )

    if unread_only:
        stmt = stmt.where(Notification.read == False)  # noqa: E712

    result = await db.execute(stmt)
    notifications = result.scalars().all()

    if not notifications:
        if unread_only:
            return "No unread notifications."
        return "No notifications."

    lines = []
    for n in notifications:
        date_str = n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "—"
        unread_marker = " 🔵" if not n.read else ""
        body = f" — {n.body}" if n.body else ""
        lines.append(f"- **{n.title}**{body} ({date_str}){unread_marker}")

    return "\n".join(lines)
