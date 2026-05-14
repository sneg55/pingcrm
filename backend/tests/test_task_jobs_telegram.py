"""Unit tests for app.services.task_jobs.telegram — Celery task orchestration.

These tests cover the orchestration layer of the Telegram sync tasks: the
``app.integrations.telegram`` layer is mocked at the function boundary
(those flow-level tests live elsewhere).

Each test exercises a specific behavior — branching on credential presence,
error/lock handling, DB writes, retry behavior, and chain composition.

Bug pins (xfail strict=True) flag two real bugs the prior run found in
production code; they are reproduced here so a fix flips them green.

Key technical notes
-------------------
* The autouse ``setup_database`` fixture from conftest.py is overridden with a
  no-op. Every DB session is mocked, so spinning up a real engine per test
  would only invite cross-loop asyncpg flakiness.
* Bound tasks (``@shared_task(bind=True)``) are invoked via ``.apply()`` so
  Celery runs them synchronously.
* ``fakeredis`` provides a Redis substitute (with Lua scripting) for the lock
  + progress-tracking code.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure settings are available before importing app modules.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("ENCRYPTION_KEY", "HiuobeEdnSk93dMtnycRm8Kob9D3-7-vCw3_L0YG9Ek=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://localhost:5432/pingcrm_test")

import fakeredis
import pytest
from telethon.errors import FloodWaitError


# ---------------------------------------------------------------------------
# Override the autouse setup_database fixture from conftest.py
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def setup_database():
    """No-op override. These tests fully mock the DB layer."""
    yield None


# ---------------------------------------------------------------------------
# Shared fake-session helper
# ---------------------------------------------------------------------------


class _FakeAsyncSession:
    """Minimal async session that records execute() / commit() / add() calls."""

    def __init__(self, scalar_results: list | None = None):
        self._scalar_results = list(scalar_results or [])
        self._scalars_all: list = []
        self.executed_statements: list = []
        self.added: list = []
        self.commits = 0
        self.flushes = 0

    async def execute(self, stmt, *args, **kwargs):
        self.executed_statements.append(stmt)
        result = MagicMock()
        if self._scalar_results:
            result.scalar_one_or_none = MagicMock(return_value=self._scalar_results.pop(0))
        else:
            result.scalar_one_or_none = MagicMock(return_value=None)
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=self._scalars_all)
        result.scalars = MagicMock(return_value=scalars)
        result.all = MagicMock(return_value=[(s,) for s in self._scalars_all])
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushes += 1

    async def rollback(self):
        pass


def _patch_session(target_module: str, session: _FakeAsyncSession):
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None
    return patch(f"{target_module}.task_session", return_value=cm)


def _patch_common_task_session(session: _FakeAsyncSession):
    """Patch task_session as imported into the common module (used by
    dismiss_suggestions_for_contacts)."""
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None
    return patch("app.services.task_jobs.common.task_session", return_value=cm)


def _make_user(**overrides):
    user = MagicMock()
    user.id = overrides.get("id", uuid.uuid4())
    user.telegram_last_synced_at = overrides.get("telegram_last_synced_at", None)
    return user


@pytest.fixture()
def fake_redis():
    """Provide a fakeredis instance, autouse-patched to be returned by redis.from_url."""
    fr = fakeredis.FakeRedis()
    with patch("redis.from_url", return_value=fr):
        yield fr


@pytest.fixture()
def fake_async_redis():
    """Patch every cached ``get_redis`` reference so each test gets its own fake.

    NOTE: ``app.services.sync_progress`` does ``from app.core.redis import get_redis``
    at module load. Once sync_progress is imported by any test, its local
    ``get_redis`` binding is fixed — patching ``app.core.redis.get_redis`` no
    longer reaches sync_progress on subsequent tests. We patch every consumer
    explicitly so each test has an isolated fakeredis instance.
    """
    fr = fakeredis.FakeAsyncRedis()
    with (
        patch("app.core.redis.get_redis", return_value=fr),
        patch("app.services.sync_progress.get_redis", return_value=fr),
    ):
        yield fr


# ---------------------------------------------------------------------------
# sync_telegram_chats_for_user
# ---------------------------------------------------------------------------


def test_sync_telegram_chats_invalid_user_id():
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    result = sync_telegram_chats_for_user.apply(args=["not-a-uuid"]).get()
    assert result == {"status": "invalid_user_id"}


def test_sync_telegram_chats_user_not_found(fake_async_redis):
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    session = _FakeAsyncSession(scalar_results=[None])

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats", new=AsyncMock(return_value={})),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
    ):
        result = sync_telegram_chats_for_user.apply(args=[str(uuid.uuid4())]).get()

    assert result == {"status": "user_not_found"}
    assert session.commits == 0


def test_sync_telegram_chats_happy_path_marks_synced_and_increments_progress(fake_async_redis):
    """End-to-end happy path: integration returns counts, sync event completes,
    user's telegram_last_synced_at is bumped, progress fields are incremented."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    chat_result = {
        "new_interactions": 7,
        "new_contacts": 2,
        "affected_contact_ids": [],
        "affected_contact_max_occurred_at": {},
    }

    record_complete_mock = AsyncMock(return_value=None)
    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value=chat_result)),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=record_complete_mock),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        result = sync_telegram_chats_for_user.apply(args=[str(user.id)]).get()

    assert result == {"status": "ok", "new_interactions": 7, "new_contacts": 2}
    # Sync event was marked complete with the integration totals.
    record_complete_mock.assert_awaited_once()
    kwargs = record_complete_mock.await_args.kwargs
    assert kwargs["records_created"] == 9  # 7 + 2
    # User's last-synced timestamp was set.
    assert isinstance(user.telegram_last_synced_at, datetime)
    assert session.commits == 1
    # Redis progress hash has the cumulative counters.
    progress = await_get_progress(fake_async_redis, str(user.id))
    assert int(progress.get(b"batches_completed", b"0")) == 1
    assert int(progress.get(b"messages_synced", b"0")) == 7
    assert int(progress.get(b"contacts_found", b"0")) == 2


