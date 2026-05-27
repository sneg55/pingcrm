"""Unit tests for app.services.task_jobs.common.

Covers:
- ``_run`` — sync wrapper around an async coroutine
- ``dismiss_suggestions_for_contacts`` — plain async helper (uses ``task_session``)
- ``notify_sync_failure`` — Celery shared_task wrapper
- ``notify_tagging_failure`` — Celery shared_task wrapper

The Celery tasks are invoked via ``.apply(args=[...])`` so they execute
synchronously without dispatching to a broker (mirrors the pattern in
``test_task_jobs_google.py``).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.notification import Notification
from app.models.user import User
from app.services.task_jobs.common import (
    _run,
    _write_sync_failure_notification,
    _write_tagging_failure_notification,
    dismiss_suggestions_for_contacts,
)


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


def test_run_executes_coroutine_and_returns_result():
    async def _co():
        await asyncio.sleep(0)
        return 42

    assert _run(_co()) == 42


def test_run_propagates_exception_from_coroutine():
    async def _boom():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _run(_boom())


# ---------------------------------------------------------------------------
# dismiss_suggestions_for_contacts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_returns_zero_for_empty_mapping(db: AsyncSession):
    assert await dismiss_suggestions_for_contacts({}) == 0


@pytest.mark.asyncio
async def test_dismiss_marks_pending_suggestions_dismissed(
    db: AsyncSession, test_user: User
):
    """A pending suggestion created before the triggering interaction must be
    dismissed and tagged with dismissed_by='system'."""
    contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Dismiss Me",
        source="manual",
    )
    db.add(contact)
    await db.commit()

    sugg = FollowUpSuggestion(
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="hi",
        suggested_channel="email",
        status="pending",
    )
    db.add(sugg)
    await db.commit()
    await db.refresh(sugg)

    # Interaction occurred after the suggestion was created → should dismiss
    occurred_at = sugg.created_at + timedelta(minutes=1)
    total = await dismiss_suggestions_for_contacts({contact.id: occurred_at})
    assert total == 1

    # dismiss_suggestions_for_contacts runs the UPDATE inside its own
    # task_session() engine. Verify via a fresh task_session() so we read
    # from a brand-new transaction that's guaranteed to see the commit.
    from app.core.database import task_session
    async with task_session() as fresh_db:
        r = await fresh_db.execute(
            select(FollowUpSuggestion).where(FollowUpSuggestion.id == sugg.id)
        )
        refreshed = r.scalar_one()
        assert refreshed.status == "dismissed"
        assert refreshed.dismissed_by == "system"


@pytest.mark.asyncio
async def test_dismiss_skips_suggestions_newer_than_interaction(
    db: AsyncSession, test_user: User
):
    """A backfilled historical interaction must NOT dismiss a fresh suggestion
    (the per-contact ``occurred_at`` gate documented in the function)."""
    contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Keep Me",
        source="manual",
    )
    db.add(contact)
    await db.commit()

    sugg = FollowUpSuggestion(
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="hi",
        suggested_channel="email",
        status="pending",
    )
    db.add(sugg)
    await db.commit()
    await db.refresh(sugg)

    # Interaction occurred 30 days BEFORE the suggestion → must not dismiss
    occurred_at = sugg.created_at - timedelta(days=30)
    total = await dismiss_suggestions_for_contacts({contact.id: occurred_at})
    assert total == 0

    r = await db.execute(
        select(FollowUpSuggestion).where(FollowUpSuggestion.id == sugg.id)
    )
    assert r.scalar_one().status == "pending"


@pytest.mark.asyncio
async def test_dismiss_only_touches_pending_status(
    db: AsyncSession, test_user: User
):
    """Already-dismissed or already-sent suggestions must not be re-touched."""
    contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="X",
        source="manual",
    )
    db.add(contact)
    await db.commit()

    already_dismissed = FollowUpSuggestion(
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="hi",
        suggested_channel="email",
        status="dismissed",
        dismissed_by="user",
    )
    sent = FollowUpSuggestion(
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="hi2",
        suggested_channel="email",
        status="sent",
    )
    db.add_all([already_dismissed, sent])
    await db.commit()
    await db.refresh(already_dismissed)

    total = await dismiss_suggestions_for_contacts(
        {contact.id: datetime.now(UTC) + timedelta(days=1)}
    )
    assert total == 0

    r = await db.execute(
        select(FollowUpSuggestion).where(FollowUpSuggestion.id == already_dismissed.id)
    )
    refreshed = r.scalar_one()
    # The 'user' marker must remain — system did not overwrite it.
    assert refreshed.dismissed_by == "user"


@pytest.mark.asyncio
async def test_dismiss_counts_across_multiple_contacts(
    db: AsyncSession, test_user: User
):
    contact_a = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="A", source="manual"
    )
    contact_b = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="B", source="manual"
    )
    db.add_all([contact_a, contact_b])
    await db.commit()

    s_a = FollowUpSuggestion(
        contact_id=contact_a.id, user_id=test_user.id,
        trigger_type="time_based", suggested_message="a",
        suggested_channel="email", status="pending",
    )
    s_b = FollowUpSuggestion(
        contact_id=contact_b.id, user_id=test_user.id,
        trigger_type="time_based", suggested_message="b",
        suggested_channel="email", status="pending",
    )
    db.add_all([s_a, s_b])
    await db.commit()
    await db.refresh(s_a)
    await db.refresh(s_b)

    future = datetime.now(UTC) + timedelta(days=1)
    total = await dismiss_suggestions_for_contacts(
        {contact_a.id: future, contact_b.id: future}
    )
    assert total == 2


# ---------------------------------------------------------------------------
# notify_sync_failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_sync_failure_creates_notification(
    db: AsyncSession, test_user: User
):
    """The impl writes a 'sync' notification with the platform name in the
    title and the (truncated) error in the body."""
    await _write_sync_failure_notification(
        db, test_user.id, "Gmail", "connection refused",
    )

    r = await db.execute(
        select(Notification).where(Notification.user_id == test_user.id)
    )
    notifs = list(r.scalars().all())
    assert len(notifs) == 1
    n = notifs[0]
    assert n.notification_type == "sync"
    assert n.title == "Gmail sync failed"
    assert "connection refused" in n.body
    assert n.link == "/settings"


@pytest.mark.asyncio
async def test_notify_sync_failure_truncates_long_error(
    db: AsyncSession, test_user: User
):
    """Errors longer than 200 chars are clipped so the notification body
    stays reasonable."""
    long_err = "x" * 500
    await _write_sync_failure_notification(
        db, test_user.id, "Telegram", long_err,
    )

    r = await db.execute(
        select(Notification).where(Notification.user_id == test_user.id)
    )
    n = r.scalar_one()
    # body = f"Sync failed after multiple retries: {error[:200]}"
    assert n.body.endswith("x" * 200)
    assert "x" * 201 not in n.body


# ---------------------------------------------------------------------------
# notify_tagging_failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_tagging_failure_creates_notification(
    db: AsyncSession, test_user: User
):
    await _write_tagging_failure_notification(
        db, test_user.id, "LLM rate limited",
    )

    r = await db.execute(
        select(Notification).where(Notification.user_id == test_user.id)
    )
    n = r.scalar_one()
    assert n.notification_type == "tagging"
    assert n.title == "Auto-tagging failed"
    assert n.body == "LLM rate limited"
    assert n.link == "/settings?tab=tags"


@pytest.mark.asyncio
async def test_notify_tagging_failure_truncates_long_error(
    db: AsyncSession, test_user: User
):
    long_err = "y" * 1000
    await _write_tagging_failure_notification(
        db, test_user.id, long_err,
    )

    r = await db.execute(
        select(Notification).where(Notification.user_id == test_user.id)
    )
    n = r.scalar_one()
    # body = error[:500]
    assert n.body == "y" * 500
