"""Relationship scoring Celery tasks.

The Celery entrypoint (``update_relationship_scores``) is a thin wrapper around
the ``_update_all_relationship_scores`` coroutine so the sync logic is directly
unit-testable against a real ``AsyncSession`` without spinning up a Celery
broker or the ``task_session`` machinery.
"""
from __future__ import annotations

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import task_session
from app.models.user import User
from app.services.scoring import batch_update_scores
from app.services.task_jobs.common import _run, logger


async def _update_all_relationship_scores(db: AsyncSession) -> dict:
    """Recalculate relationship scores for every user's contacts.

    Per-user failures are caught and counted in ``errors``; the function never
    raises for a single user's batch failure. A single ``db.commit()`` flushes
    all updates at the end.

    Returns a dict with ``updated`` (total contact-rows updated across all
    users) and ``errors`` (count of users whose batch raised).
    """
    updated = 0
    errors = 0

    user_result = await db.execute(select(User.id))
    user_ids = user_result.scalars().all()

    for user_id in user_ids:
        try:
            count = await batch_update_scores(user_id, db)
            updated += count
        except Exception:
            logger.exception(
                "update_relationship_scores: batch failed for user %s.", user_id
            )
            errors += 1

    await db.commit()

    return {"updated": updated, "errors": errors}


@shared_task(name="app.services.tasks.update_relationship_scores")
def update_relationship_scores() -> dict:
    """
    Beat-scheduled task: recalculate relationship scores for all contacts.

    Uses batch_update_scores() which runs a single aggregation query per user
    instead of N queries per contact.

    Returns:
        A dict with ``updated`` count and ``errors`` count.
    """
    async def _runner() -> dict:
        async with task_session() as db:
            return await _update_all_relationship_scores(db)

    result = _run(_runner())
    logger.info(
        "update_relationship_scores: updated=%d errors=%d",
        result["updated"],
        result["errors"],
    )
    return result