def await_get_progress(fr, user_id: str) -> dict:
    """Synchronous helper to read the progress hash from a FakeAsyncRedis instance."""
    # FakeAsyncRedis stores keys in a synchronously-readable dict via .connection_pool.
    # The simpler path: use the underlying sync FakeRedis via fr.connection_pool.connection_class
    # but the public API exposes hgetall as async.  Run it through asyncio.
    import asyncio
    return asyncio.new_event_loop().run_until_complete(fr.hgetall(f"tg_sync_progress:{user_id}"))


def test_sync_telegram_chats_score_recalc_failures_are_logged_but_dont_block(fake_async_redis, caplog):
    """A calculate_score exception per contact does not abort the sync."""
    import logging
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    affected_ids = [str(uuid.uuid4()) for _ in range(3)]
    chat_result = {
        "new_interactions": 0,
        "new_contacts": 0,
        "affected_contact_ids": affected_ids,
        "affected_contact_max_occurred_at": {},
    }

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value=chat_result)),
        patch("app.services.scoring.calculate_score",
              new=AsyncMock(side_effect=RuntimeError("score boom"))),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger="app.services.task_jobs.common"),
    ):
        result = sync_telegram_chats_for_user.apply(args=[str(user.id)]).get()

    assert result["status"] == "ok"
    # All three failures logged
    score_warnings = [r for r in caplog.records if "score recalc failed" in r.message]
    assert len(score_warnings) == 3


def test_sync_telegram_chats_sync_integration_failure_records_failure_and_retries(fake_async_redis):
    """When sync_telegram_chats raises, record_sync_failure is called and the task retries."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    n_attempts = sync_telegram_chats_for_user.max_retries + 1
    session = _FakeAsyncSession(scalar_results=[user] * (n_attempts + 1))

    record_failure_mock = AsyncMock(return_value=None)
    chat_mock = AsyncMock(side_effect=RuntimeError("telethon blew up"))

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats", new=chat_mock),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=record_failure_mock),
    ):
        result = sync_telegram_chats_for_user.apply(args=[str(user.id)])

    assert result.failed()
    assert chat_mock.await_count == n_attempts
    # record_sync_failure invoked at every attempt
    assert record_failure_mock.await_count == n_attempts


def test_sync_telegram_chats_flood_wait_releases_lock_and_returns_partial(fake_redis, fake_async_redis):
    """FloodWaitError releases the lock (if token matches) and returns partial_flood_wait
    instead of retrying — preserves the downstream chain."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    user_id = str(user.id)
    lock_token = str(uuid.uuid4())

    # Pre-acquire the lock with our token
    fake_redis.set(f"tg_sync_lock:{user_id}", lock_token, ex=3600)

    n_attempts = sync_telegram_chats_for_user.max_retries + 1
    session = _FakeAsyncSession(scalar_results=[user] * (n_attempts + 1))

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(side_effect=FloodWaitError(request=None, capture=45))),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        result = sync_telegram_chats_for_user.apply(args=[user_id, 100, lock_token]).get()

    assert result == {"status": "partial_flood_wait", "new_interactions": 0, "new_contacts": 0}
    # Lock was released because token matched
    assert fake_redis.get(f"tg_sync_lock:{user_id}") is None


