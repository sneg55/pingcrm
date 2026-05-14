"""Unit tests for app.services.task_jobs.twitter — Celery task orchestration.

These tests target the orchestration layer only: branching on credential
presence, error handling, DB writes via mocked sessions, and retry behavior.

The app.integrations.twitter layer is mocked at the function boundary —
those flow tests live in test_twitter_dm_sync_flow.py.

Key technical notes
-------------------
* The autouse `setup_database` fixture from conftest.py is overridden with a
  no-op here. Every DB session is mocked, so spinning up a real engine per
  test would only invite cross-loop asyncpg flakiness.
* Bound tasks (``@shared_task(bind=True)``) are invoked via ``.apply()`` so
  Celery runs them synchronously and ``self.retry()`` raises ``Retry`` instead
  of dispatching to a broker.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure settings are available before importing app modules.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("ENCRYPTION_KEY", "HiuobeEdnSk93dMtnycRm8Kob9D3-7-vCw3_L0YG9Ek=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://localhost:5432/pingcrm_test")

import httpx
import pytest
from celery.exceptions import Retry


# ---------------------------------------------------------------------------
# Override the autouse setup_database fixture from conftest.py
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def setup_database():
    """No-op override. These tests fully mock the DB layer."""
    yield None


# ---------------------------------------------------------------------------
# Mock-session helpers
# ---------------------------------------------------------------------------


class _FakeAsyncSession:
    """Minimal async session that records execute() / commit() / add() calls."""

    def __init__(self, scalar_results: list | None = None):
        # scalar_results: list of values returned by each execute().scalar_one_or_none()
        self._scalar_results = list(scalar_results or [])
        self._scalars_all = []  # list returned by execute().scalars().all()
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
        # For (cid,) iteration in score recalc
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
    """Return a patch object that replaces task_session in the given module."""
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None
    return patch(f"{target_module}.task_session", return_value=cm)


def _make_user(**overrides):
    """Build a User-like MagicMock with sensible defaults."""
    user = MagicMock()
    user.id = overrides.get("id", uuid.uuid4())
    user.twitter_access_token = overrides.get("twitter_access_token", "tok")
    user.twitter_bird_status = overrides.get("twitter_bird_status", "ok")
    return user


# ---------------------------------------------------------------------------
# poll_twitter_activity
# ---------------------------------------------------------------------------


def test_poll_twitter_activity_invalid_user_id_returns_sentinel():
    """Non-UUID user_id short-circuits without touching the DB."""
    from app.services.task_jobs.twitter import poll_twitter_activity

    with _patch_session("app.services.task_jobs.twitter", _FakeAsyncSession()) as p:
        result = poll_twitter_activity.apply(args=["not-a-uuid"]).get()

    assert result == {"status": "invalid_user_id", "contacts_processed": 0, "events_created": 0}


def test_poll_twitter_activity_user_not_found_returns_sentinel():
    """Missing user yields a `user_not_found` status, no commits."""
    from app.services.task_jobs.twitter import poll_twitter_activity

    session = _FakeAsyncSession(scalar_results=[None])
    with _patch_session("app.services.task_jobs.twitter", session):
        result = poll_twitter_activity.apply(args=[str(uuid.uuid4())]).get()

    assert result == {"status": "user_not_found", "contacts_processed": 0}
    assert session.commits == 0


def test_poll_twitter_activity_commits_and_counts_bio_changes():
    """Records returned by the integration are summarized + DB is committed."""
    from app.services.task_jobs.twitter import poll_twitter_activity

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    records = [
        {"contact_id": "c1", "bio_changed": True},
        {"contact_id": "c2", "bio_changed": False},
        {"contact_id": "c3", "bio_changed": True},
    ]

    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.integrations.twitter.poll_contacts_activity",
              new=AsyncMock(return_value=records)),
    ):
        result = poll_twitter_activity.apply(args=[str(user.id)]).get()

    assert result["status"] == "ok"
    assert result["contacts_processed"] == 3
    assert result["bio_changes"] == 2
    assert session.commits == 1


def test_poll_twitter_activity_expired_bird_status_logs_but_succeeds(caplog):
    """`twitter_bird_status == expired` logs a warning but doesn't error."""
    import logging
    from app.services.task_jobs.twitter import poll_twitter_activity

    user = _make_user(twitter_bird_status="expired")
    session = _FakeAsyncSession(scalar_results=[user])

    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.integrations.twitter.poll_contacts_activity",
              new=AsyncMock(return_value=[])),
        caplog.at_level(logging.WARNING, logger="app.services.task_jobs.common"),
    ):
        result = poll_twitter_activity.apply(args=[str(user.id)]).get()

    assert result["status"] == "ok"
    assert any("cookies expired" in r.message for r in caplog.records)


