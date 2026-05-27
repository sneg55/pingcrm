"""Unit tests for app.services.task_jobs.telegram_maintenance.

These tests exercise the lifted ``_collect_telegram_user_ids`` coroutine
against a real Postgres test database (via the conftest ``db`` fixture) and
the three ``@shared_task`` Celery entrypoints by invoking them via ``.apply()``
with the external boundary (Redis client / per-user sync tasks) mocked at the
``task_jobs.telegram_maintenance`` module level.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.task_jobs.telegram_maintenance import (
    _collect_telegram_user_ids,
    cleanup_stale_telegram_locks,
    recheck_telegram_bios_all,
    sync_telegram_all,
)


# ---------------------------------------------------------------------------
# _collect_telegram_user_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_user_ids_returns_only_users_with_telegram_session(
    db: AsyncSession, test_user: User, user_factory
):
    with_session = await user_factory(telegram_session="encrypted-session-blob")
    await user_factory(telegram_session=None)
    # test_user also has no telegram_session by default

    ids = await _collect_telegram_user_ids(db)
    assert str(with_session.id) in ids
    assert str(test_user.id) not in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_collect_user_ids_empty_when_no_sessions(db: AsyncSession, test_user: User):
    ids = await _collect_telegram_user_ids(db)
    assert ids == []


@pytest.mark.asyncio
async def test_collect_user_ids_returns_stringified_uuids(
    db: AsyncSession, user_factory
):
    """IDs must be stringified — downstream ``.delay()`` calls expect str args."""
    u = await user_factory(telegram_session="tok")
    ids = await _collect_telegram_user_ids(db)
    assert ids == [str(u.id)]
    assert isinstance(ids[0], str)


# ---------------------------------------------------------------------------
# cleanup_stale_telegram_locks
# ---------------------------------------------------------------------------


def _fake_redis(
    lock_keys: list[bytes | str],
    *,
    has_progress: dict[str, bool] | None = None,
    ttls: dict[str, int] | None = None,
) -> MagicMock:
    """Build a MagicMock that mimics the subset of redis client used by the task."""
    has_progress = has_progress or {}
    ttls = ttls or {}
    r = MagicMock()
    r.scan_iter.return_value = iter(lock_keys)
    r.exists.side_effect = lambda key: 1 if has_progress.get(key, False) else 0
    r.ttl.side_effect = lambda key: ttls.get(
        key.decode() if isinstance(key, bytes) else key, 0
    )
    r.delete = MagicMock()
    return r


def test_cleanup_deletes_stale_lock_with_no_progress_and_short_ttl():
    """Lock with no progress key + TTL < 2700 → deleted."""
    fake = _fake_redis(
        lock_keys=[b"tg_sync_lock:user-a"],
        has_progress={"tg_sync_progress:user-a": False},
        ttls={"tg_sync_lock:user-a": 1000},
    )
    with patch(
        "app.services.task_jobs.telegram_maintenance._redis.from_url",
        return_value=fake,
    ):
        result = cleanup_stale_telegram_locks.apply().get()

    assert result == {"scanned": 1, "deleted": 1}
    fake.delete.assert_called_once_with(b"tg_sync_lock:user-a")


def test_cleanup_skips_lock_with_active_progress_key():
    """Lock with an active progress key must NOT be deleted, even if TTL is low."""
    fake = _fake_redis(
        lock_keys=[b"tg_sync_lock:user-b"],
        has_progress={"tg_sync_progress:user-b": True},
        ttls={"tg_sync_lock:user-b": 100},
    )
    with patch(
        "app.services.task_jobs.telegram_maintenance._redis.from_url",
        return_value=fake,
    ):
        result = cleanup_stale_telegram_locks.apply().get()

    assert result == {"scanned": 1, "deleted": 0}
    fake.delete.assert_not_called()


def test_cleanup_skips_lock_with_high_ttl():
    """Lock with TTL >= 2700 (fresh lock) must not be deleted — sync is plausibly
    still running and just hasn't yet written its progress key."""
    fake = _fake_redis(
        lock_keys=[b"tg_sync_lock:user-c"],
        has_progress={"tg_sync_progress:user-c": False},
        ttls={"tg_sync_lock:user-c": 3000},
    )
    with patch(
        "app.services.task_jobs.telegram_maintenance._redis.from_url",
        return_value=fake,
    ):
        result = cleanup_stale_telegram_locks.apply().get()

    assert result == {"scanned": 1, "deleted": 0}
    fake.delete.assert_not_called()


def test_cleanup_skips_lock_when_ttl_minus_two():
    """TTL == -2 means the key was deleted between scan_iter and ttl(). Skip."""
    fake = _fake_redis(
        lock_keys=[b"tg_sync_lock:user-d"],
        has_progress={"tg_sync_progress:user-d": False},
        ttls={"tg_sync_lock:user-d": -2},
    )
    with patch(
        "app.services.task_jobs.telegram_maintenance._redis.from_url",
        return_value=fake,
    ):
        result = cleanup_stale_telegram_locks.apply().get()

    assert result == {"scanned": 1, "deleted": 0}
    fake.delete.assert_not_called()


def test_cleanup_handles_string_lock_keys():
    """scan_iter can return str (decode_responses=True) — must handle without decode."""
    fake = _fake_redis(
        lock_keys=["tg_sync_lock:user-e"],
        has_progress={"tg_sync_progress:user-e": False},
        ttls={"tg_sync_lock:user-e": 500},
    )
    with patch(
        "app.services.task_jobs.telegram_maintenance._redis.from_url",
        return_value=fake,
    ):
        result = cleanup_stale_telegram_locks.apply().get()

    assert result == {"scanned": 1, "deleted": 1}