def test_sync_telegram_chats_flood_wait_with_stale_token_doesnt_release_other_lock(fake_redis, fake_async_redis):
    """If a stale task hits FloodWait but holds the wrong token, it must not delete a newer task's lock."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    user_id = str(user.id)
    other_token = "newer-token"
    stale_token = "stale-token"

    fake_redis.set(f"tg_sync_lock:{user_id}", other_token, ex=3600)

    session = _FakeAsyncSession(scalar_results=[user])

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(side_effect=FloodWaitError(request=None, capture=10))),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        result = sync_telegram_chats_for_user.apply(args=[user_id, 100, stale_token]).get()

    assert result["status"] == "partial_flood_wait"
    # Lock for the newer task remains intact
    assert fake_redis.get(f"tg_sync_lock:{user_id}") == b"newer-token"


def test_sync_telegram_chats_auto_merge_runs_when_new_contacts(fake_async_redis):
    """find_deterministic_matches is called when new contacts were created."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    chat_result = {
        "new_interactions": 0,
        "new_contacts": 3,
        "affected_contact_ids": [],
        "affected_contact_max_occurred_at": {},
    }

    find_matches_mock = AsyncMock(return_value=[MagicMock(), MagicMock()])

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value=chat_result)),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.identity_resolution.find_deterministic_matches",
              new=find_matches_mock),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        sync_telegram_chats_for_user.apply(args=[str(user.id)]).get()

    find_matches_mock.assert_awaited_once()


def test_sync_telegram_chats_auto_merge_failure_doesnt_block_sync(fake_async_redis, caplog):
    """If find_deterministic_matches raises, the sync still completes successfully."""
    import logging
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    chat_result = {
        "new_interactions": 1,
        "new_contacts": 2,
        "affected_contact_ids": [],
        "affected_contact_max_occurred_at": {},
    }

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value=chat_result)),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.identity_resolution.find_deterministic_matches",
              new=AsyncMock(side_effect=RuntimeError("merge boom"))),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger="app.services.task_jobs.common"),
    ):
        result = sync_telegram_chats_for_user.apply(args=[str(user.id)]).get()

    assert result["status"] == "ok"
    assert any("auto-merge failed" in r.message for r in caplog.records)


def test_sync_telegram_chats_auto_merge_skipped_when_no_new_contacts(fake_async_redis):
    """find_deterministic_matches is NOT called when no new contacts were created."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    chat_result = {
        "new_interactions": 5,
        "new_contacts": 0,
        "affected_contact_ids": [],
        "affected_contact_max_occurred_at": {},
    }

    find_matches_mock = AsyncMock(return_value=[])

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value=chat_result)),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.identity_resolution.find_deterministic_matches",
              new=find_matches_mock),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        sync_telegram_chats_for_user.apply(args=[str(user.id)]).get()

    find_matches_mock.assert_not_awaited()


def test_sync_telegram_chats_non_dict_result_falls_back_to_scalar_count(fake_async_redis):
    """If the integration returns a bare int (legacy shape), it's treated as new_interactions."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value=42)),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        result = sync_telegram_chats_for_user.apply(args=[str(user.id)]).get()

    assert result == {"status": "ok", "new_interactions": 42, "new_contacts": 0}


# Regression test for prior bug: a local `from datetime import UTC, datetime` inside
# _sync once shadowed the module-level `datetime`, making `datetime.fromisoformat(ts)`
# raise UnboundLocalError whenever the dismiss path actually ran. UTC is now imported
# at module level and the local re-import was removed.
def test_sync_telegram_chats_dismisses_suggestions_for_affected_contacts(fake_async_redis):
    """When the integration reports affected_contact_max_occurred_at, suggestions
    for those contacts should be dismissed up to that timestamp."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    contact_id = str(uuid.uuid4())
    session = _FakeAsyncSession(scalar_results=[user])

    chat_result = {
        "new_interactions": 1,
        "new_contacts": 0,
        "affected_contact_ids": [contact_id],
        "affected_contact_max_occurred_at": {contact_id: "2026-05-01T12:00:00+00:00"},
    }

    dismiss_mock = AsyncMock(return_value=1)
    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value=chat_result)),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.task_jobs.telegram.dismiss_suggestions_for_contacts",
              new=dismiss_mock),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        result = sync_telegram_chats_for_user.apply(args=[str(user.id)]).get()

    # If the bug is fixed: result is ok and dismiss_suggestions was called.
    assert result["status"] == "ok"
    dismiss_mock.assert_awaited_once()


def test_sync_telegram_chats_uses_scheduled_type_when_no_lock_token(fake_async_redis):
    """When invoked without a lock_token, the sync_event sync_type is 'scheduled' (cron)."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    record_start_mock = AsyncMock(return_value=MagicMock())
    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value={"new_interactions": 0, "new_contacts": 0,
                                          "affected_contact_ids": [],
                                          "affected_contact_max_occurred_at": {}})),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.sync_history.record_sync_start", new=record_start_mock),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        sync_telegram_chats_for_user.apply(args=[str(user.id)]).get()

    args = record_start_mock.await_args.args
    assert args[1] == "telegram"
    assert args[2] == "scheduled"


