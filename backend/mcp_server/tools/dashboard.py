"""MCP tools for dashboard statistics."""

import uuid as _uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction
from mcp_server.server import mcp_app
from mcp_server.db import get_session

_current_user_id = None


def set_user_id(uid):
    global _current_user_id
    _current_user_id = uid


async def _get_dashboard_stats(
    user_id: _uuid.UUID,
    db: AsyncSession,
) -> str:
    """Return a formatted dashboard summary with key CRM stats."""
    # 1. Total contacts (excluding archived)
    total_result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.priority_level != "archived",
        )
    )
    total_contacts = total_result.scalar_one()

    # 2. Score distribution
    score_result = await db.execute(
        select(
            func.count(case((Contact.relationship_score >= 8, 1))).label("strong"),
            func.count(
                case(
                    (
                        (Contact.relationship_score >= 4)
                        & (Contact.relationship_score <= 7),
                        1,
                    )
                )
            ).label("warm"),
            func.count(case((Contact.relationship_score <= 3, 1))).label("cold"),
        ).where(
            Contact.user_id == user_id,
            Contact.priority_level != "archived",
        )
    )
    score_row = score_result.one()

    # 3. Pending suggestions count
    sugg_result = await db.execute(
        select(func.count(FollowUpSuggestion.id)).where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "pending",
        )
    )
    pending_suggestions = sugg_result.scalar_one()

    # 4. 7-day interactions by platform
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)
    ix_result = await db.execute(
        select(Interaction.platform, func.count(Interaction.id))
        .where(
            Interaction.user_id == user_id,
            Interaction.occurred_at >= seven_days_ago,
        )
        .group_by(Interaction.platform)
        .order_by(func.count(Interaction.id).desc())
    )
    platform_counts = ix_result.all()

    # Format output
    lines = [
        "# Dashboard",
        "",
        f"**Total contacts:** {total_contacts}",
        "",
        "## Score Distribution",
        f"- Strong (8-10): {score_row.strong}",
        f"- Warm (4-7): {score_row.warm}",
        f"- Cold (0-3): {score_row.cold}",
        "",
        f"**Pending suggestions:** {pending_suggestions}",
        "",
        "## Interactions (last 7 days)",
    ]

    if platform_counts:
        for platform, count in platform_counts:
            lines.append(f"- {platform}: {count}")
    else:
        lines.append("No interactions in the last 7 days.")

    return "\n".join(lines)


@mcp_app.tool()
async def get_dashboard_stats() -> str:
    """Get network health overview: contact counts, score distribution, pending suggestions, recent activity."""
    async with get_session() as db:
        return await _get_dashboard_stats(_current_user_id, db)
