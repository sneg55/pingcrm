"""Unit tests for app.services.task_jobs.whatsapp.

These tests exercise the lifted ``_sync_whatsapp_backfill`` /
``_check_whatsapp_sessions`` coroutines against a real Postgres test database
(via the conftest ``db`` fixture). The external integration boundary
(``trigger_backfill`` / ``get_status``) is mocked at the ``task_jobs.whatsapp``
module level so we cover the orchestration logic — credential gating, sync-event
recording, dead-session handling, notifications, error paths — without hitting
the sidecar.

The Celery entrypoint wrappers are tested separately by invoking them via
``.apply()`` so retries surface as ``celery.exceptions.Retry`` exceptions
instead of dispatching to a broker.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from celery.exceptions import Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.sync_event import SyncEvent
from app.models.user import User
from app.services.task_jobs.whatsapp import (
    _check_whatsapp_sessions,
    _sync_whatsapp_backfill,
    check_whatsapp_sessions,
    sync_whatsapp_backfill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _notifications_for(db: AsyncSession, user_id: uuid.UUID) -> list[Notification]:
    r = await db.execute(select(Notification).where(Notification.user_id == user_id))
    return list(r.scalars().all())


async def _sync_events_for(db: AsyncSession, user_id: uuid.UUID) -> list[SyncEvent]:
    r = await db.execute(select(SyncEvent).where(SyncEvent.user_id == user_id))
    return list(r.scalars().all())


async def _fetch_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Re-fetch via db (user_factory binds to db_session, not db)."""
    r = await db.execute(select(User).where(User.id == user_id))
    return r.scalar_one()


# ---------------------------------------------------------------------------
# _sync_whatsapp_backfill — early exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_user_not_found(db: AsyncSession):
    result = await _sync_whatsapp_backfill(db, uuid.uuid4())
    assert result == {"status": "user_not_found", "records_created": 0}


@pytest.mark.asyncio
async def test_backfill_not_connected(db: AsyncSession, test_user: User):
    # whatsapp_connected defaults to False
    result = await _sync_whatsapp_backfill(db, test_user.id)
    assert result == {"status": "not_connected", "records_created": 0}
    # No sync events recorded when the early exit fires
    assert await _sync_events_for(db, test_user.id) == []


# ---------------------------------------------------------------------------
# _sync_whatsapp_backfill — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_happy_path_messages_imported_key(
    db: AsyncSession, test_user: User
):
    """When the sidecar returns ``messages_imported``, that count flows into the
    SyncEvent and the result dict."""
    test_user.whatsapp_connected = True
    await db.commit()

    payload = {"messages_imported": 42, "extra": "stuff"}
    with patch(
        "app.services.task_jobs.whatsapp.trigger_backfill",
        new=AsyncMock(return_value=payload),
    ) as mock_trigger:
        result = await _sync_whatsapp_backfill(db, test_user.id)

    assert result == {"status": "ok", "records_created": 42}
    mock_trigger.assert_awaited_once_with(str(test_user.id))

    events = await _sync_events_for(db, test_user.id)
    assert len(events) == 1
    assert events[0].platform == "whatsapp"
    assert events[0].sync_type == "manual"
    assert events[0].status == "success"
    assert events[0].records_created == 42
    # details JSON-serialized
    assert json.loads(events[0].details) == payload


@pytest.mark.asyncio
async def test_backfill_falls_back_to_total_key(
    db: AsyncSession, test_user: User
):
    """If the sidecar omits ``messages_imported``, the code uses ``total``."""
    test_user.whatsapp_connected = True
    await db.commit()

    with patch(
        "app.services.task_jobs.whatsapp.trigger_backfill",
        new=AsyncMock(return_value={"total": 7}),
    ):
        result = await _sync_whatsapp_backfill(db, test_user.id)

    assert result == {"status": "ok", "records_created": 7}
    events = await _sync_events_for(db, test_user.id)
    assert events[0].records_created == 7


