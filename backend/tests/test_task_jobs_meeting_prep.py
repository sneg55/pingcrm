"""Unit tests for app.services.task_jobs.meeting_prep.

These tests exercise the lifted ``_scan_meeting_preps`` coroutine against a real
Postgres test database (via the conftest ``db`` fixture). The external boundary
(``send_email``, ``get_upcoming_meetings``, ``build_prep_brief``,
``generate_talking_points``, ``compose_prep_email``) is mocked at the
``task_jobs.meeting_prep`` module level so we cover the orchestration logic —
user enumeration, settings gating, dedup, account selection, error paths —
without hitting Gmail or Anthropic.

The Celery entrypoint wrapper is tested separately by invoking it via
``.apply()`` so retries surface as ``celery.exceptions.Retry`` exceptions
instead of dispatching to a broker.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import Retry
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.google_account import GoogleAccount
from app.models.notification import Notification
from app.models.user import User
from app.services.task_jobs.meeting_prep import (
    _scan_meeting_preps,
    scan_meeting_preps,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_redis(exists_return: bool = False) -> MagicMock:
    """Build a MagicMock that quacks like the redis client used in the task."""
    r = MagicMock()
    r.exists.return_value = exists_return
    r.set.return_value = True
    return r


def _meeting(event_id: str = "evt-1", title: str = "Strategy sync", contact_ids=None) -> dict:
    from datetime import UTC, datetime
    return {
        "event_id": event_id,
        "title": title,
        "occurred_at": datetime.now(UTC),
        "contact_ids": list(contact_ids) if contact_ids is not None else [uuid.uuid4()],
    }


# ---------------------------------------------------------------------------
# _scan_meeting_preps — early exit when no users are Google-connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_zero_counts_when_no_google_users(db: AsyncSession):
    """No GoogleAccount rows + no legacy user.google_refresh_token → bail out."""
    result = await _scan_meeting_preps(db, _fake_redis())
    assert result == {"sent": 0, "skipped": 0, "errors": 0}


@pytest.mark.asyncio
async def test_returns_zero_counts_when_no_google_users_skips_other_users(
    db: AsyncSession, user_factory
):
    """A user without a Google token must not appear in the result counts."""
    await user_factory(google_refresh_token=None)
    result = await _scan_meeting_preps(db, _fake_redis())
    assert result == {"sent": 0, "skipped": 0, "errors": 0}


# ---------------------------------------------------------------------------
# Settings gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skips_user_when_meeting_prep_disabled(
    db: AsyncSession, test_user: User
):
    """sync_settings['gmail']['meeting_prep_enabled']=False → user counted as skipped."""
    test_user.google_refresh_token = "legacy-tok"
    test_user.sync_settings = {"gmail": {"meeting_prep_enabled": False}}
    await db.commit()

    with patch(
        "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
        new=AsyncMock(return_value=[]),
    ) as mock_meetings:
        result = await _scan_meeting_preps(db, _fake_redis())

    assert result["skipped"] == 1
    assert result["sent"] == 0
    assert result["errors"] == 0
    # Disabled → we never even fetched meetings for that user
    mock_meetings.assert_not_awaited()


@pytest.mark.asyncio
async def test_default_meeting_prep_enabled_is_true(
    db: AsyncSession, test_user: User
):
    """Empty sync_settings dict → meeting_prep_enabled defaults to True
    (i.e. we DO call get_upcoming_meetings for that user)."""
    test_user.google_refresh_token = "tok"
    test_user.sync_settings = None
    await db.commit()

    with patch(
        "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
        new=AsyncMock(return_value=[]),
    ) as mock_meetings:
        result = await _scan_meeting_preps(db, _fake_redis())

    assert result["sent"] == 0
    mock_meetings.assert_awaited_once()


# ---------------------------------------------------------------------------
# Dedup, no-contact, no-brief skip paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedup_skips_meeting_already_seen(
    db: AsyncSession, test_user: User
):
    """A meeting whose dedup key exists in Redis must be counted as skipped."""
    test_user.google_refresh_token = "tok"
    await db.commit()

    meeting = _meeting()
    with (
        patch(
            "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
            new=AsyncMock(return_value=[meeting]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.build_prep_brief",
            new=AsyncMock(return_value=[{"name": "X"}]),
        ) as mock_brief,
        patch(
            "app.services.task_jobs.meeting_prep.send_email",
            return_value=True,
        ) as mock_send,
    ):
        r = _fake_redis(exists_return=True)
        result = await _scan_meeting_preps(db, r)

    assert result["skipped"] == 1
    assert result["sent"] == 0
    # Dedup short-circuits before brief / send
    mock_brief.assert_not_awaited()
    mock_send.assert_not_called()
    r.exists.assert_called()


@pytest.mark.asyncio
async def test_skips_meeting_with_no_contact_ids(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    await db.commit()

    meeting = _meeting(contact_ids=[])
    with (
        patch(
            "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
            new=AsyncMock(return_value=[meeting]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.build_prep_brief",
            new=AsyncMock(return_value=[]),
        ) as mock_brief,
    ):
        result = await _scan_meeting_preps(db, _fake_redis())

    assert result["skipped"] == 1
    mock_brief.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_meeting_when_brief_is_empty(
    db: AsyncSession, test_user: User
):
    """Unknown contacts → build_prep_brief returns [] → skip without sending."""
    test_user.google_refresh_token = "tok"
    await db.commit()

    meeting = _meeting()
    with (
        patch(
            "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
            new=AsyncMock(return_value=[meeting]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.build_prep_brief",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.send_email",
            return_value=True,
        ) as mock_send,
    ):
        result = await _scan_meeting_preps(db, _fake_redis())

    assert result["skipped"] == 1
    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Send paths — happy + auth_error + generic error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sends_prep_email_via_google_account_row(
    db: AsyncSession, test_user: User
):
    """A GoogleAccount row → that account is used for send (not the legacy token)."""
    test_user.google_refresh_token = "legacy-should-NOT-be-used"
    ga = GoogleAccount(
        user_id=test_user.id,
        email="primary@example.com",
        refresh_token="ga-refresh-tok",
    )
    db.add(ga)
    await db.commit()

    meeting = _meeting()
    with (
        patch(
            "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
            new=AsyncMock(return_value=[meeting]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.build_prep_brief",
            new=AsyncMock(return_value=[{"name": "Alice"}]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.generate_talking_points",
            new=AsyncMock(return_value="- talk"),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.compose_prep_email",
            return_value=("Subject", "<p>HTML</p>"),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.send_email",
            return_value=True,
        ) as mock_send,
    ):
        r = _fake_redis(exists_return=False)
        result = await _scan_meeting_preps(db, r)

    assert result == {"sent": 1, "skipped": 0, "errors": 0}
    # Send used the GoogleAccount row (refresh_token="ga-refresh-tok"), not the legacy
    sent_account = mock_send.call_args.args[0]
    assert sent_account.refresh_token == "ga-refresh-tok"
    # Dedup key set with 24h TTL after a successful send
    r.set.assert_called_once()
    set_args, set_kwargs = r.set.call_args
    assert set_args[0].startswith(f"meeting_prep:{test_user.id}:")
    assert set_kwargs.get("ex") == 86400


@pytest.mark.asyncio
async def test_sends_via_legacy_token_when_no_google_account_row(
    db: AsyncSession, test_user: User
):
    """No GoogleAccount row → falls back to user.google_refresh_token via SimpleNamespace."""
    test_user.google_refresh_token = "legacy-tok"
    await db.commit()

    meeting = _meeting()
    with (
        patch(
            "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
            new=AsyncMock(return_value=[meeting]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.build_prep_brief",
            new=AsyncMock(return_value=[{"name": "Alice"}]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.generate_talking_points",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.compose_prep_email",
            return_value=("Subject", "<p>HTML</p>"),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.send_email",
            return_value=True,
        ) as mock_send,
    ):
        result = await _scan_meeting_preps(db, _fake_redis())

    assert result["sent"] == 1
    sent_account = mock_send.call_args.args[0]
    assert sent_account.refresh_token == "legacy-tok"
    assert sent_account.email == test_user.email


@pytest.mark.asyncio
async def test_auth_error_writes_notification_and_breaks_for_user(
    db: AsyncSession, test_user: User
):
    """send_email returns 'auth_error' → write a 'system' notification and stop
    processing remaining meetings for this user (break)."""
    test_user.google_refresh_token = "legacy-tok"
    await db.commit()

    m1 = _meeting(event_id="e1")
    m2 = _meeting(event_id="e2")
    with (
        patch(
            "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
            new=AsyncMock(return_value=[m1, m2]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.build_prep_brief",
            new=AsyncMock(return_value=[{"name": "Alice"}]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.generate_talking_points",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.compose_prep_email",
            return_value=("Subject", "<p>HTML</p>"),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.send_email",
            return_value="auth_error",
        ) as mock_send,
    ):
        result = await _scan_meeting_preps(db, _fake_redis())

    # No counters bumped for auth_error — it's neither sent nor errored nor skipped
    assert result == {"sent": 0, "skipped": 0, "errors": 0}
    # Only the first meeting attempted: break stops the per-user loop
    assert mock_send.call_count == 1

    # Notification persisted
    from sqlalchemy import select
    notifs = list(
        (await db.execute(
            select(Notification).where(Notification.user_id == test_user.id)
        )).scalars().all()
    )
    assert len(notifs) == 1
    assert notifs[0].notification_type == "system"
    assert "Re-authorize Gmail" in notifs[0].title
    assert notifs[0].link == "/settings"


@pytest.mark.asyncio
async def test_send_email_failure_counts_as_error(
    db: AsyncSession, test_user: User
):
    """send_email returns False (network blip) → errors counter +1, no notification."""
    test_user.google_refresh_token = "tok"
    await db.commit()

    meeting = _meeting()
    with (
        patch(
            "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
            new=AsyncMock(return_value=[meeting]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.build_prep_brief",
            new=AsyncMock(return_value=[{"name": "Alice"}]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.generate_talking_points",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.compose_prep_email",
            return_value=("Subject", "<p>HTML</p>"),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.send_email",
            return_value=False,
        ),
    ):
        r = _fake_redis(exists_return=False)
        result = await _scan_meeting_preps(db, r)

    assert result == {"sent": 0, "skipped": 0, "errors": 1}
    # No dedup key set on failure — so we'll retry next tick
    r.set.assert_not_called()


# ---------------------------------------------------------------------------
# Multi-user flow — verifies bulk fetch + per-user iteration aggregates correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_users_aggregated_counts(
    db: AsyncSession, user_factory
):
    """Two Google-connected users, each with one sendable meeting → sent == 2.

    Verifies the bulk-fetch path that joins ga_user_ids ∪ legacy_user_ids and
    iterates per-user without N+1.
    """
    u1 = await user_factory(google_refresh_token="legacy-u1")
    u2 = await user_factory(google_refresh_token=None)
    db.add(GoogleAccount(
        user_id=u2.id, email="u2@example.com", refresh_token="ga-u2",
    ))
    await db.commit()

    with (
        patch(
            "app.services.task_jobs.meeting_prep.get_upcoming_meetings",
            new=AsyncMock(return_value=[_meeting()]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.build_prep_brief",
            new=AsyncMock(return_value=[{"name": "Alice"}]),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.generate_talking_points",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.compose_prep_email",
            return_value=("S", "<p>H</p>"),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.send_email",
            return_value=True,
        ) as mock_send,
    ):
        result = await _scan_meeting_preps(db, _fake_redis())

    assert result["sent"] == 2
    assert mock_send.call_count == 2


# ---------------------------------------------------------------------------
# Celery wrapper — argument validation + retry plumbing
# ---------------------------------------------------------------------------


def test_scan_meeting_preps_celery_wrapper_runs_runner_and_returns_dict():
    """Cover the Celery wrapper's _runner + _run path."""
    fake_result = {"sent": 3, "skipped": 1, "errors": 0}
    with (
        patch(
            "app.services.task_jobs.meeting_prep._scan_meeting_preps",
            new=AsyncMock(return_value=fake_result),
        ) as mock_impl,
        patch(
            "app.services.task_jobs.meeting_prep.task_session"
        ) as mock_session,
        patch(
            "app.services.task_jobs.meeting_prep._redis.from_url"
        ) as mock_redis_factory,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm
        fake_r = MagicMock()
        mock_redis_factory.return_value = fake_r

        result = scan_meeting_preps.apply().get()

    assert result == fake_result
    mock_impl.assert_awaited_once()
    # The redis client built by from_url(settings.REDIS_URL) is forwarded
    # to the impl as the second positional arg
    _, called_redis = mock_impl.await_args.args
    assert called_redis is fake_r


def test_scan_meeting_preps_retries_on_impl_failure():
    """When the impl raises, the wrapper logs and calls self.retry()."""
    with (
        patch(
            "app.services.task_jobs.meeting_prep._scan_meeting_preps",
            new=AsyncMock(side_effect=RuntimeError("nope")),
        ),
        patch(
            "app.services.task_jobs.meeting_prep.task_session"
        ) as mock_session,
        patch(
            "app.services.task_jobs.meeting_prep._redis.from_url",
            return_value=MagicMock(),
        ),
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        with pytest.raises(Retry):
            scan_meeting_preps.apply(throw=True).get()


# ---------------------------------------------------------------------------
# Registration + beat schedule
# ---------------------------------------------------------------------------


def test_task_registered_in_tasks_module():
    """The Celery task is re-exported from app.services.tasks so the worker
    discovers it."""
    from app.services.tasks import scan_meeting_preps as tsk
    assert callable(tsk)
    assert tsk.name == "app.services.tasks.scan_meeting_preps"
