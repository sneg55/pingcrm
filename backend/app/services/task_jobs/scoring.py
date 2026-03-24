"""Relationship scoring Celery tasks."""
from __future__ import annotations

from celery import shared_task
from sqlalchemy import select

from app.core.database import task_session
from app.models.user import User
from app.services.task_jobs.common import _run, logger


@shared_task(name="app.services.tasks.update_relationship_scores")
def update_relationship_scores() -> dict:
    """
    Beat-scheduled task: recalculate relationship scores for all contacts.

    Uses batch_update_scores() which runs a single aggregation query per user
    instead of N queries per contact.

    Returns:
        A dict with ``updated`` count and ``errors`` count.
    """
    async def _update_all() -> dict:
        from app.services.scoring import batch_update_scores

        updated = 0
        errors = 0

        async with task_session() as db:
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

    result = _run(_update_all())
    logger.info(
        "update_relationship_scores: updated=%d errors=%d",
        result["updated"],
        result["errors"],
    )
    return result