@pytest.mark.asyncio
async def test_backfill_defaults_count_to_zero_when_neither_key_present(
    db: AsyncSession, test_user: User
):
    """If the sidecar returns neither ``messages_imported`` nor ``total``, the
    count is 0 — quirk preserved verbatim from the original closure."""
    test_user.whatsapp_connected = True
    await db.commit()

    with patch(
        "app.services.task_jobs.whatsapp.trigger_backfill",
        new=AsyncMock(return_value={}),
    ):
        result = await _sync_whatsapp_backfill(db, test_user.id)

    assert result == {"status": "ok", "records_created": 0}


# ---------------------------------------------------------------------------
# _sync_whatsapp_backfill — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_sidecar_failure_records_failure_and_reraises(
    db: AsyncSession, test_user: User
):
    """Sidecar throw → record_sync_failure runs, sync_event committed as failed,
    and the exception propagates so the Celery wrapper can retry."""
    test_user.whatsapp_connected = True
    await db.commit()

    with patch(
        "app.services.task_jobs.whatsapp.trigger_backfill",
        new=AsyncMock(side_effect=RuntimeError("sidecar down")),
    ):
        with pytest.raises(RuntimeError, match="sidecar down"):
            await _sync_whatsapp_backfill(db, test_user.id)

    events = await _sync_events_for(db, test_user.id)
    assert len(events) == 1
    assert events[0].status == "failed"
    assert "sidecar down" in (events[0].error_message or "")


# ---------------------------------------------------------------------------
# _check_whatsapp_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_sessions_no_connected_users(db: AsyncSession, test_user: User):
    """When nobody has whatsapp_connected=True, checked=0 and dead=0."""
    with patch(
        "app.services.task_jobs.whatsapp.get_status",
        new=AsyncMock(return_value="connected"),
    ) as mock_status:
        result = await _check_whatsapp_sessions(db)

    assert result == {"checked": 0, "dead_sessions": 0}
    mock_status.assert_not_called()


@pytest.mark.asyncio
async def test_check_sessions_all_connected(db: AsyncSession, user_factory):
    """Sidecar reports 'connected' for everyone → no users flipped, no notifs."""
    u1 = await user_factory(whatsapp_connected=True)
    u2 = await user_factory(whatsapp_connected=True)

    with patch(
        "app.services.task_jobs.whatsapp.get_status",
        new=AsyncMock(return_value="connected"),
    ) as mock_status:
        result = await _check_whatsapp_sessions(db)

    assert result == {"checked": 2, "dead_sessions": 0}
    assert mock_status.await_count == 2

    u1_fresh = await _fetch_user(db, u1.id)
    u2_fresh = await _fetch_user(db, u2.id)
    assert u1_fresh.whatsapp_connected is True
    assert u2_fresh.whatsapp_connected is True
    assert await _notifications_for(db, u1.id) == []
    assert await _notifications_for(db, u2.id) == []


@pytest.mark.asyncio
async def test_check_sessions_dead_session_flips_flag_and_notifies(
    db: AsyncSession, user_factory
):
    """A non-'connected' status flips whatsapp_connected to False and creates
    a 'WhatsApp session disconnected' notification linked to /settings."""
    dead = await user_factory(whatsapp_connected=True)
    alive = await user_factory(whatsapp_connected=True)

    async def fake_status(uid: str) -> str:
        return "disconnected" if uid == str(dead.id) else "connected"

    with patch(
        "app.services.task_jobs.whatsapp.get_status",
        new=AsyncMock(side_effect=fake_status),
    ):
        result = await _check_whatsapp_sessions(db)

    assert result == {"checked": 2, "dead_sessions": 1}

    dead_fresh = await _fetch_user(db, dead.id)
    alive_fresh = await _fetch_user(db, alive.id)
    assert dead_fresh.whatsapp_connected is False
    assert alive_fresh.whatsapp_connected is True

    notifs = await _notifications_for(db, dead.id)
    assert len(notifs) == 1
    assert notifs[0].title == "WhatsApp session disconnected"
    assert notifs[0].link == "/settings"
    assert notifs[0].notification_type == "sync"
    assert await _notifications_for(db, alive.id) == []


