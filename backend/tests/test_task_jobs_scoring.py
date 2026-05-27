"""Unit tests for app.services.task_jobs.scoring.

These tests exercise the lifted ``_update_all_relationship_scores`` coroutine
against a real Postgres test database (via the conftest ``db`` fixture). The
scoring boundary (``batch_update_scores``) is mocked at the
``task_jobs.scoring`` module level so we cover the orchestration logic —
per-user iteration, error counting, total accumulation, the trailing
``db.commit()`` — without exercising the real scoring SQL aggregate.

The Celery entrypoint wrapper is tested by invoking it via ``.apply()`` so the
``_run`` + ``task_session`` plumbing is covered as a unit.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.task_jobs.scoring import (
    _update_all_relationship_scores,
    update_relationship_scores,
)


# ---------------------------------------------------------------------------
# _update_all_relationship_scores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_zero_counts_when_no_users(db: AsyncSession):
    """No users in DB → no batch calls, no errors, no updates.

    Note: conftest's `db` fixture rolls back between tests, but doesn't
    pre-seed users. test_user only exists when injected explicitly.
    """
    with patch(
        "app.services.task_jobs.scoring.batch_update_scores",
        new=AsyncMock(return_value=0),
    ) as mock_batch:
        result = await _update_all_relationship_scores(db)

    assert result == {"updated": 0, "errors": 0}
    mock_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_invokes_batch_update_for_every_user_and_sums(
    db: AsyncSession, test_user: User, user_factory
):
    other = await user_factory()

    seen_ids: list = []

    async def fake_batch(user_id, session):  # noqa: ARG001
        seen_ids.append(user_id)
        # Return different counts to verify the sum
        return 5 if user_id == test_user.id else 3

    with patch(
        "app.services.task_jobs.scoring.batch_update_scores",
        new=AsyncMock(side_effect=fake_batch),
    ) as mock_batch:
        result = await _update_all_relationship_scores(db)

    assert result == {"updated": 8, "errors": 0}
    assert mock_batch.await_count == 2
    assert set(seen_ids) == {test_user.id, other.id}


@pytest.mark.asyncio
async def test_per_user_exception_is_counted_and_loop_continues(
    db: AsyncSession, test_user: User, user_factory
):
    """If one user's batch raises, the error is counted, the next user still
    processes, and the function returns normally (does not re-raise)."""
    other = await user_factory()

    async def fake_batch(user_id, session):  # noqa: ARG001
        if user_id == test_user.id:
            raise RuntimeError("scoring blew up")
        return 7

    with patch(
        "app.services.task_jobs.scoring.batch_update_scores",
        new=AsyncMock(side_effect=fake_batch),
    ):
        result = await _update_all_relationship_scores(db)

    assert result == {"updated": 7, "errors": 1}
    # The successful user's count survives despite the other failing
    assert other is not None  # keep ref live


@pytest.mark.asyncio
async def test_all_users_failing_returns_all_errors_no_updates(
    db: AsyncSession, test_user: User, user_factory
):
    await user_factory()

    with patch(
        "app.services.task_jobs.scoring.batch_update_scores",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await _update_all_relationship_scores(db)

    assert result == {"updated": 0, "errors": 2}


@pytest.mark.asyncio
async def test_single_user_zero_count_returns_zero_updates(
    db: AsyncSession, test_user: User
):
    with patch(
        "app.services.task_jobs.scoring.batch_update_scores",
        new=AsyncMock(return_value=0),
    ) as mock_batch:
        result = await _update_all_relationship_scores(db)

    assert result == {"updated": 0, "errors": 0}
    mock_batch.assert_awaited_once()
    # Confirm it was called with the user id + the session we passed in
    args, _ = mock_batch.call_args
    assert args[0] == test_user.id
    assert args[1] is db


# ---------------------------------------------------------------------------
# Celery wrapper — update_relationship_scores
# ---------------------------------------------------------------------------


def test_celery_wrapper_runs_runner_and_returns_impl_result():
    """Cover the wrapper's _runner + _run + task_session path with the impl
    fully mocked — we just want to confirm the wrapper returns whatever the
    coroutine returned."""
    fake_result = {"updated": 42, "errors": 1}
    with (
        patch(
            "app.services.task_jobs.scoring._update_all_relationship_scores",
            new=AsyncMock(return_value=fake_result),
        ) as mock_impl,
        patch("app.services.task_jobs.scoring.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = update_relationship_scores.apply().get()

    assert result == fake_result
    mock_impl.assert_awaited_once()


def test_celery_wrapper_propagates_zero_counts():
    """The wrapper logs counts then returns them — verify the no-op case
    survives the round-trip without crashing the logger format string."""
    with (
        patch(
            "app.services.task_jobs.scoring._update_all_relationship_scores",
            new=AsyncMock(return_value={"updated": 0, "errors": 0}),
        ),
        patch("app.services.task_jobs.scoring.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = update_relationship_scores.apply().get()

    assert result == {"updated": 0, "errors": 0}