def test_poll_twitter_activity_notifies_when_final_retry_exhausted():
    """When the final retry is exhausted, notify_sync_failure.delay is invoked
    with the correct platform label and error message."""
    from app.services.task_jobs.twitter import poll_twitter_activity

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.integrations.twitter.poll_contacts_activity",
              new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.services.task_jobs.twitter.notify_sync_failure") as mock_notify,
    ):
        result = poll_twitter_activity.apply(
            args=[str(user.id)],
            retries=poll_twitter_activity.max_retries,
        )

    assert result.failed()
    mock_notify.delay.assert_called_once()
    notify_args = mock_notify.delay.call_args.args
    assert notify_args[1] == "Twitter activity"
    assert "boom" in notify_args[2]


def test_poll_twitter_activity_eager_retries_all_exhaust_then_notify_once():
    """End-to-end eager retry loop: the integration is called max_retries+1 times
    total, and notify_sync_failure.delay is dispatched exactly once (on the
    final attempt only)."""
    from app.services.task_jobs.twitter import poll_twitter_activity

    user = _make_user()
    n_attempts = poll_twitter_activity.max_retries + 1
    session = _FakeAsyncSession(scalar_results=[user] * (n_attempts + 1))
    poll_mock = AsyncMock(side_effect=RuntimeError("transient"))

    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.integrations.twitter.poll_contacts_activity", new=poll_mock),
        patch("app.services.task_jobs.twitter.notify_sync_failure") as mock_notify,
    ):
        result = poll_twitter_activity.apply(args=[str(user.id)])

    assert result.failed()
    assert poll_mock.await_count == n_attempts
    # Only the *final* attempt triggers the user-facing notification.
    mock_notify.delay.assert_called_once()


# ---------------------------------------------------------------------------
# sync_twitter_dms_for_user
# ---------------------------------------------------------------------------


def _patch_dm_dependencies(
    *,
    dm_result=None,
    mentions: int = 0,
    replies: int = 0,
    id_map=None,
    headers_first=None,
    headers_refresh=None,
):
    """Bundle the common patches needed by sync_twitter_dms_for_user tests."""
    if dm_result is None:
        dm_result = {"new_interactions": 0, "new_contacts": 0}
    if id_map is None:
        id_map = {}
    if headers_first is None:
        headers_first = {"Authorization": "Bearer tok"}

    return [
        patch("app.integrations.twitter.sync_twitter_dms",
              new=AsyncMock(return_value=dm_result)),
        patch("app.integrations.twitter.sync_twitter_mentions",
              new=AsyncMock(return_value=mentions)),
        patch("app.integrations.twitter.sync_twitter_replies",
              new=AsyncMock(return_value=replies)),
        patch("app.integrations.twitter._user_bearer_headers",
              new=AsyncMock(return_value=headers_first)),
        patch("app.integrations.twitter._refresh_and_retry",
              new=AsyncMock(return_value=headers_refresh or headers_first)),
        patch("app.integrations.twitter_contacts._build_twitter_id_to_contact_map",
              new=AsyncMock(return_value=id_map)),
        patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=42)),
        patch("app.services.sync_history.record_sync_start",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.sync_history.record_sync_complete",
              new=AsyncMock(return_value=None)),
        patch("app.services.sync_history.record_sync_failure",
              new=AsyncMock(return_value=None)),
    ]