@pytest.mark.asyncio
async def test_check_sessions_sidecar_error_treated_as_dead(
    db: AsyncSession, user_factory
):
    """If get_status raises, status is set to 'error' (logged) and the user is
    treated as dead — flag flipped, notification created."""
    user = await user_factory(whatsapp_connected=True)

    with patch(
        "app.services.task_jobs.whatsapp.get_status",
        new=AsyncMock(side_effect=RuntimeError("sidecar gone")),
    ):
        result = await _check_whatsapp_sessions(db)

    assert result == {"checked": 1, "dead_sessions": 1}
    user_fresh = await _fetch_user(db, user.id)
    assert user_fresh.whatsapp_connected is False
    notifs = await _notifications_for(db, user.id)
    assert len(notifs) == 1
    assert notifs[0].title == "WhatsApp session disconnected"


# ---------------------------------------------------------------------------
# Celery wrappers — argument validation + retry plumbing
# ---------------------------------------------------------------------------


def test_backfill_wrapper_returns_sentinel_on_invalid_uuid():
    result = sync_whatsapp_backfill.apply(args=["not-a-uuid"]).get()
    assert result == {"status": "invalid_user_id", "records_created": 0}


def test_backfill_wrapper_runs_impl_and_returns_result():
    """Cover the Celery wrapper's _runner + _run path with a successful impl."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.whatsapp._sync_whatsapp_backfill",
            new=AsyncMock(return_value={"status": "ok", "records_created": 5}),
        ),
        patch("app.services.task_jobs.whatsapp.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = sync_whatsapp_backfill.apply(args=[uid]).get()

    assert result == {"status": "ok", "records_created": 5}


def test_backfill_wrapper_retries_on_failure():
    """When the impl raises, the wrapper logs and calls self.retry()."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.whatsapp._sync_whatsapp_backfill",
            new=AsyncMock(side_effect=RuntimeError("nope")),
        ),
        patch("app.services.task_jobs.whatsapp.task_session") as mock_session,
        patch("app.services.task_jobs.whatsapp.notify_sync_failure") as mock_notify,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        with pytest.raises(Retry):
            sync_whatsapp_backfill.apply(args=[uid], throw=True).get()

    # Not yet exhausted on the first attempt
    assert mock_notify.delay.call_count == 0


def test_backfill_wrapper_notifies_when_retries_exhausted():
    """On the final retry attempt, notify_sync_failure.delay fires once with
    the 'WhatsApp backfill' label so the user sees the failure in-app."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.whatsapp._sync_whatsapp_backfill",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("app.services.task_jobs.whatsapp.task_session") as mock_session,
        patch("app.services.task_jobs.whatsapp.notify_sync_failure") as mock_notify,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        sync_whatsapp_backfill.apply(
            args=[uid],
            retries=sync_whatsapp_backfill.max_retries,
        )

    mock_notify.delay.assert_called_once()
    args = mock_notify.delay.call_args.args
    assert args[0] == uid
    assert args[1] == "WhatsApp backfill"


def test_check_sessions_wrapper_runs_impl():
    """Cover the check_whatsapp_sessions Celery wrapper's _runner + _run path."""
    with (
        patch(
            "app.services.task_jobs.whatsapp._check_whatsapp_sessions",
            new=AsyncMock(return_value={"checked": 3, "dead_sessions": 1}),
        ),
        patch("app.services.task_jobs.whatsapp.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = check_whatsapp_sessions.apply().get()

    assert result == {"checked": 3, "dead_sessions": 1}
