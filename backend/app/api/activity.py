from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

router = APIRouter(prefix="/api/v1/activity", tags=["activity"])


def envelope(data, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


@router.get("/recent")
async def get_recent_activity(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return a unified activity feed of recent interactions across all contacts."""
    since = datetime.now(UTC) - timedelta(days=7)

    result = await db.execute(
        select(Interaction, Contact)
        .join(Contact, Contact.id == Interaction.contact_id)
        .where(
            Interaction.user_id == current_user.id,
            Interaction.occurred_at >= since,
            Contact.priority_level != "archived",
        )
        .order_by(Interaction.occurred_at.desc())
        .limit(limit * 3)  # fetch extra to allow dedup
    )
    rows = result.all()

    # Deduplicate: only the most recent activity per contact
    seen_contacts: set[str] = set()
    events: list[dict] = []
    for interaction, contact in rows:
        cid = str(contact.id)
        if cid in seen_contacts:
            continue
        seen_contacts.add(cid)
        events.append({
            "type": "message",
            "contact_name": contact.full_name,
            "contact_id": cid,
            "contact_avatar_url": contact.avatar_url,
            "platform": interaction.platform,
            "direction": interaction.direction,
            "content_preview": interaction.content_preview,
            "timestamp": interaction.occurred_at.isoformat(),
        })
        if len(events) >= limit:
            break

    return envelope(events)