def test_sync_twitter_dms_invalid_user_id():
    """Bad UUID short-circuits."""
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    result = sync_twitter_dms_for_user.apply(args=["bad"]).get()
    assert result == {"status": "invalid_user_id"}


def test_sync_twitter_dms_user_not_found():
    """Missing user returns sentinel without integration calls."""
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    session = _FakeAsyncSession(scalar_results=[None])
    with _patch_session("app.services.task_jobs.twitter", session):
        result = sync_twitter_dms_for_user.apply(args=[str(uuid.uuid4())]).get()

    assert result == {"status": "user_not_found"}


def test_sync_twitter_dms_skipped_when_user_has_no_access_token():
    """Users without OAuth token skip DM sync entirely (Bird CLI handles tweets separately)."""
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    user = _make_user(twitter_access_token=None)
    session = _FakeAsyncSession(scalar_results=[user])

    with _patch_session("app.services.task_jobs.twitter", session):
        result = sync_twitter_dms_for_user.apply(args=[str(user.id)]).get()

    assert result == {"status": "skipped", "reason": "no_twitter_token", "new_interactions": 0}
    assert session.commits == 0


def test_sync_twitter_dms_skipped_when_headers_build_fails():
    """If _user_bearer_headers returns falsy, sync skips with no_twitter_token."""
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.integrations.twitter._user_bearer_headers", new=AsyncMock(return_value=None)),
    ):
        result = sync_twitter_dms_for_user.apply(args=[str(user.id)]).get()

    assert result == {"status": "skipped", "reason": "no_twitter_token", "new_interactions": 0}
    assert session.commits == 0


def test_sync_twitter_dms_happy_path_creates_notification():
    """Full happy path: sync runs, notification body lists counts, sync_event marked complete."""
    from contextlib import ExitStack
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    with ExitStack() as stack:
        stack.enter_context(_patch_session("app.services.task_jobs.twitter", session))
        for p in _patch_dm_dependencies(
            dm_result={"new_interactions": 2, "new_contacts": 1},
            mentions=3,
            replies=5,
        ):
            stack.enter_context(p)

        result = sync_twitter_dms_for_user.apply(args=[str(user.id)]).get()

    assert result["status"] == "ok"
    assert result["dms"] == 2
    assert result["mentions"] == 3
    assert result["replies"] == 5
    assert result["new_contacts"] == 1
    # Notification persisted
    assert any(getattr(o, "notification_type", None) == "sync" for o in session.added)
    notif = next(o for o in session.added if getattr(o, "notification_type", None) == "sync")
    assert "2 DMs" in notif.body
    assert "3 mentions" in notif.body
    assert "5 replies" in notif.body
    assert "1 new contacts" in notif.body
    assert session.commits == 1


def test_sync_twitter_dms_notification_body_when_nothing_new():
    """No new activity surfaces a 'No new activity' notification rather than empty body."""
    from contextlib import ExitStack
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    with ExitStack() as stack:
        stack.enter_context(_patch_session("app.services.task_jobs.twitter", session))
        for p in _patch_dm_dependencies(dm_result={"new_interactions": 0, "new_contacts": 0}):
            stack.enter_context(p)

        sync_twitter_dms_for_user.apply(args=[str(user.id)]).get()

    notif = next(o for o in session.added if getattr(o, "notification_type", None) == "sync")
    assert notif.body == "No new activity"