def test_sync_telegram_chats_uses_manual_type_when_lock_token_present(fake_async_redis):
    """When invoked with a lock_token (user-initiated sync), the sync_event sync_type is 'manual'."""
    from app.services.task_jobs.telegram import sync_telegram_chats_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    record_start_mock = AsyncMock(return_value=MagicMock())
    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats",
              new=AsyncMock(return_value={"new_interactions": 0, "new_contacts": 0,
                                          "affected_contact_ids": [],
                                          "affected_contact_max_occurred_at": {}})),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.sync_history.record_sync_start", new=record_start_mock),
        patch("app.services.sync_history.record_sync_complete", new=AsyncMock()),
        patch("app.services.sync_history.record_sync_failure", new=AsyncMock()),
    ):
        sync_telegram_chats_for_user.apply(args=[str(user.id), 100, "some-token"]).get()

    assert record_start_mock.await_args.args[2] == "manual"


# ---------------------------------------------------------------------------
# sync_telegram_chats_batch_task
# ---------------------------------------------------------------------------


def test_sync_telegram_chats_batch_invalid_user_id():
    from app.services.task_jobs.telegram import sync_telegram_chats_batch_task

    result = sync_telegram_chats_batch_task.apply(args=["nope", [1, 2]]).get()
    assert result == {"status": "invalid_user_id"}


def test_sync_telegram_chats_batch_user_not_found(fake_async_redis):
    from app.services.task_jobs.telegram import sync_telegram_chats_batch_task

    session = _FakeAsyncSession(scalar_results=[None])

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats_batch",
              new=AsyncMock(return_value={})),
    ):
        result = sync_telegram_chats_batch_task.apply(
            args=[str(uuid.uuid4()), [1, 2, 3]]
        ).get()

    assert result == {"status": "user_not_found"}


def test_sync_telegram_chats_batch_happy_path_increments_progress(fake_async_redis):
    from app.services.task_jobs.telegram import sync_telegram_chats_batch_task

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])
    entity_ids = [101, 102, 103]

    batch_result = {
        "new_interactions": 4,
        "new_contacts": 1,
        "affected_contact_ids": [],
        "affected_contact_max_occurred_at": {},
    }

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats_batch",
              new=AsyncMock(return_value=batch_result)),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
    ):
        result = sync_telegram_chats_batch_task.apply(
            args=[str(user.id), entity_ids]
        ).get()

    assert result == {"status": "ok", "new_interactions": 4, "new_contacts": 1}
    progress = await_get_progress(fake_async_redis, str(user.id))
    assert int(progress.get(b"dialogs_processed", b"0")) == len(entity_ids)
    assert int(progress.get(b"messages_synced", b"0")) == 4
    assert int(progress.get(b"contacts_found", b"0")) == 1
    assert session.commits == 1


def test_sync_telegram_chats_batch_dismisses_and_scores_for_affected_contacts(fake_async_redis):
    """Batch task: per-contact calculate_score is called for affected_contact_ids,
    and dismiss_suggestions_for_contacts is called when occurred timestamps are present."""
    from app.services.task_jobs.telegram import sync_telegram_chats_batch_task

    user = _make_user()
    affected_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    session = _FakeAsyncSession(scalar_results=[user])

    batch_result = {
        "new_interactions": 1,
        "new_contacts": 0,
        "affected_contact_ids": affected_ids,
        "affected_contact_max_occurred_at": {
            affected_ids[0]: "2026-05-01T12:00:00+00:00",
        },
    }

    score_mock = AsyncMock(side_effect=[RuntimeError("bad"), 0])  # first fails, second succeeds
    dismiss_mock = AsyncMock(return_value=1)

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats_batch",
              new=AsyncMock(return_value=batch_result)),
        patch("app.services.scoring.calculate_score", new=score_mock),
        patch("app.services.task_jobs.telegram.dismiss_suggestions_for_contacts",
              new=dismiss_mock),
    ):
        result = sync_telegram_chats_batch_task.apply(
            args=[str(user.id), [1, 2]]
        ).get()

    assert result["status"] == "ok"
    # calculate_score called for both contacts even though first raised
    assert score_mock.await_count == 2
    dismiss_mock.assert_awaited_once()


