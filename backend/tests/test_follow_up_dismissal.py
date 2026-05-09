"""Tests for follow_up_dismissal.dismiss_outdated_pending_suggestions.

This is the helper used by all sync paths (worker telegram + per-contact
HTTP endpoints + LinkedIn/Meta pushes) to dismiss pending suggestions when
new interactions arrive — but only when the contact's last_interaction_at
is on/after the suggestion's created_at, so backfilled historical messages
don't kill fresh suggestions.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.user import User
from app.services.follow_up_dismissal import dismiss_outdated_pending_suggestions


def _contact(
    user_id: uuid.UUID,
    *,
    name: str = "C",
    last_interaction_at: datetime | None = None,
) -> Contact:
    return Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=name,
        relationship_score=5,
        priority_level="medium",
        source="manual",
        last_interaction_at=last_interaction_at,
    )


def _suggestion(
    contact: Contact,
    user_id: uuid.UUID,
    *,
    created_at: datetime,
    status: str = "pending",
) -> FollowUpSuggestion:
    return FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user_id,
        trigger_type="time_based",
        suggested_message="hi",
        suggested_channel="telegram",
        status=status,
        created_at=created_at,
    )


async def _status(db: AsyncSession, sid: uuid.UUID) -> str:
    return (await db.execute(
        select(FollowUpSuggestion.status).where(FollowUpSuggestion.id == sid)
    )).scalar_one()


@pytest.mark.asyncio
async def test_dismisses_when_last_interaction_after_suggestion_created(
    db: AsyncSession, test_user: User
):
    c = _contact(
        test_user.id,
        last_interaction_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    s = _suggestion(c, test_user.id, created_at=datetime.now(UTC) - timedelta(hours=4))
    db.add_all([c, s])
    await db.commit()

    n = await dismiss_outdated_pending_suggestions(db, [c.id])
    await db.commit()

    assert n == 1
    assert await _status(db, s.id) == "dismissed"


@pytest.mark.asyncio
async def test_keeps_suggestion_when_last_interaction_predates_creation(
    db: AsyncSession, test_user: User
):
    """Backfill case: last_interaction_at points to an old historical
    message. The fresh suggestion must survive."""
    c = _contact(
        test_user.id,
        last_interaction_at=datetime.now(UTC) - timedelta(days=180),
    )
    s = _suggestion(c, test_user.id, created_at=datetime.now(UTC) - timedelta(hours=1))
    db.add_all([c, s])
    await db.commit()

    n = await dismiss_outdated_pending_suggestions(db, [c.id])
    await db.commit()

    assert n == 0
    assert await _status(db, s.id) == "pending"


@pytest.mark.asyncio
async def test_keeps_suggestion_when_last_interaction_is_null(
    db: AsyncSession, test_user: User
):
    """A contact we've never recorded an interaction with — no signal to
    dismiss on, so the suggestion stays."""
    c = _contact(test_user.id, last_interaction_at=None)
    s = _suggestion(c, test_user.id, created_at=datetime.now(UTC) - timedelta(hours=1))
    db.add_all([c, s])
    await db.commit()

    n = await dismiss_outdated_pending_suggestions(db, [c.id])
    assert n == 0
    assert await _status(db, s.id) == "pending"


@pytest.mark.asyncio
async def test_only_pending_status_affected(
    db: AsyncSession, test_user: User
):
    c = _contact(test_user.id, last_interaction_at=datetime.now(UTC))
    base = datetime.now(UTC) - timedelta(hours=2)
    pending = _suggestion(c, test_user.id, created_at=base, status="pending")
    sent = _suggestion(c, test_user.id, created_at=base, status="sent")
    snoozed = _suggestion(c, test_user.id, created_at=base, status="snoozed")
    db.add_all([c, pending, sent, snoozed])
    await db.commit()

    n = await dismiss_outdated_pending_suggestions(db, [c.id])
    await db.commit()

    assert n == 1
    assert await _status(db, pending.id) == "dismissed"
    assert await _status(db, sent.id) == "sent"
    assert await _status(db, snoozed.id) == "snoozed"


@pytest.mark.asyncio
async def test_per_contact_filter_isolated(
    db: AsyncSession, test_user: User
):
    fresh = _contact(
        test_user.id, name="Fresh",
        last_interaction_at=datetime.now(UTC),  # active right now
    )
    stale = _contact(
        test_user.id, name="Stale",
        last_interaction_at=datetime.now(UTC) - timedelta(days=180),  # old
    )
    base = datetime.now(UTC) - timedelta(hours=2)
    s_fresh = _suggestion(fresh, test_user.id, created_at=base)
    s_stale = _suggestion(stale, test_user.id, created_at=base)
    db.add_all([fresh, stale, s_fresh, s_stale])
    await db.commit()

    n = await dismiss_outdated_pending_suggestions(db, [fresh.id, stale.id])
    await db.commit()

    assert n == 1
    assert await _status(db, s_fresh.id) == "dismissed"
    assert await _status(db, s_stale.id) == "pending"


@pytest.mark.asyncio
async def test_empty_input_is_noop(db: AsyncSession, test_user: User):
    n = await dismiss_outdated_pending_suggestions(db, [])
    assert n == 0
