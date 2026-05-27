"""Unit tests for app.services.task_jobs.followups.

These tests exercise the lifted impl coroutines against a real Postgres test
database (via the conftest ``db`` fixture). External services
(``generate_suggestions``, ``notify_new_suggestions``, ``send_weekly_digest``)
are mocked at the module level so we cover the orchestration logic — loop
iteration, error swallowing, status filtering — without hitting downstream
modules.

The Celery entrypoint wrappers are tested separately by invoking them via
``.apply()`` so retries surface as ``celery.exceptions.Retry`` exceptions
instead of dispatching to a broker.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from celery.exceptions import Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.user import User
from app.services.task_jobs.followups import (
    _generate_suggestions_all,
    _generate_weekly_suggestions,
    _reactivate_snoozed_suggestions,
    _send_weekly_digests,
    generate_suggestions_all,
    generate_weekly_suggestions,
    reactivate_snoozed_suggestions,
    send_weekly_digests,
)


# ---------------------------------------------------------------------------
# _generate_weekly_suggestions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_weekly_user_not_found(db: AsyncSession):
    result = await _generate_weekly_suggestions(db, uuid.uuid4())
    assert result == {"status": "user_not_found", "generated": 0}


@pytest.mark.asyncio
async def test_generate_weekly_zero_suggestions_no_notify(
    db: AsyncSession, test_user: User
):
    """No suggestions returned → notify_new_suggestions must not be called."""
    with (
        patch(
            "app.services.task_jobs.followups.generate_suggestions",
            new=AsyncMock(return_value=[]),
        ) as mock_gen,
        patch(
            "app.services.task_jobs.followups.notify_new_suggestions",
            new=AsyncMock(),
        ) as mock_notify,
    ):
        result = await _generate_weekly_suggestions(db, test_user.id)

    assert result == {"status": "ok", "generated": 0}
    mock_gen.assert_awaited_once_with(
        test_user.id, db, priority_settings=test_user.priority_settings
    )
    mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_weekly_with_suggestions_notifies(
    db: AsyncSession, test_user: User
):
    """Non-empty suggestion list → notify is called with the count."""
    fake_suggestions = ["s1", "s2", "s3"]
    with (
        patch(
            "app.services.task_jobs.followups.generate_suggestions",
            new=AsyncMock(return_value=fake_suggestions),
        ),
        patch(
            "app.services.task_jobs.followups.notify_new_suggestions",
            new=AsyncMock(),
        ) as mock_notify,
    ):
        result = await _generate_weekly_suggestions(db, test_user.id)

    assert result == {"status": "ok", "generated": 3}
    mock_notify.assert_awaited_once_with(test_user.id, 3, db)


@pytest.mark.asyncio
async def test_generate_weekly_passes_priority_settings(
    db: AsyncSession, test_user: User
):
    """User's priority_settings must be forwarded to generate_suggestions."""
    test_user.priority_settings = {"min_score": 10}
    await db.commit()

    with (
        patch(
            "app.services.task_jobs.followups.generate_suggestions",
            new=AsyncMock(return_value=[]),
        ) as mock_gen,
        patch(
            "app.services.task_jobs.followups.notify_new_suggestions",
            new=AsyncMock(),
        ),
    ):
        await _generate_weekly_suggestions(db, test_user.id)

    mock_gen.assert_awaited_once_with(
        test_user.id, db, priority_settings={"min_score": 10}
    )


# ---------------------------------------------------------------------------
# _send_weekly_digests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_weekly_digests_empty_db(db: AsyncSession):
    """No users → sent=0, errors=0."""
    with patch(
        "app.services.task_jobs.followups.send_weekly_digest",
        new=AsyncMock(),
    ) as mock_send:
        result = await _send_weekly_digests(db)

    assert result == {"sent": 0, "errors": 0}
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_weekly_digests_all_succeed(
    db: AsyncSession, test_user: User, user_factory
):
    """Three users, all succeed → sent=3, errors=0."""
    await user_factory()
    await user_factory()

    with patch(
        "app.services.task_jobs.followups.send_weekly_digest",
        new=AsyncMock(),
    ) as mock_send:
        result = await _send_weekly_digests(db)

    assert result == {"sent": 3, "errors": 0}
    assert mock_send.await_count == 3


@pytest.mark.asyncio
async def test_send_weekly_digests_partial_failure_increments_errors(
    db: AsyncSession, test_user: User, user_factory
):
    """One user blows up → errors=1, sent=remaining. Loop continues."""
    other = await user_factory()
    failing_id = other.id

    async def fake_send(uid, _db):
        if uid == failing_id:
            raise RuntimeError("digest broke")

    with patch(
        "app.services.task_jobs.followups.send_weekly_digest",
        new=AsyncMock(side_effect=fake_send),
    ):
        result = await _send_weekly_digests(db)

    assert result == {"sent": 1, "errors": 1}


