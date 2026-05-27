"""Unit tests for app.services.task_jobs.maintenance.

These tests exercise the lifted ``_refresh_org_stats`` / ``_backfill_org_logos``
coroutines against a real Postgres test database (via the conftest ``db``
fixture) and the Celery wrappers via ``.apply()`` so we never go through the
broker.

The materialized view ``organization_stats_mv`` is not created in the test
schema, so ``_refresh_org_stats`` is verified by mocking ``db.execute`` /
``db.commit`` directly. ``_backfill_org_logos`` mocks the underlying
``backfill_org_logos`` service to isolate the wrapper's commit + return-value
contract.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.task_jobs.maintenance import (
    _backfill_org_logos,
    _refresh_org_stats,
    backfill_org_logos_task,
    refresh_org_stats,
)


# ---------------------------------------------------------------------------
# _refresh_org_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_org_stats_issues_concurrent_refresh_and_commits():
    """The impl must issue exactly the CONCURRENTLY refresh statement and
    commit. Capturing the exact SQL guards against accidental conversion to a
    blocking (non-CONCURRENTLY) refresh, which would lock readers in prod."""
    fake_db = MagicMock()
    fake_db.execute = AsyncMock()
    fake_db.commit = AsyncMock()

    await _refresh_org_stats(fake_db)

    fake_db.execute.assert_awaited_once()
    stmt = fake_db.execute.await_args.args[0]
    # Compile to text to check the literal SQL
    sql_text = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "REFRESH MATERIALIZED VIEW CONCURRENTLY organization_stats_mv" in sql_text
    fake_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_org_stats_propagates_execute_failure():
    """If the underlying execute raises, the impl must not swallow it — the
    Celery wrapper's retry logic depends on the exception surfacing."""
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(side_effect=RuntimeError("mv missing"))
    fake_db.commit = AsyncMock()

    with pytest.raises(RuntimeError, match="mv missing"):
        await _refresh_org_stats(fake_db)

    fake_db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# _backfill_org_logos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_org_logos_returns_count_and_commits(db: AsyncSession):
    """Wrapper delegates to organization_service.backfill_org_logos, commits,
    and returns the underlying count verbatim."""
    with patch(
        "app.services.task_jobs.maintenance.backfill_org_logos",
        new=AsyncMock(return_value=7),
    ) as mock_backfill:
        # Spy the commit
        with patch.object(db, "commit", new=AsyncMock(wraps=db.commit)) as mock_commit:
            result = await _backfill_org_logos(db)

    assert result == 7
    mock_backfill.assert_awaited_once_with(db)
    mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_backfill_org_logos_zero_count_still_commits(db: AsyncSession):
    """Even when nothing was updated, the wrapper still commits — this matches
    the original closure's behavior and keeps the contract simple."""
    with patch(
        "app.services.task_jobs.maintenance.backfill_org_logos",
        new=AsyncMock(return_value=0),
    ):
        with patch.object(db, "commit", new=AsyncMock(wraps=db.commit)) as mock_commit:
            result = await _backfill_org_logos(db)

    assert result == 0
    mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_backfill_org_logos_propagates_service_failure(db: AsyncSession):
    with patch(
        "app.services.task_jobs.maintenance.backfill_org_logos",
        new=AsyncMock(side_effect=RuntimeError("logo fetch broke")),
    ):
        with patch.object(db, "commit", new=AsyncMock(wraps=db.commit)) as mock_commit:
            with pytest.raises(RuntimeError, match="logo fetch broke"):
                await _backfill_org_logos(db)

    mock_commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Celery wrappers
# ---------------------------------------------------------------------------


def _patched_task_session_cm() -> AsyncMock:
    """Build an async-context-manager mock for ``task_session()``."""
    cm = AsyncMock()
    cm.__aenter__.return_value = object()
    cm.__aexit__.return_value = None
    return cm


def test_refresh_org_stats_celery_wrapper_returns_status_ok():
    """The Celery wrapper builds a session, calls _refresh_org_stats, logs, and
    returns the ``{"status": "ok"}`` envelope."""
    with (
        patch(
            "app.services.task_jobs.maintenance._refresh_org_stats",
            new=AsyncMock(return_value=None),
        ) as mock_impl,
        patch(
            "app.services.task_jobs.maintenance.task_session",
        ) as mock_session,
    ):
        mock_session.return_value = _patched_task_session_cm()
        result = refresh_org_stats.apply().get()

    assert result == {"status": "ok"}
    mock_impl.assert_awaited_once()


def test_backfill_org_logos_task_wrapper_returns_updated_count():
    """The Celery wrapper surfaces the impl's int return value as ``updated``
    in the envelope."""
    with (
        patch(
            "app.services.task_jobs.maintenance._backfill_org_logos",
            new=AsyncMock(return_value=12),
        ) as mock_impl,
        patch(
            "app.services.task_jobs.maintenance.task_session",
        ) as mock_session,
    ):
        mock_session.return_value = _patched_task_session_cm()
        result = backfill_org_logos_task.apply().get()

    assert result == {"status": "ok", "updated": 12}
    mock_impl.assert_awaited_once()


def test_backfill_org_logos_task_wrapper_handles_zero_updates():
    with (
        patch(
            "app.services.task_jobs.maintenance._backfill_org_logos",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.services.task_jobs.maintenance.task_session",
        ) as mock_session,
    ):
        mock_session.return_value = _patched_task_session_cm()
        result = backfill_org_logos_task.apply().get()

    assert result == {"status": "ok", "updated": 0}
