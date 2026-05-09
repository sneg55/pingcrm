"""Tests for the followup engine's dismiss-cooldown filter:

The 30-day post-dismiss cooldown should ONLY apply to suggestions the
user explicitly dismissed (dismissed_by='user'). System dismissals from
sync paths (dismissed_by='system') must not lock the contact out — they
weren't a signal of "user said no", just "we have new activity".
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction
from app.models.user import User
from app.services.follow_up_dismissal import dismiss_outdated_pending_suggestions
from app.services.followup_engine import generate_suggestions


def _contact(
    user_id: uuid.UUID,
    *,
    name: str = "C",
    last_interaction_at: datetime | None = None,
    score: int = 2,
    priority: str = "medium",
    interaction_count: int = 5,
) -> Contact:
    return Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=name,
        emails=[f"{name.lower()}@example.com"],
        relationship_score=score,
        priority_level=priority,
        source="manual",
        last_interaction_at=last_interaction_at,
        interaction_count=interaction_count,
    )


def _interaction(
    contact: Contact, user_id: uuid.UUID, *, days_ago: int
) -> Interaction:
    return Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user_id,
        platform="telegram",
        direction="inbound",
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


def _dismissed_suggestion(
    contact: Contact,
    user_id: uuid.UUID,
    *,
    dismissed_at: datetime,
    dismissed_by: str | None,
) -> FollowUpSuggestion:
    return FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user_id,
        trigger_type="time_based",
        suggested_message="hi",
        suggested_channel="telegram",
        status="dismissed",
        created_at=dismissed_at - timedelta(hours=1),
        updated_at=dismissed_at,
        dismissed_by=dismissed_by,
    )


# ---------------------------------------------------------------------------
# Engine cooldown filter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_dismissal_triggers_cooldown(
    db: AsyncSession, test_user: User
):
    """Contact with a recent user-dismissed suggestion is excluded from
    the next generation run."""
    c = _contact(
        test_user.id,
        last_interaction_at=datetime.now(UTC) - timedelta(days=70),  # Pool A medium eligible
    )
    db.add(c)
    db.add(_interaction(c, test_user.id, days_ago=70))
    db.add(_dismissed_suggestion(
        c, test_user.id,
        dismissed_at=datetime.now(UTC) - timedelta(days=5),  # well within 30-day cooldown
        dismissed_by="user",
    ))
    await db.commit()

    suggestions = await generate_suggestions(test_user.id, db)
    await db.commit()

    # Contact is in cooldown — no new suggestion should be created for it.
    assert all(s.contact_id != c.id for s in suggestions), (
        "user-dismissed contact should be in cooldown"
    )


@pytest.mark.asyncio
async def test_system_dismissal_does_not_trigger_cooldown(
    db: AsyncSession, test_user: User
):
    """Same setup but dismissed_by='system' — engine should NOT exclude
    the contact, so it's eligible to receive a fresh suggestion."""
    c = _contact(
        test_user.id,
        last_interaction_at=datetime.now(UTC) - timedelta(days=70),
    )
    db.add(c)
    db.add(_interaction(c, test_user.id, days_ago=70))
    db.add(_dismissed_suggestion(
        c, test_user.id,
        dismissed_at=datetime.now(UTC) - timedelta(days=5),
        dismissed_by="system",
    ))
    await db.commit()

    suggestions = await generate_suggestions(test_user.id, db)
    await db.commit()

    # System-dismissed contact should be eligible — a new pending suggestion
    # exists for it.
    contact_ids = {s.contact_id for s in suggestions}
    assert c.id in contact_ids, (
        "system-dismissed contact must not be locked out by cooldown"
    )


@pytest.mark.asyncio
async def test_null_dismissed_by_treated_as_not_user_dismissal(
    db: AsyncSession, test_user: User
):
    """Pre-migration rows have dismissed_by=NULL. Treat them as non-user
    (so they don't trigger cooldown) — the safer, more permissive default."""
    c = _contact(
        test_user.id,
        last_interaction_at=datetime.now(UTC) - timedelta(days=70),
    )
    db.add(c)
    db.add(_interaction(c, test_user.id, days_ago=70))
    db.add(_dismissed_suggestion(
        c, test_user.id,
        dismissed_at=datetime.now(UTC) - timedelta(days=5),
        dismissed_by=None,
    ))
    await db.commit()

    suggestions = await generate_suggestions(test_user.id, db)
    await db.commit()

    contact_ids = {s.contact_id for s in suggestions}
    assert c.id in contact_ids, "NULL dismissed_by should not trigger cooldown"


# ---------------------------------------------------------------------------
# Producer side: dismiss helpers stamp the column
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dismiss_outdated_stamps_system_by_default(
    db: AsyncSession, test_user: User
):
    """The shared helper used by all sync paths must stamp dismissed_by='system'."""
    c = _contact(
        test_user.id,
        last_interaction_at=datetime.now(UTC),  # recent activity
    )
    suggestion = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=c.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="hi",
        suggested_channel="telegram",
        status="pending",
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )
    db.add_all([c, suggestion])
    await db.commit()

    n = await dismiss_outdated_pending_suggestions(db, [c.id])
    await db.commit()

    assert n == 1
    refreshed_status, refreshed_by = (await db.execute(
        select(FollowUpSuggestion.status, FollowUpSuggestion.dismissed_by)
        .where(FollowUpSuggestion.id == suggestion.id)
    )).one()
    assert refreshed_status == "dismissed"
    assert refreshed_by == "system"