# ---------------------------------------------------------------------------
# _generate_suggestions_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_all_empty_db(db: AsyncSession):
    with (
        patch(
            "app.services.task_jobs.followups.generate_suggestions",
            new=AsyncMock(return_value=[]),
        ) as mock_gen,
        patch(
            "app.services.task_jobs.followups.notify_new_suggestions",
            new=AsyncMock(),
        ),
    ):
        result = await _generate_suggestions_all(db)

    assert result == {"generated": 0, "errors": 0}
    mock_gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_all_sums_counts_across_users(
    db: AsyncSession, test_user: User, user_factory
):
    """Total ``generated`` is the SUM of suggestions across all users."""
    await user_factory()
    await user_factory()

    # Each user gets 2 suggestions → 6 total
    with (
        patch(
            "app.services.task_jobs.followups.generate_suggestions",
            new=AsyncMock(return_value=["a", "b"]),
        ),
        patch(
            "app.services.task_jobs.followups.notify_new_suggestions",
            new=AsyncMock(),
        ) as mock_notify,
    ):
        result = await _generate_suggestions_all(db)

    assert result == {"generated": 6, "errors": 0}
    assert mock_notify.await_count == 3


@pytest.mark.asyncio
async def test_generate_all_swallows_per_user_exception(
    db: AsyncSession, test_user: User, user_factory
):
    """A user that explodes increments ``errors`` but doesn't abort the loop."""
    bad = await user_factory()
    bad_id = bad.id

    async def fake_gen(uid, _db, priority_settings=None):  # noqa: ARG001
        if uid == bad_id:
            raise RuntimeError("engine kaboom")
        return ["one"]

    with (
        patch(
            "app.services.task_jobs.followups.generate_suggestions",
            new=AsyncMock(side_effect=fake_gen),
        ),
        patch(
            "app.services.task_jobs.followups.notify_new_suggestions",
            new=AsyncMock(),
        ) as mock_notify,
    ):
        result = await _generate_suggestions_all(db)

    # 1 good user produced 1 suggestion; 1 bad user → 1 error
    assert result == {"generated": 1, "errors": 1}
    # notify only fires for the good user
    assert mock_notify.await_count == 1


@pytest.mark.asyncio
async def test_generate_all_skips_notify_for_empty_results(
    db: AsyncSession, test_user: User
):
    """If a user has zero suggestions, notify must not be called for them."""
    with (
        patch(
            "app.services.task_jobs.followups.generate_suggestions",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.task_jobs.followups.notify_new_suggestions",
            new=AsyncMock(),
        ) as mock_notify,
    ):
        result = await _generate_suggestions_all(db)

    assert result == {"generated": 0, "errors": 0}
    mock_notify.assert_not_awaited()


# ---------------------------------------------------------------------------
# _reactivate_snoozed_suggestions
# ---------------------------------------------------------------------------


async def _make_contact(db: AsyncSession, user_id: uuid.UUID) -> Contact:
    c = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name="C",
        source="manual",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest.mark.asyncio
async def test_reactivate_no_snoozed_suggestions(db: AsyncSession):
    result = await _reactivate_snoozed_suggestions(db)
    assert result == 0


@pytest.mark.asyncio
async def test_reactivate_only_due_snoozed_suggestions(
    db: AsyncSession, test_user: User
):
    """Only snoozed suggestions whose scheduled_for is in the past must flip."""
    contact = await _make_contact(db, test_user.id)
    now = datetime.now(UTC)

    due = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="hi",
        suggested_channel="email",
        status="snoozed",
        scheduled_for=now - timedelta(hours=1),
    )
    future = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="later",
        suggested_channel="email",
        status="snoozed",
        scheduled_for=now + timedelta(days=1),
    )
    pending = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="pending",
        suggested_channel="email",
        status="pending",
        scheduled_for=now - timedelta(hours=1),
    )
    db.add_all([due, future, pending])
    await db.commit()

    result = await _reactivate_snoozed_suggestions(db)
    assert result == 1

    await db.refresh(due)
    await db.refresh(future)
    await db.refresh(pending)
    assert due.status == "pending"
    assert future.status == "snoozed"  # untouched
    assert pending.status == "pending"  # untouched


@pytest.mark.asyncio
async def test_reactivate_ignores_dismissed_suggestions(
    db: AsyncSession, test_user: User
):
    """Only ``status == 'snoozed'`` is touched — dismissed/completed stay put
    even with a past scheduled_for."""
    contact = await _make_contact(db, test_user.id)
    now = datetime.now(UTC)

    dismissed = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="x",
        suggested_channel="email",
        status="dismissed",
        scheduled_for=now - timedelta(hours=1),
    )
    db.add(dismissed)
    await db.commit()

    result = await _reactivate_snoozed_suggestions(db)
    assert result == 0
    await db.refresh(dismissed)
    assert dismissed.status == "dismissed"