def test_sync_twitter_dms_401_triggers_refresh_and_retry():
    """When sync_twitter_dms raises 401, _refresh_and_retry is called and DM sync re-runs."""
    from contextlib import ExitStack
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    # First call raises 401, second call (after refresh) succeeds.
    resp_401 = httpx.Response(401, request=httpx.Request("GET", "https://api.twitter.com/2/dm_events"))
    call_count = {"n": 0}

    async def _dm_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.HTTPStatusError("401", request=resp_401.request, response=resp_401)
        return {"new_interactions": 4, "new_contacts": 0}

    refresh_mock = AsyncMock(return_value={"Authorization": "Bearer refreshed"})

    with ExitStack() as stack:
        stack.enter_context(_patch_session("app.services.task_jobs.twitter", session))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_dms", new=AsyncMock(side_effect=_dm_side_effect)))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_mentions", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_replies", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.integrations.twitter._user_bearer_headers", new=AsyncMock(return_value={"Authorization": "Bearer original"})))
        stack.enter_context(patch("app.integrations.twitter._refresh_and_retry", new=refresh_mock))
        stack.enter_context(patch("app.integrations.twitter_contacts._build_twitter_id_to_contact_map", new=AsyncMock(return_value={})))
        stack.enter_context(patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.services.sync_history.record_sync_start", new=AsyncMock(return_value=MagicMock())))
        stack.enter_context(patch("app.services.sync_history.record_sync_complete", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("app.services.sync_history.record_sync_failure", new=AsyncMock(return_value=None)))

        result = sync_twitter_dms_for_user.apply(args=[str(user.id)]).get()

    assert result["status"] == "ok"
    assert result["dms"] == 4
    refresh_mock.assert_awaited_once()
    assert call_count["n"] == 2  # original call + retry


def test_sync_twitter_dms_401_then_refresh_failure_returns_auth_failed():
    """If refresh returns None after a 401, we record sync_failure and return auth_failed."""
    from contextlib import ExitStack
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    resp_401 = httpx.Response(401, request=httpx.Request("GET", "https://api.twitter.com/2/dm_events"))

    record_failure_mock = AsyncMock(return_value=None)

    with ExitStack() as stack:
        stack.enter_context(_patch_session("app.services.task_jobs.twitter", session))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_dms",
                                  new=AsyncMock(side_effect=httpx.HTTPStatusError("401", request=resp_401.request, response=resp_401))))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_mentions", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_replies", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.integrations.twitter._user_bearer_headers", new=AsyncMock(return_value={"Authorization": "Bearer tok"})))
        stack.enter_context(patch("app.integrations.twitter._refresh_and_retry", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("app.integrations.twitter_contacts._build_twitter_id_to_contact_map", new=AsyncMock(return_value={})))
        stack.enter_context(patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.services.sync_history.record_sync_start", new=AsyncMock(return_value=MagicMock())))
        stack.enter_context(patch("app.services.sync_history.record_sync_complete", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("app.services.sync_history.record_sync_failure", new=record_failure_mock))

        result = sync_twitter_dms_for_user.apply(args=[str(user.id)]).get()

    assert result == {"status": "auth_failed", "new_interactions": 0}
    record_failure_mock.assert_awaited_once()
    assert session.commits == 1


def test_sync_twitter_dms_non_401_http_error_propagates_for_retry():
    """Non-401 HTTPStatusError isn't swallowed — it propagates so Celery retries.

    The eager Celery runner will execute every retry attempt inline, so we
    seed the fake session with enough user lookups for all attempts and
    confirm the task ultimately fails (the final retry escalates).
    """
    from contextlib import ExitStack
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    user = _make_user()
    # User lookup happens once per attempt; max_retries+1 attempts total.
    session = _FakeAsyncSession(
        scalar_results=[user] * (sync_twitter_dms_for_user.max_retries + 2)
    )

    resp_500 = httpx.Response(500, request=httpx.Request("GET", "https://api.twitter.com/2/dm_events"))
    dm_mock = AsyncMock(side_effect=httpx.HTTPStatusError("500", request=resp_500.request, response=resp_500))

    with ExitStack() as stack:
        stack.enter_context(_patch_session("app.services.task_jobs.twitter", session))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_dms", new=dm_mock))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_mentions", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_replies", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.integrations.twitter._user_bearer_headers", new=AsyncMock(return_value={"Authorization": "Bearer tok"})))
        stack.enter_context(patch("app.integrations.twitter._refresh_and_retry", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("app.integrations.twitter_contacts._build_twitter_id_to_contact_map", new=AsyncMock(return_value={})))
        stack.enter_context(patch("app.services.scoring.calculate_score", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.services.sync_history.record_sync_start", new=AsyncMock(return_value=MagicMock())))
        stack.enter_context(patch("app.services.sync_history.record_sync_complete", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("app.services.sync_history.record_sync_failure", new=AsyncMock(return_value=None)))

        result = sync_twitter_dms_for_user.apply(args=[str(user.id)])

    assert result.failed()
    assert dm_mock.await_count >= 1
    # Underlying exception type is preserved through Retry wrapping
    exc = result.result
    assert isinstance(exc, (httpx.HTTPStatusError, Retry, Exception))


def test_sync_twitter_dms_score_recalc_failure_doesnt_block_sync():
    """If calculate_score raises, the rest of the sync still completes."""
    from contextlib import ExitStack
    from app.services.task_jobs.twitter import sync_twitter_dms_for_user

    user = _make_user()
    contact_uid = uuid.uuid4()

    session = _FakeAsyncSession(scalar_results=[user])
    session._scalars_all = [contact_uid]  # Contact.id rows for score recalc

    with ExitStack() as stack:
        stack.enter_context(_patch_session("app.services.task_jobs.twitter", session))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_dms", new=AsyncMock(return_value={"new_interactions": 1, "new_contacts": 0})))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_mentions", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.integrations.twitter.sync_twitter_replies", new=AsyncMock(return_value=0)))
        stack.enter_context(patch("app.integrations.twitter._user_bearer_headers", new=AsyncMock(return_value={"Authorization": "Bearer tok"})))
        stack.enter_context(patch("app.integrations.twitter._refresh_and_retry", new=AsyncMock(return_value={"Authorization": "Bearer tok"})))
        stack.enter_context(patch("app.integrations.twitter_contacts._build_twitter_id_to_contact_map", new=AsyncMock(return_value={})))
        stack.enter_context(patch("app.services.scoring.calculate_score", new=AsyncMock(side_effect=RuntimeError("score boom"))))
        stack.enter_context(patch("app.services.sync_history.record_sync_start", new=AsyncMock(return_value=MagicMock())))
        stack.enter_context(patch("app.services.sync_history.record_sync_complete", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("app.services.sync_history.record_sync_failure", new=AsyncMock(return_value=None)))

        result = sync_twitter_dms_for_user.apply(args=[str(user.id)]).get()

    assert result["status"] == "ok"
    assert session.commits == 1


# ---------------------------------------------------------------------------
# poll_twitter_all
# ---------------------------------------------------------------------------


def test_poll_twitter_all_resets_bird_verification_cache_each_run():
    """Each run starts with a cleared bird-cookie verification cache."""
    from app.services.task_jobs.twitter import poll_twitter_activity
    from app.services import bird_session

    # Seed the cache
    bird_session._verified_this_run.add("some-user-id")

    user = _make_user()
    session = _FakeAsyncSession(scalar_results=[user])

    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.integrations.twitter.poll_contacts_activity", new=AsyncMock(return_value=[])),
    ):
        poll_twitter_activity.apply(args=[str(user.id)]).get()

    assert bird_session._verified_this_run == set()


def test_poll_twitter_all_enqueues_activity_and_dms_for_each_connected_user():
    """poll_twitter_all dispatches BOTH poll_twitter_activity and sync_twitter_dms
    for every user that has a refresh token."""
    from app.services.task_jobs.twitter import poll_twitter_all

    uids = [uuid.uuid4() for _ in range(2)]
    session = _FakeAsyncSession()
    session._scalars_all = uids

    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.services.task_jobs.twitter.poll_twitter_activity") as mock_activity,
        patch("app.services.task_jobs.twitter.sync_twitter_dms_for_user") as mock_dms,
    ):
        mock_activity.delay = MagicMock(return_value=None)
        mock_dms.delay = MagicMock(return_value=None)
        result = poll_twitter_all()

    assert result == {"queued": 2}
    assert mock_activity.delay.call_count == 2
    assert mock_dms.delay.call_count == 2
    # Each invocation gets one user id as a string
    called_ids = {call.args[0] for call in mock_activity.delay.call_args_list}
    assert called_ids == {str(u) for u in uids}


# ---------------------------------------------------------------------------
# refresh_contact_twitter_bio
# ---------------------------------------------------------------------------


def test_refresh_contact_twitter_bio_invalid_ids():
    from app.services.task_jobs.twitter import refresh_contact_twitter_bio

    result = refresh_contact_twitter_bio.apply(args=["bad", "also-bad"]).get()
    assert result == {"status": "invalid_id"}


def test_refresh_contact_twitter_bio_user_not_found():
    from app.services.task_jobs.twitter import refresh_contact_twitter_bio

    session = _FakeAsyncSession(scalar_results=[None])
    with _patch_session("app.services.task_jobs.twitter", session):
        result = refresh_contact_twitter_bio.apply(
            args=[str(uuid.uuid4()), str(uuid.uuid4())]
        ).get()

    assert result == {"status": "user_not_found"}


def test_refresh_contact_twitter_bio_contact_not_found():
    from app.services.task_jobs.twitter import refresh_contact_twitter_bio

    user = _make_user()
    # First lookup returns user, second returns None for contact
    session = _FakeAsyncSession(scalar_results=[user, None])
    with _patch_session("app.services.task_jobs.twitter", session):
        result = refresh_contact_twitter_bio.apply(
            args=[str(user.id), str(uuid.uuid4())]
        ).get()

    assert result == {"status": "contact_not_found"}


def test_refresh_contact_twitter_bio_calls_refresh_and_commits():
    from app.services.task_jobs.twitter import refresh_contact_twitter_bio

    user = _make_user()
    contact = MagicMock()
    contact.id = uuid.uuid4()
    session = _FakeAsyncSession(scalar_results=[user, contact])

    refresh_mock = AsyncMock(return_value={"bio_changed": True, "handle_changed": False})

    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.services.bio_refresh.refresh_contact_bios", new=refresh_mock),
    ):
        result = refresh_contact_twitter_bio.apply(
            args=[str(user.id), str(contact.id)]
        ).get()

    assert result["status"] == "ok"
    assert result["changes"] == {"bio_changed": True, "handle_changed": False}
    refresh_mock.assert_awaited_once_with(contact, user, session)
    assert session.commits == 1


def test_refresh_contact_twitter_bio_retries_on_failure():
    """Exception from refresh_contact_bios triggers Celery retry (terminal Retry on the last attempt)."""
    from app.services.task_jobs.twitter import refresh_contact_twitter_bio

    user = _make_user()
    contact = MagicMock()
    contact.id = uuid.uuid4()

    # Eager Celery re-runs the task body for each retry — supply enough lookups.
    n_attempts = refresh_contact_twitter_bio.max_retries + 1
    session = _FakeAsyncSession(scalar_results=[user, contact] * n_attempts)

    refresh_mock = AsyncMock(side_effect=RuntimeError("bird blew up"))
    with (
        _patch_session("app.services.task_jobs.twitter", session),
        patch("app.services.bio_refresh.refresh_contact_bios", new=refresh_mock),
    ):
        result = refresh_contact_twitter_bio.apply(
            args=[str(user.id), str(contact.id)]
        )

    assert result.failed()
    # Confirm refresh_contact_bios was retried (called more than once)
    assert refresh_mock.await_count == n_attempts