def test_cleanup_returns_error_dict_on_unexpected_failure():
    """Redis exploding mid-scan must not propagate — return an error dict."""
    fake = MagicMock()
    fake.scan_iter.side_effect = RuntimeError("connection refused")
    with patch(
        "app.services.task_jobs.telegram_maintenance._redis.from_url",
        return_value=fake,
    ):
        result = cleanup_stale_telegram_locks.apply().get()

    assert result == {"scanned": 0, "deleted": 0, "error": True}


def test_cleanup_with_no_locks_returns_zero_counts():
    fake = _fake_redis(lock_keys=[])
    with patch(
        "app.services.task_jobs.telegram_maintenance._redis.from_url",
        return_value=fake,
    ):
        result = cleanup_stale_telegram_locks.apply().get()

    assert result == {"scanned": 0, "deleted": 0}


def test_cleanup_mixed_locks_deletes_only_stale_ones():
    """Three locks: one stale, one with progress, one fresh — only stale gets deleted."""
    keys = [
        b"tg_sync_lock:stale",
        b"tg_sync_lock:active",
        b"tg_sync_lock:fresh",
    ]
    fake = _fake_redis(
        lock_keys=keys,
        has_progress={
            "tg_sync_progress:stale": False,
            "tg_sync_progress:active": True,
            "tg_sync_progress:fresh": False,
        },
        ttls={
            "tg_sync_lock:stale": 500,
            "tg_sync_lock:active": 500,
            "tg_sync_lock:fresh": 3500,
        },
    )
    with patch(
        "app.services.task_jobs.telegram_maintenance._redis.from_url",
        return_value=fake,
    ):
        result = cleanup_stale_telegram_locks.apply().get()

    assert result == {"scanned": 3, "deleted": 1}
    fake.delete.assert_called_once_with(b"tg_sync_lock:stale")


# ---------------------------------------------------------------------------
# recheck_telegram_bios_all
# ---------------------------------------------------------------------------


def test_recheck_bios_all_queues_one_per_user_id():
    """Each collected user ID dispatches sync_telegram_bios_for_user.delay
    with exclude_2nd_tier=True, stale_days=3."""
    fake_ids = ["uid-1", "uid-2", "uid-3"]
    with (
        patch(
            "app.services.task_jobs.telegram_maintenance._collect_telegram_user_ids",
            new_callable=AsyncMock,
        ) as mock_collect,
        patch(
            "app.services.task_jobs.telegram_maintenance.task_session",
        ) as mock_session,
        patch(
            "app.services.task_jobs.telegram_maintenance.sync_telegram_bios_for_user.delay",
        ) as mock_delay,
    ):
        mock_collect.return_value = fake_ids

        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = recheck_telegram_bios_all.apply().get()

    assert result == {"queued": 3}
    assert mock_delay.call_count == 3
    for uid in fake_ids:
        mock_delay.assert_any_call(uid, exclude_2nd_tier=True, stale_days=3)


def test_recheck_bios_all_no_users_queued_returns_zero():
    with (
        patch(
            "app.services.task_jobs.telegram_maintenance._collect_telegram_user_ids",
            new_callable=AsyncMock,
        ) as mock_collect,
        patch(
            "app.services.task_jobs.telegram_maintenance.task_session",
        ) as mock_session,
        patch(
            "app.services.task_jobs.telegram_maintenance.sync_telegram_bios_for_user.delay",
        ) as mock_delay,
    ):
        mock_collect.return_value = []

        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = recheck_telegram_bios_all.apply().get()

    assert result == {"queued": 0}
    mock_delay.assert_not_called()


# ---------------------------------------------------------------------------
# sync_telegram_all
# ---------------------------------------------------------------------------


def test_sync_telegram_all_invokes_sync_telegram_for_user_directly():
    """Quirk codification: sync_telegram_all calls sync_telegram_for_user(uid)
    *synchronously* (not via .delay) — see telegram_maintenance.py current line
    where it iterates user_ids and calls the function directly. This is despite
    the docstring saying "enqueue" — preserved as-is.
    """
    fake_ids = ["uid-a", "uid-b"]
    with (
        patch(
            "app.services.task_jobs.telegram_maintenance._collect_telegram_user_ids",
            new_callable=AsyncMock,
        ) as mock_collect,
        patch(
            "app.services.task_jobs.telegram_maintenance.task_session",
        ) as mock_session,
        patch(
            "app.services.task_jobs.telegram_maintenance.sync_telegram_for_user",
        ) as mock_sync,
    ):
        mock_collect.return_value = fake_ids

        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = sync_telegram_all.apply().get()

    assert result == {"queued": 2}
    assert mock_sync.call_count == 2
    mock_sync.assert_any_call("uid-a")
    mock_sync.assert_any_call("uid-b")
    # Crucially: .delay was NOT used (the quirk)
    assert not mock_sync.delay.called


def test_sync_telegram_all_no_users_returns_zero():
    with (
        patch(
            "app.services.task_jobs.telegram_maintenance._collect_telegram_user_ids",
            new_callable=AsyncMock,
        ) as mock_collect,
        patch(
            "app.services.task_jobs.telegram_maintenance.task_session",
        ) as mock_session,
        patch(
            "app.services.task_jobs.telegram_maintenance.sync_telegram_for_user",
        ) as mock_sync,
    ):
        mock_collect.return_value = []

        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = sync_telegram_all.apply().get()

    assert result == {"queued": 0}
    mock_sync.assert_not_called()


