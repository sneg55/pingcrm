"""Unit tests for app.services.task_jobs.version_check.

The Celery task is a thin wrapper around ``version_checker.is_disabled`` and
``version_checker.refresh_cache``. There's no closure to lift — instead we mock
the two dependencies at the ``task_jobs.version_check`` module level and drive
the task via ``.apply()`` so behavior is exercised without a broker or network.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

from app.services.task_jobs.version_check import check_for_updates


def test_returns_early_when_disabled():
    """If is_disabled() is truthy, refresh_cache must not be invoked."""
    with (
        patch(
            "app.services.task_jobs.version_check.is_disabled",
            return_value=True,
        ) as mock_disabled,
        patch(
            "app.services.task_jobs.version_check.refresh_cache",
            new=AsyncMock(),
        ) as mock_refresh,
    ):
        result = check_for_updates.apply().get()

    assert result is None
    mock_disabled.assert_called_once_with()
    mock_refresh.assert_not_awaited()


def test_invokes_refresh_cache_when_enabled():
    """Happy path: when enabled, refresh_cache is awaited exactly once via
    asyncio.run inside the task body."""
    with (
        patch(
            "app.services.task_jobs.version_check.is_disabled",
            return_value=False,
        ),
        patch(
            "app.services.task_jobs.version_check.refresh_cache",
            new=AsyncMock(return_value=None),
        ) as mock_refresh,
    ):
        result = check_for_updates.apply().get()

    assert result is None
    mock_refresh.assert_awaited_once()


def test_swallows_exceptions_and_logs(caplog):
    """If refresh_cache raises, the task must log via logger.exception and
    return None — never propagate to Celery (no retry configured)."""
    with (
        patch(
            "app.services.task_jobs.version_check.is_disabled",
            return_value=False,
        ),
        patch(
            "app.services.task_jobs.version_check.refresh_cache",
            new=AsyncMock(side_effect=RuntimeError("github timed out")),
        ),
        caplog.at_level(logging.ERROR, logger="app.services.task_jobs.version_check"),
    ):
        result = check_for_updates.apply().get()

    assert result is None
    # logger.exception emits at ERROR level and includes the message + extra
    matching = [
        r for r in caplog.records
        if "version check task failed" in r.getMessage()
    ]
    assert len(matching) == 1
    assert matching[0].levelno == logging.ERROR
    assert getattr(matching[0], "provider", None) == "github"


def test_celery_task_is_registered_with_expected_name():
    """The task is dispatched via Celery beat by name — pin the name so a
    rename in tasks.py registry doesn't silently break the periodic schedule."""
    assert check_for_updates.name == "app.services.tasks.check_for_updates"


def test_is_disabled_check_happens_before_refresh():
    """Order matters: is_disabled() must short-circuit before refresh_cache
    runs, otherwise disabling the check wouldn't actually prevent the call."""
    call_order: list[str] = []

    def fake_is_disabled():
        call_order.append("is_disabled")
        return True

    async def fake_refresh():
        call_order.append("refresh_cache")

    with (
        patch(
            "app.services.task_jobs.version_check.is_disabled",
            side_effect=fake_is_disabled,
        ),
        patch(
            "app.services.task_jobs.version_check.refresh_cache",
            new=fake_refresh,
        ),
    ):
        check_for_updates.apply().get()

    assert call_order == ["is_disabled"]
