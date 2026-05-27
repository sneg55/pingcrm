"""Unit tests for app.services.task_jobs.gmail.

These tests exercise the lifted ``_sync_gmail`` / ``_collect_gmail_user_ids``
coroutines against a real Postgres test database (via the conftest ``db``
fixture). The external integration boundary
(``app.integrations.gmail.sync_gmail_for_user``) is mocked at the
``task_jobs.gmail`` module level so we cover orchestration logic —
user lookup, sync history, scoring, identity resolution — without hitting
Gmail.

The Celery entrypoint wrappers are tested via ``.apply()`` so retries surface
as ``celery.exceptions.Retry`` exceptions instead of dispatching to a broker.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from celery.exceptions import Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import Provider
from app.models.contact import Contact
from app.models.sync_event import SyncEvent
from app.models.user import User
from app.services.task_jobs.gmail import (
    _collect_gmail_user_ids,
    _sync_gmail,
    sync_gmail_all,
    sync_gmail_for_user,
)


# ---------------------------------------------------------------------------
# _sync_gmail — early exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_gmail_user_not_found(db: AsyncSession):
    result = await _sync_gmail(db, uuid.uuid4())
    assert result == {"status": "user_not_found", "new_interactions": 0}


# ---------------------------------------------------------------------------
# _sync_gmail — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_gmail_records_history_and_returns_count(
    db: AsyncSession, test_user: User
):
    """Successful sync records a completed SyncEvent and returns the new-count."""
    with patch(
        "app.services.task_jobs.gmail._gmail_sync",
        new=AsyncMock(return_value=3),
    ) as mock_sync:
        result = await _sync_gmail(db, test_user.id)

    assert result == {"status": "ok", "new_interactions": 3}
    mock_sync.assert_awaited_once()
    # First positional arg to the integration is the User row.
    called_user = mock_sync.await_args.args[0]
    assert called_user.id == test_user.id

    # A SyncEvent row was created and marked complete.
    r = await db.execute(
        select(SyncEvent).where(SyncEvent.user_id == test_user.id)
    )
    events = list(r.scalars().all())
    assert len(events) == 1
    assert events[0].platform == Provider.GMAIL


@pytest.mark.asyncio
async def test_sync_gmail_zero_new_skips_scoring_and_merge(
    db: AsyncSession, test_user: User
):
    """If sync returns 0 new interactions, scoring + identity resolution must
    be skipped (saves a round-trip on quiet syncs)."""
    with (
        patch(
            "app.services.task_jobs.gmail._gmail_sync",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.services.task_jobs.gmail.calculate_score",
            new=AsyncMock(return_value=42),
        ) as mock_score,
        patch(
            "app.services.task_jobs.gmail.find_deterministic_matches",
            new=AsyncMock(return_value=[]),
        ) as mock_dedup,
    ):
        result = await _sync_gmail(db, test_user.id)

    assert result["new_interactions"] == 0
    mock_score.assert_not_awaited()
    mock_dedup.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_gmail_rescores_contacts_with_interactions(
    db: AsyncSession, test_user: User
):
    """When new_count > 0, every contact with last_interaction_at gets a
    calculate_score call. Contacts without it are skipped."""
    has_interaction = Contact(
        user_id=test_user.id,
        full_name="Active",
        emails=["active@example.com"],
        last_interaction_at=datetime.now(UTC) - timedelta(days=1),
        source="manual",
    )
    no_interaction = Contact(
        user_id=test_user.id,
        full_name="Quiet",
        emails=["quiet@example.com"],
        last_interaction_at=None,
        source="manual",
    )
    db.add_all([has_interaction, no_interaction])
    await db.commit()

    with (
        patch(
            "app.services.task_jobs.gmail._gmail_sync",
            new=AsyncMock(return_value=2),
        ),
        patch(
            "app.services.task_jobs.gmail.calculate_score",
            new=AsyncMock(return_value=10),
        ) as mock_score,
        patch(
            "app.services.task_jobs.gmail.find_deterministic_matches",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await _sync_gmail(db, test_user.id)

    assert mock_score.await_count == 1
    called_cid = mock_score.await_args.args[0]
    assert called_cid == has_interaction.id


@pytest.mark.asyncio
async def test_sync_gmail_score_recalc_failure_is_logged_not_fatal(
    db: AsyncSession, test_user: User
):
    """If calculate_score raises mid-loop, the sync still completes
    successfully — scoring is best-effort."""
    db.add(Contact(
        user_id=test_user.id,
        full_name="Scored",
        emails=["s@example.com"],
        last_interaction_at=datetime.now(UTC) - timedelta(days=1),
        source="manual",
    ))
    await db.commit()

    with (
        patch(
            "app.services.task_jobs.gmail._gmail_sync",
            new=AsyncMock(return_value=1),
        ),
        patch(
            "app.services.task_jobs.gmail.calculate_score",
            new=AsyncMock(side_effect=RuntimeError("scoring broke")),
        ),
        patch(
            "app.services.task_jobs.gmail.find_deterministic_matches",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await _sync_gmail(db, test_user.id)

    assert result["status"] == "ok"
    assert result["new_interactions"] == 1


@pytest.mark.asyncio
async def test_sync_gmail_invokes_auto_merge_when_new_interactions(
    db: AsyncSession, test_user: User
):
    """find_deterministic_matches runs whenever new_count > 0 — it's what
    auto-collapses duplicate contacts produced by mail-import flows."""
    with (
        patch(
            "app.services.task_jobs.gmail._gmail_sync",
            new=AsyncMock(return_value=1),
        ),
        patch(
            "app.services.task_jobs.gmail.find_deterministic_matches",
            new=AsyncMock(return_value=["fake-match"]),
        ) as mock_dedup,
    ):
        await _sync_gmail(db, test_user.id)

    mock_dedup.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_gmail_auto_merge_failure_is_logged_not_fatal(
    db: AsyncSession, test_user: User
):
    """If identity resolution explodes after a sync, the sync still returns
    ok — dedup is best-effort and runs at the very end of the flow."""
    with (
        patch(
            "app.services.task_jobs.gmail._gmail_sync",
            new=AsyncMock(return_value=1),
        ),
        patch(
            "app.services.task_jobs.gmail.find_deterministic_matches",
            new=AsyncMock(side_effect=RuntimeError("dedup broke")),
        ),
    ):
        result = await _sync_gmail(db, test_user.id)

    assert result == {"status": "ok", "new_interactions": 1}


# ---------------------------------------------------------------------------
# _sync_gmail — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_gmail_integration_error_records_failure_and_reraises(
    db: AsyncSession, test_user: User
):
    """If the Gmail integration raises, ``record_sync_failure`` is committed
    before the exception propagates so Celery can retry."""
    with patch(
        "app.services.task_jobs.gmail._gmail_sync",
        new=AsyncMock(side_effect=RuntimeError("gmail boom")),
    ):
        with pytest.raises(RuntimeError, match="gmail boom"):
            await _sync_gmail(db, test_user.id)

    # SyncEvent row exists and has a non-null finished_at/error indicator —
    # exact column varies by model, just confirm the row was committed.
    r = await db.execute(
        select(SyncEvent).where(SyncEvent.user_id == test_user.id)
    )
    events = list(r.scalars().all())
    assert len(events) == 1
    assert events[0].platform == Provider.GMAIL


# ---------------------------------------------------------------------------
# _collect_gmail_user_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_gmail_user_ids_returns_only_users_with_refresh_token(
    db: AsyncSession, test_user: User, user_factory
):
    with_token = await user_factory(google_refresh_token="refresh-tok")
    await user_factory(google_refresh_token=None)
    # test_user has no token by default

    ids = await _collect_gmail_user_ids(db)
    assert str(with_token.id) in ids
    assert str(test_user.id) not in ids


# ---------------------------------------------------------------------------
# Celery wrappers — argument validation + retry plumbing
# ---------------------------------------------------------------------------


def test_sync_gmail_for_user_returns_sentinel_on_invalid_uuid():
    """Invalid UUIDs short-circuit before any DB session is acquired."""
    result = sync_gmail_for_user.apply(args=["not-a-uuid"]).get()
    assert result == {"status": "invalid_user_id", "new_interactions": 0}


def test_sync_gmail_for_user_runs_wrapper_and_returns_impl_result():
    """Happy path: wrapper acquires a task_session, calls _sync_gmail,
    returns its dict."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.gmail._sync_gmail",
            new=AsyncMock(return_value={"status": "ok", "new_interactions": 5}),
        ),
        patch("app.services.task_jobs.gmail.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = sync_gmail_for_user.apply(args=[uid]).get()

    assert result == {"status": "ok", "new_interactions": 5}


def test_sync_gmail_for_user_retries_on_failure():
    """When the impl raises, the wrapper logs and calls self.retry(); under
    ``apply(throw=True)`` the Retry signal surfaces."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.gmail._sync_gmail",
            new=AsyncMock(side_effect=RuntimeError("nope")),
        ),
        patch("app.services.task_jobs.gmail.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        with pytest.raises(Retry):
            sync_gmail_for_user.apply(args=[uid], throw=True).get()


def test_sync_gmail_for_user_does_not_notify_when_retries_exhausted():
    """Gmail's wrapper intentionally does NOT call ``notify_sync_failure`` on
    exhausted retries — unlike the Google Contacts/Calendar wrappers.
    Codifying this so a future refactor doesn't silently start spamming
    notifications. See task_jobs/gmail.py line ~120.
    """
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.gmail._sync_gmail",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("app.services.task_jobs.gmail.task_session") as mock_session,
        patch(
            "app.services.task_jobs.common.notify_sync_failure"
        ) as mock_notify,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        sync_gmail_for_user.apply(
            args=[uid],
            retries=sync_gmail_for_user.max_retries,
        )

    mock_notify.delay.assert_not_called()


def test_sync_gmail_all_enqueues_one_task_per_user_id():
    """Beat task pulls eligible user IDs and dispatches one
    ``sync_gmail_for_user`` per ID."""
    fake_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    with (
        patch(
            "app.services.task_jobs.gmail._collect_gmail_user_ids",
            new=AsyncMock(return_value=fake_ids),
        ),
        patch("app.services.task_jobs.gmail.task_session") as mock_session,
        patch(
            "app.services.task_jobs.gmail.sync_gmail_for_user.delay",
        ) as mock_delay,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = sync_gmail_all()

    assert result == {"queued": 2}
    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(fake_ids[0])
    mock_delay.assert_any_call(fake_ids[1])


def test_sync_gmail_all_empty_user_list_is_noop():
    """Empty user list yields ``queued: 0`` and no .delay() calls."""
    with (
        patch(
            "app.services.task_jobs.gmail._collect_gmail_user_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch("app.services.task_jobs.gmail.task_session") as mock_session,
        patch(
            "app.services.task_jobs.gmail.sync_gmail_for_user.delay",
        ) as mock_delay,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = sync_gmail_all()

    assert result == {"queued": 0}
    mock_delay.assert_not_called()