def test_sync_telegram_chats_batch_flood_wait_releases_lock(fake_redis, fake_async_redis):
    """Batch task on FloodWait: releases lock and returns partial result."""
    from app.services.task_jobs.telegram import sync_telegram_chats_batch_task

    user = _make_user()
    user_id = str(user.id)
    lock_token = "batch-token"
    fake_redis.set(f"tg_sync_lock:{user_id}", lock_token, ex=3600)

    n_attempts = sync_telegram_chats_batch_task.max_retries + 1
    session = _FakeAsyncSession(scalar_results=[user] * (n_attempts + 1))

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats_batch",
              new=AsyncMock(side_effect=FloodWaitError(request=None, capture=30))),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
    ):
        result = sync_telegram_chats_batch_task.apply(
            args=[user_id, [1, 2], lock_token]
        ).get()

    assert result == {"status": "partial_flood_wait", "new_interactions": 0, "new_contacts": 0}
    assert fake_redis.get(f"tg_sync_lock:{user_id}") is None


def test_sync_telegram_chats_batch_generic_error_retries_then_notifies(fake_redis, fake_async_redis):
    """On the final retry of a non-FloodWait failure, notify_sync_failure is dispatched."""
    from app.services.task_jobs.telegram import sync_telegram_chats_batch_task

    user = _make_user()
    user_id = str(user.id)
    n_attempts = sync_telegram_chats_batch_task.max_retries + 1
    session = _FakeAsyncSession(scalar_results=[user] * (n_attempts + 1))

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_chats_batch",
              new=AsyncMock(side_effect=RuntimeError("kaboom"))),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)),
        patch("app.services.task_jobs.telegram.notify_sync_failure") as mock_notify,
    ):
        result = sync_telegram_chats_batch_task.apply(args=[user_id, [1, 2], "tok"])

    assert result.failed()
    mock_notify.delay.assert_called_once()
    # platform label is "telegram" for batch task
    notify_args = mock_notify.delay.call_args.args
    assert notify_args[1] == "telegram"


# ---------------------------------------------------------------------------
# sync_telegram_groups_for_user — covers Bug Pin #1 (ImportError)
# ---------------------------------------------------------------------------


# Regression test for prior bug: sync_telegram_group_members must remain importable
# from wherever app/services/task_jobs/telegram.py expects to find it. Commit 208d89b
# dropped a re-export from app.integrations.telegram and broke the daily group sync;
# the production import was moved to app.integrations.telegram_groups.
def test_sync_telegram_groups_import_is_resolvable():
    """Confirm the import path used by sync_telegram_groups_for_user resolves."""
    from app.integrations.telegram_groups import sync_telegram_group_members  # noqa: F401


def test_sync_telegram_groups_invalid_user_id(fake_async_redis):
    from app.services.task_jobs.telegram import sync_telegram_groups_for_user

    result = sync_telegram_groups_for_user.apply(args=["bad"]).get()
    assert result == {"status": "invalid_user_id"}


# ---------------------------------------------------------------------------
# sync_telegram_bios_for_user
# ---------------------------------------------------------------------------


def test_sync_telegram_bios_invalid_user_id(fake_async_redis):
    from app.services.task_jobs.telegram import sync_telegram_bios_for_user

    result = sync_telegram_bios_for_user.apply(args=["bad"]).get()
    assert result == {"status": "invalid_user_id"}


def test_sync_telegram_bios_user_not_found(fake_async_redis):
    from app.services.task_jobs.telegram import sync_telegram_bios_for_user

    session = _FakeAsyncSession(scalar_results=[None])

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_bios", new=AsyncMock(return_value=None)),
    ):
        result = sync_telegram_bios_for_user.apply(args=[str(uuid.uuid4())]).get()

    assert result == {"status": "user_not_found"}
    assert session.commits == 0


def test_sync_telegram_bios_happy_path_passes_flags_and_commits(fake_async_redis):
    """exclude_2nd_tier + stale_days args are forwarded to the integration."""
    from app.services.task_jobs.telegram import sync_telegram_bios_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    bios_mock = AsyncMock(return_value=None)
    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_bios", new=bios_mock),
    ):
        result = sync_telegram_bios_for_user.apply(
            args=[str(user.id), True, 14]
        ).get()

    assert result == {"status": "ok"}
    bios_mock.assert_awaited_once()
    kwargs = bios_mock.await_args.kwargs
    assert kwargs["exclude_2nd_tier"] is True
    assert kwargs["stale_days"] == 14
    assert session.commits == 1


