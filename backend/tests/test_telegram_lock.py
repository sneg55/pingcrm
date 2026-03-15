"""Unit tests for token-based Telegram sync lock (compare-and-delete Lua script).

These tests verify the core correctness property:
  - Only the task that holds the lock (matching token) can release it.
  - A stale task with a wrong token cannot delete a newer task's lock.

Uses fakeredis[lua] (lupa) for Lua script support without a real Redis server.
"""
from __future__ import annotations

import os
import unittest.mock

import fakeredis
import pytest

# Ensure settings are available before importing app modules
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("ENCRYPTION_KEY", "HiuobeEdnSk93dMtnycRm8Kob9D3-7-vCw3_L0YG9Ek=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://localhost:5432/pingcrm_test")


@pytest.fixture()
def fr():
    """Provide a fakeredis instance with Lua scripting enabled (requires lupa)."""
    return fakeredis.FakeRedis()


# ---------------------------------------------------------------------------
# Helpers that operate directly on the fake Redis instance
# ---------------------------------------------------------------------------

def _acquire(r: fakeredis.FakeRedis, user_id: str, token: str, ex: int = 3600) -> bool:
    """Acquire the lock by setting the key with NX (only-if-not-exists)."""
    return bool(r.set(f"tg_sync_lock:{user_id}", token, nx=True, ex=ex))


def _get_value(r: fakeredis.FakeRedis, user_id: str) -> bytes | None:
    """Read the current lock value (raw bytes)."""
    return r.get(f"tg_sync_lock:{user_id}")


# ---------------------------------------------------------------------------
# Tests for the Lua compare-and-delete script directly
# ---------------------------------------------------------------------------


def test_wrong_token_does_not_delete(fr):
    """A wrong token must not delete the lock — core correctness requirement."""
    from app.services.task_jobs.telegram import _RELEASE_LOCK_LUA

    user_id = "user-abc"
    real_token = "correct-token"
    wrong_token = "wrong-token"

    _acquire(fr, user_id, real_token)

    result = fr.eval(_RELEASE_LOCK_LUA, 1, f"tg_sync_lock:{user_id}", wrong_token)

    assert result == 0, "Lua script should return 0 when token does not match"
    assert _get_value(fr, user_id) == b"correct-token", "Lock must still exist after wrong-token attempt"


def test_correct_token_deletes_lock(fr):
    """The correct token must successfully delete the lock."""
    from app.services.task_jobs.telegram import _RELEASE_LOCK_LUA

    user_id = "user-abc"
    token = "correct-token"

    _acquire(fr, user_id, token)

    result = fr.eval(_RELEASE_LOCK_LUA, 1, f"tg_sync_lock:{user_id}", token)

    assert result == 1, "Lua script should return 1 when lock is released"
    assert _get_value(fr, user_id) is None, "Lock must be gone after correct-token release"


def test_release_absent_lock_returns_zero(fr):
    """Releasing a non-existent lock must return 0 (idempotent, safe)."""
    from app.services.task_jobs.telegram import _RELEASE_LOCK_LUA

    result = fr.eval(_RELEASE_LOCK_LUA, 1, "tg_sync_lock:no-user", "any-token")
    assert result == 0


def test_stale_task_cannot_steal_newer_lock(fr):
    """Simulate task A's lock expiring, task B re-acquiring, then stale A trying to release."""
    from app.services.task_jobs.telegram import _RELEASE_LOCK_LUA

    user_id = "user-overlap"
    token_a = "token-task-a"
    token_b = "token-task-b"

    # Task B now holds the lock (task A's lock expired, B re-acquired)
    _acquire(fr, user_id, token_b)

    # Stale task A tries to release with its own (now-stale) token
    result_stale = fr.eval(_RELEASE_LOCK_LUA, 1, f"tg_sync_lock:{user_id}", token_a)
    assert result_stale == 0, "Stale task A must not delete task B's lock"
    assert _get_value(fr, user_id) == b"token-task-b", "Task B's lock must remain intact"

    # Task B correctly releases its own lock
    result_b = fr.eval(_RELEASE_LOCK_LUA, 1, f"tg_sync_lock:{user_id}", token_b)
    assert result_b == 1
    assert _get_value(fr, user_id) is None


# ---------------------------------------------------------------------------
# Tests for the _release_lock() Python helper
# ---------------------------------------------------------------------------


def _make_release_lock_context(fake_r):
    """Return a context manager that patches redis.from_url to use fake_r."""
    return unittest.mock.patch("redis.from_url", return_value=fake_r)


def test_empty_token_is_noop(fr):
    """_release_lock with an empty token must be a no-op and return False."""
    _acquire(fr, "user-empty", "real-token")

    with _make_release_lock_context(fr), \
         unittest.mock.patch("app.core.config.settings") as s:
        s.REDIS_URL = "redis://localhost"
        from app.services.task_jobs.telegram import _release_lock
        result = _release_lock("user-empty", "")

    assert result is False
    assert _get_value(fr, "user-empty") == b"real-token", "Lock must not be touched when token is empty"


def test_helper_returns_true_on_correct_token(fr):
    """_release_lock() returns True when it holds the lock."""
    _acquire(fr, "user-helper", "helper-token")

    with _make_release_lock_context(fr), \
         unittest.mock.patch("app.core.config.settings") as s:
        s.REDIS_URL = "redis://localhost"
        from app.services.task_jobs.telegram import _release_lock
        result = _release_lock("user-helper", "helper-token")

    assert result is True
    assert _get_value(fr, "user-helper") is None


def test_helper_returns_false_on_wrong_token(fr):
    """_release_lock() returns False when the token doesn't match."""
    _acquire(fr, "user-mismatch", "real-token")

    with _make_release_lock_context(fr), \
         unittest.mock.patch("app.core.config.settings") as s:
        s.REDIS_URL = "redis://localhost"
        from app.services.task_jobs.telegram import _release_lock
        result = _release_lock("user-mismatch", "wrong-token")

    assert result is False
    assert _get_value(fr, "user-mismatch") == b"real-token"
