"""Tests for dismiss_suggestions_for_contacts — only dismiss when the
triggering interaction's occurred_at is on/after the suggestion's created_at.

Bug this fixes: a Telegram sync that backfills historical messages was
calling dismiss for every affected contact, killing pending suggestions
created moments earlier. Combined with the followup engine's 30-day
post-dismiss cooldown, the result was 0 pending suggestions in prod
despite the cron creating new ones each run.
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
from app.services.task_jobs.common import dismiss_suggestions_for_contacts


def _contact(user_id: uuid.UUID, name: str = "Bob") -> Contact:
    return Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=name,
        relationship_score=5,
        priority_level="medium",
        source="manual",
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
        suggested_message="hey there",
        suggested_channel="telegram",
        status=status,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_dismisses_when_interaction_occurred_after_suggestion_created(
    db: AsyncSession, test_user: User
):
    """The genuine case: user got a reply 2 minutes ago, suggestion created
    4 hours ago — dismiss is correct."""
    c = _contact(test_user.id)
    db.add(c)

    suggestion_created = datetime.now(UTC) - timedelta(hours=4)
    s = _suggestion(c, test_user.id, created_at=suggestion_created)
    db.add(s)
    await db.commit()

    # Interaction occurred AFTER suggestion was created
    interaction_time = datetime.now(UTC) - timedelta(minutes=2)
    n = await dismiss_suggestions_for_contacts({c.id: interaction_time})

    assert n == 1
    # Query status as a scalar column (bypasses ORM identity-map cache).
    status = (await db.execute(
        select(FollowUpSuggestion.status).where(FollowUpSuggestion.id == s.id)
    )).scalar_one()
    assert status == "dismissed"


@pytest.mark.asyncio
async def test_does_not_dismiss_when_interaction_predates_suggestion(
    db: AsyncSession, test_user: User
):
    """The bug case: backfilled 6-month-old message arrives via sync,
    suggestion was created 1 hour ago. The old message must not dismiss
    a fresh suggestion."""
    c = _contact(test_user.id)
    db.add(c)

    suggestion_created = datetime.now(UTC) - timedelta(hours=1)
    s = _suggestion(c, test_user.id, created_at=suggestion_created)
    db.add(s)
    await db.commit()

    # Interaction occurred 6 months BEFORE suggestion
    backfill_time = datetime.now(UTC) - timedelta(days=180)
    n = await dismiss_suggestions_for_contacts({c.id: backfill_time})

    assert n == 0
    status = (await db.execute(
        select(FollowUpSuggestion.status).where(FollowUpSuggestion.id == s.id)
    )).scalar_one()
    assert status == "pending"


@pytest.mark.asyncio
async def test_only_dismisses_pending_not_sent_or_snoozed(
    db: AsyncSession, test_user: User
):
    c = _contact(test_user.id)
    db.add(c)

    base = datetime.now(UTC) - timedelta(hours=4)
    db.add(_suggestion(c, test_user.id, created_at=base, status="pending"))
    db.add(_suggestion(c, test_user.id, created_at=base, status="sent"))
    db.add(_suggestion(c, test_user.id, created_at=base, status="snoozed"))
    await db.commit()

    n = await dismiss_suggestions_for_contacts({c.id: datetime.now(UTC)})

    assert n == 1


@pytest.mark.asyncio
async def test_empty_input_is_noop(db: AsyncSession, test_user: User):
    n = await dismiss_suggestions_for_contacts({})
    assert n == 0


@pytest.mark.asyncio
async def test_per_contact_filter_is_isolated(
    db: AsyncSession, test_user: User
):
    """Two contacts: one has fresh activity (should dismiss), one has
    stale activity (should not). Verify filter is per-contact, not global."""
    fresh_contact = _contact(test_user.id, name="Fresh")
    stale_contact = _contact(test_user.id, name="Stale")
    db.add_all([fresh_contact, stale_contact])

    base = datetime.now(UTC) - timedelta(hours=2)
    s_fresh = _suggestion(fresh_contact, test_user.id, created_at=base)
    s_stale = _suggestion(stale_contact, test_user.id, created_at=base)
    db.add_all([s_fresh, s_stale])
    await db.commit()

    now = datetime.now(UTC)
    n = await dismiss_suggestions_for_contacts({
        fresh_contact.id: now,                    # after suggestion -> dismiss
        stale_contact.id: now - timedelta(days=180),  # before suggestion -> keep
    })

    assert n == 1
    fresh_status = (await db.execute(
        select(FollowUpSuggestion.status).where(FollowUpSuggestion.id == s_fresh.id)
    )).scalar_one()
    stale_status = (await db.execute(
        select(FollowUpSuggestion.status).where(FollowUpSuggestion.id == s_stale.id)
    )).scalar_one()
    assert fresh_status == "dismissed"
    assert stale_status == "pending"


@pytest.mark.asyncio
async def test_equality_at_boundary_dismisses(db: AsyncSession, test_user: User):
    """Edge case: occurred_at == created_at (millisecond match). The
    suggestion was created at the same instant the interaction occurred —
    the interaction is no older than the suggestion, so dismiss applies."""
    c = _contact(test_user.id)
    db.add(c)

    t = datetime.now(UTC) - timedelta(hours=1)
    s = _suggestion(c, test_user.id, created_at=t)
    db.add(s)
    await db.commit()

    n = await dismiss_suggestions_for_contacts({c.id: t})

    assert n == 1