def test_sync_telegram_bios_eager_retries_then_notify_on_final_failure(fake_async_redis):
    from app.services.task_jobs.telegram import sync_telegram_bios_for_user

    user = _make_user()
    n_attempts = sync_telegram_bios_for_user.max_retries + 1
    session = _FakeAsyncSession(scalar_results=[user] * (n_attempts + 1))

    with (
        _patch_session("app.services.task_jobs.telegram", session),
        patch("app.integrations.telegram.sync_telegram_bios",
              new=AsyncMock(side_effect=RuntimeError("flood detail"))),
        patch("app.services.task_jobs.telegram.notify_sync_failure") as mock_notify,
    ):
        result = sync_telegram_bios_for_user.apply(args=[str(user.id)])

    assert result.failed()
    mock_notify.delay.assert_called_once()
    assert mock_notify.delay.call_args.args[1] == "Telegram bios"


# ---------------------------------------------------------------------------
# sync_telegram_notify
# ---------------------------------------------------------------------------


def test_sync_telegram_notify_invalid_user_id():
    from app.services.task_jobs.telegram import sync_telegram_notify

    result = sync_telegram_notify.apply(args=["bad"]).get()
    assert result == {"status": "invalid_user_id"}


def test_sync_telegram_notify_writes_notification_and_marks_synced(fake_redis, fake_async_redis):
    """The notify task: builds a notification, marks user.telegram_last_synced_at, releases the lock."""
    from app.services.task_jobs.telegram import sync_telegram_notify

    user = _make_user()
    user_id = str(user.id)
    lock_token = "release-me"
    fake_redis.set(f"tg_sync_lock:{user_id}", lock_token, ex=3600)

    # Two sessions used: one for _notify (Interaction count), one for _mark_synced (User lookup)
    notify_session = _FakeAsyncSession()
    # The notify session's execute returns a count result; scalar_one returns 5
    async def _exec(stmt, *a, **kw):
        r = MagicMock()
        r.scalar_one = MagicMock(return_value=5)
        return r
    notify_session.execute = _exec
    mark_session = _FakeAsyncSession(scalar_results=[user])

    # Patch task_session to alternate between the two sessions
    sessions = [notify_session, mark_session]
    def _make_cm(*a, **kw):
        s = sessions.pop(0)
        cm = AsyncMock()
        cm.__aenter__.return_value = s
        cm.__aexit__.return_value = None
        return cm

    with patch("app.services.task_jobs.telegram.task_session", side_effect=_make_cm):
        result = sync_telegram_notify.apply(args=[user_id, lock_token]).get()

    assert result == {"status": "ok"}
    # Notification recorded in the first session
    assert any(getattr(o, "notification_type", None) == "sync" for o in notify_session.added)
    notif = next(o for o in notify_session.added if getattr(o, "notification_type", None) == "sync")
    assert notif.title == "Telegram sync completed"
    assert "5 messages" in notif.body
    # User marked as synced
    assert isinstance(user.telegram_last_synced_at, datetime)
    # Lock released
    assert fake_redis.get(f"tg_sync_lock:{user_id}") is None


def test_sync_telegram_notify_empty_activity_body(fake_redis, fake_async_redis):
    """Zero new interactions surfaces 'No new activity' body."""
    from app.services.task_jobs.telegram import sync_telegram_notify

    user = _make_user()
    user_id = str(user.id)

    notify_session = _FakeAsyncSession()
    async def _exec(stmt, *a, **kw):
        r = MagicMock()
        r.scalar_one = MagicMock(return_value=0)
        return r
    notify_session.execute = _exec
    mark_session = _FakeAsyncSession(scalar_results=[user])
    sessions = [notify_session, mark_session]

    def _make_cm(*a, **kw):
        s = sessions.pop(0)
        cm = AsyncMock()
        cm.__aenter__.return_value = s
        cm.__aexit__.return_value = None
        return cm

    with patch("app.services.task_jobs.telegram.task_session", side_effect=_make_cm):
        sync_telegram_notify.apply(args=[user_id, ""]).get()

    notif = next(o for o in notify_session.added if getattr(o, "notification_type", None) == "sync")
    assert notif.body == "No new activity"


# ---------------------------------------------------------------------------
# sync_telegram_for_user — orchestrator
# ---------------------------------------------------------------------------