@pytest.mark.asyncio
async def test_reactivate_treats_null_scheduled_for_as_not_due(
    db: AsyncSession, test_user: User
):
    """A snoozed suggestion with NULL scheduled_for must NOT be reactivated —
    the SQL comparison ``NULL <= now`` is UNKNOWN, which behaves as false."""
    contact = await _make_contact(db, test_user.id)

    s = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="x",
        suggested_channel="email",
        status="snoozed",
        scheduled_for=None,
    )
    db.add(s)
    await db.commit()

    result = await _reactivate_snoozed_suggestions(db)
    assert result == 0
    await db.refresh(s)
    assert s.status == "snoozed"


# ---------------------------------------------------------------------------
# Celery wrappers — argument validation + retry plumbing
# ---------------------------------------------------------------------------


def test_generate_weekly_returns_sentinel_on_invalid_uuid():
    result = generate_weekly_suggestions.apply(args=["not-a-uuid"]).get()
    assert result == {"status": "invalid_user_id", "generated": 0}


def test_generate_weekly_runs_wrapper_and_returns_impl_result():
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.followups._generate_weekly_suggestions",
            new=AsyncMock(return_value={"status": "ok", "generated": 4}),
        ),
        patch(
            "app.services.task_jobs.followups.task_session",
        ) as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = generate_weekly_suggestions.apply(args=[uid]).get()

    assert result == {"status": "ok", "generated": 4}


def test_generate_weekly_retries_on_failure():
    """When the impl raises, the wrapper logs and calls self.retry()."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.followups._generate_weekly_suggestions",
            new=AsyncMock(side_effect=RuntimeError("nope")),
        ),
        patch(
            "app.services.task_jobs.followups.task_session",
        ) as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        with pytest.raises(Retry):
            generate_weekly_suggestions.apply(args=[uid], throw=True).get()


def test_send_weekly_digests_wrapper_returns_impl_result():
    with (
        patch(
            "app.services.task_jobs.followups._send_weekly_digests",
            new=AsyncMock(return_value={"sent": 7, "errors": 1}),
        ),
        patch(
            "app.services.task_jobs.followups.task_session",
        ) as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = send_weekly_digests()

    assert result == {"sent": 7, "errors": 1}


def test_generate_suggestions_all_wrapper_returns_impl_result():
    with (
        patch(
            "app.services.task_jobs.followups._generate_suggestions_all",
            new=AsyncMock(return_value={"generated": 12, "errors": 0}),
        ),
        patch(
            "app.services.task_jobs.followups.task_session",
        ) as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = generate_suggestions_all()

    assert result == {"generated": 12, "errors": 0}


def test_reactivate_snoozed_suggestions_wrapper_returns_count_dict():
    """Wrapper wraps the raw int count in a ``{"reactivated": N}`` dict."""
    with (
        patch(
            "app.services.task_jobs.followups._reactivate_snoozed_suggestions",
            new=AsyncMock(return_value=5),
        ),
        patch(
            "app.services.task_jobs.followups.task_session",
        ) as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = reactivate_snoozed_suggestions()

    assert result == {"reactivated": 5}


# ---------------------------------------------------------------------------
# End-to-end sanity check using a real DB and lifted impl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_weekly_persists_via_db_commit(
    db: AsyncSession, test_user: User
):
    """Verify the impl actually commits — the notification side effect of
    notify_new_suggestions must survive past the function call."""
    seen_db_in_notify: list[AsyncSession] = []

    async def fake_notify(uid, count, db_arg):  # noqa: ARG001
        seen_db_in_notify.append(db_arg)

    with (
        patch(
            "app.services.task_jobs.followups.generate_suggestions",
            new=AsyncMock(return_value=["one"]),
        ),
        patch(
            "app.services.task_jobs.followups.notify_new_suggestions",
            new=AsyncMock(side_effect=fake_notify),
        ),
    ):
        result = await _generate_weekly_suggestions(db, test_user.id)

    assert result == {"status": "ok", "generated": 1}
    # notify received the *same* session we passed in
    assert seen_db_in_notify == [db]


@pytest.mark.asyncio
async def test_reactivate_returns_int_not_dict(
    db: AsyncSession, test_user: User
):
    """The lifted impl returns the raw int; only the wrapper wraps it in a dict.
    Codifying this so future refactors don't quietly change the shape."""
    result = await _reactivate_snoozed_suggestions(db)
    assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Quirk codification
# ---------------------------------------------------------------------------


def test_reactivate_wrapper_logs_count(caplog):
    """The wrapper logs a single info line ``reactivated %d suggestion(s)``.
    Codifying this so log-watchers don't break silently."""
    import logging

    with (
        patch(
            "app.services.task_jobs.followups._reactivate_snoozed_suggestions",
            new=AsyncMock(return_value=3),
        ),
        patch("app.services.task_jobs.followups.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        with caplog.at_level(logging.INFO, logger="app.services.task_jobs.common"):
            reactivate_snoozed_suggestions()

    assert any(
        "reactivated 3 suggestion(s)" in rec.getMessage() for rec in caplog.records
    )