def test_sync_telegram_for_user_skips_when_api_creds_missing(fake_redis, caplog):
    """If TELEGRAM_API_ID/HASH are not configured, the orchestrator is a no-op."""
    import logging
    from app.services.task_jobs import telegram as tg_mod

    user_id = str(uuid.uuid4())

    fake_settings = MagicMock()
    fake_settings.TELEGRAM_API_ID = None
    fake_settings.TELEGRAM_API_HASH = None
    fake_settings.REDIS_URL = "redis://localhost"

    with (
        patch("app.core.config.settings", fake_settings),
        caplog.at_level(logging.WARNING, logger="app.services.task_jobs.common"),
    ):
        result = tg_mod.sync_telegram_for_user(user_id)

    assert result is None
    assert any("TELEGRAM_API_ID/HASH not configured" in r.message for r in caplog.records)
    # No lock acquired in fake_redis
    assert fake_redis.get(f"tg_sync_lock:{user_id}") is None


def test_sync_telegram_for_user_skips_when_lock_already_held(fake_redis, caplog):
    """If the per-user lock key already exists, the orchestrator skips."""
    import logging
    from app.services.task_jobs import telegram as tg_mod

    user_id = str(uuid.uuid4())
    # Pre-acquire the lock
    fake_redis.set(f"tg_sync_lock:{user_id}", "other-task", ex=3600)

    fake_settings = MagicMock()
    fake_settings.TELEGRAM_API_ID = 12345
    fake_settings.TELEGRAM_API_HASH = "hash"
    fake_settings.REDIS_URL = "redis://localhost"

    with (
        patch("app.core.config.settings", fake_settings),
        caplog.at_level(logging.INFO, logger="app.services.task_jobs.common"),
    ):
        result = tg_mod.sync_telegram_for_user(user_id)

    assert result is None
    assert any("sync already in progress" in r.message for r in caplog.records)
    # Lock untouched
    assert fake_redis.get(f"tg_sync_lock:{user_id}") == b"other-task"


def test_sync_telegram_for_user_incremental_chain_when_user_previously_synced(
    fake_redis, fake_async_redis
):
    """When telegram_last_synced_at is non-null, an incremental 2-task chain is dispatched."""
    from app.services.task_jobs import telegram as tg_mod

    user = _make_user(telegram_last_synced_at=datetime(2026, 5, 1, tzinfo=UTC))
    user_id = str(user.id)

    fake_settings = MagicMock()
    fake_settings.TELEGRAM_API_ID = 12345
    fake_settings.TELEGRAM_API_HASH = "hash"
    fake_settings.REDIS_URL = "redis://localhost"

    session = _FakeAsyncSession(scalar_results=[user.telegram_last_synced_at])

    chain_mock = MagicMock()
    chain_mock.return_value.apply_async = MagicMock()

    with (
        patch("app.core.config.settings", fake_settings),
        patch("app.services.task_jobs.telegram.task_session",
              side_effect=lambda *a, **kw: _patch_session_value(session)),
        patch("celery.chain", chain_mock),
    ):
        tg_mod.sync_telegram_for_user(user_id)

    # chain was invoked with 2 signatures: chats + notify
    assert chain_mock.called
    sig_args = chain_mock.call_args.args
    assert len(sig_args) == 2
    chain_mock.return_value.apply_async.assert_called_once()
    # Lock was acquired
    assert fake_redis.get(f"tg_sync_lock:{user_id}") is not None


def _patch_session_value(session):
    """Tiny helper: return an async context manager wrapping ``session``."""
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None
    return cm


def test_sync_telegram_for_user_first_sync_chunks_dialogs_into_batches(
    fake_redis, fake_async_redis
):
    """First sync: collects all dialog IDs, chunks them into BATCH_SIZE-sized batches,
    and builds a chain ending with groups + bios + notify."""
    from app.services.task_jobs import telegram as tg_mod

    user_id = str(uuid.uuid4())
    fake_settings = MagicMock()
    fake_settings.TELEGRAM_API_ID = 12345
    fake_settings.TELEGRAM_API_HASH = "hash"
    fake_settings.REDIS_URL = "redis://localhost"

    # First _run inside the orchestrator queries User.telegram_last_synced_at — None means first sync.
    # Second _run calls collect_dialog_ids — return 120 dialogs to produce 3 batches @ 50 each.
    last_synced_session = _FakeAsyncSession(scalar_results=[None])
    collect_session = _FakeAsyncSession(scalar_results=[MagicMock()])

    dialogs = [{"entity_id": i} for i in range(120)]

    chain_mock = MagicMock()
    chain_mock.return_value.apply_async = MagicMock()

    sessions = [last_synced_session, collect_session]
    def _make_cm(*a, **kw):
        s = sessions.pop(0)
        return _patch_session_value(s)

    with (
        patch("app.core.config.settings", fake_settings),
        patch("app.services.task_jobs.telegram.task_session", side_effect=_make_cm),
        patch("app.integrations.telegram.collect_dialog_ids",
              new=AsyncMock(return_value=dialogs)),
        patch("celery.chain", chain_mock),
    ):
        tg_mod.sync_telegram_for_user(user_id)

    # 120 dialogs → ceil(120 / 50) = 3 batches; plus groups + bios + notify = 6 sigs
    assert chain_mock.called
    sig_args = chain_mock.call_args.args
    assert len(sig_args) == 3 + 3  # 3 batches + groups + bios + notify
    chain_mock.return_value.apply_async.assert_called_once()


def test_sync_telegram_for_user_first_sync_handles_missing_user_during_collect(
    fake_redis, fake_async_redis, caplog
):
    """If the User row vanishes between the first-sync check and dialog collection,
    _collect returns [] and the orchestrator releases the lock + bails."""
    import logging
    from app.services.task_jobs import telegram as tg_mod

    user_id = str(uuid.uuid4())
    fake_settings = MagicMock()
    fake_settings.TELEGRAM_API_ID = 12345
    fake_settings.TELEGRAM_API_HASH = "hash"
    fake_settings.REDIS_URL = "redis://localhost"

    # First lookup says "never synced" -> first sync path
    last_synced_session = _FakeAsyncSession(scalar_results=[None])
    # Second lookup returns no user -> _collect returns []
    collect_session = _FakeAsyncSession(scalar_results=[None])

    sessions = [last_synced_session, collect_session]
    def _make_cm(*a, **kw):
        s = sessions.pop(0)
        return _patch_session_value(s)

    with (
        patch("app.core.config.settings", fake_settings),
        patch("app.services.task_jobs.telegram.task_session", side_effect=_make_cm),
        patch("app.integrations.telegram.collect_dialog_ids",
              new=AsyncMock(return_value=[])),
        caplog.at_level(logging.INFO, logger="app.services.task_jobs.common"),
    ):
        tg_mod.sync_telegram_for_user(user_id)

    # Lock released — even though we never made it to collect_dialog_ids
    assert fake_redis.get(f"tg_sync_lock:{user_id}") is None


def test_sync_telegram_for_user_first_sync_releases_lock_when_no_dialogs(
    fake_redis, fake_async_redis, caplog
):
    """First sync with zero dialogs: release the lock immediately and return."""
    import logging
    from app.services.task_jobs import telegram as tg_mod

    user_id = str(uuid.uuid4())
    fake_settings = MagicMock()
    fake_settings.TELEGRAM_API_ID = 12345
    fake_settings.TELEGRAM_API_HASH = "hash"
    fake_settings.REDIS_URL = "redis://localhost"

    last_synced_session = _FakeAsyncSession(scalar_results=[None])
    collect_session = _FakeAsyncSession(scalar_results=[MagicMock()])

    sessions = [last_synced_session, collect_session]
    def _make_cm(*a, **kw):
        s = sessions.pop(0)
        return _patch_session_value(s)

    with (
        patch("app.core.config.settings", fake_settings),
        patch("app.services.task_jobs.telegram.task_session", side_effect=_make_cm),
        patch("app.integrations.telegram.collect_dialog_ids",
              new=AsyncMock(return_value=[])),
        caplog.at_level(logging.INFO, logger="app.services.task_jobs.common"),
    ):
        tg_mod.sync_telegram_for_user(user_id)

    assert any("no dialogs found" in r.message for r in caplog.records)
    # Lock released
    assert fake_redis.get(f"tg_sync_lock:{user_id}") is None


# ---------------------------------------------------------------------------
# _release_lock — additional edge cases beyond test_telegram_lock.py
# ---------------------------------------------------------------------------


def test_release_lock_falls_back_to_false_on_redis_failure():
    """If the Redis connection throws, _release_lock swallows it and returns False."""
    from app.services.task_jobs.telegram import _release_lock

    fake_redis_module = MagicMock()
    fake_redis_module.from_url.side_effect = ConnectionError("redis down")

    fake_settings = MagicMock()
    fake_settings.REDIS_URL = "redis://localhost"

    with (
        patch.dict("sys.modules", {"redis": fake_redis_module}),
        patch("app.core.config.settings", fake_settings),
    ):
        result = _release_lock("user-x", "tok")

    assert result is False
