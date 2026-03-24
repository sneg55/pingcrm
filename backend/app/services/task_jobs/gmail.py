"""Gmail sync Celery tasks."""
from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.database import task_session
from app.models.contact import Contact
from app.models.user import User
from app.services.task_jobs.common import _run, logger, notify_sync_failure


@shared_task(name="app.services.tasks.sync_gmail_for_user", bind=True, max_retries=3, soft_time_limit=900, time_limit=1200)
def sync_gmail_for_user(self, user_id: str) -> dict:
    """
    Sync Gmail threads for a single user.

    Args:
        user_id: String representation of the user's UUID.

    Returns:
        A dict with ``new_interactions`` count and ``status``.
    """
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.gmail import sync_gmail_for_user as _gmail_sync
        from app.services.scoring import calculate_score
        from app.services.sync_history import record_sync_start, record_sync_complete, record_sync_failure

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("sync_gmail_for_user: user %s not found.", uid)
                return {"status": "user_not_found", "new_interactions": 0}

            sync_event = await record_sync_start(uid, "gmail", "scheduled", db)

            try:
                new_count = await _gmail_sync(user, db)
            except Exception as exc:
                await record_sync_failure(sync_event, str(exc), db=db)
                await db.commit()
                raise

            # Rescore contacts that have interactions
            if new_count > 0:
                contact_ids_result = await db.execute(
                    select(Contact.id).where(
                        Contact.user_id == uid,
                        Contact.last_interaction_at.isnot(None),
                    )
                )
                for (cid,) in contact_ids_result.all():
                    try:
                        await calculate_score(cid, db)
                    except Exception:
                        logger.warning("gmail: score recalc failed for contact %s", cid, exc_info=True)

            await record_sync_complete(sync_event, records_created=new_count, db=db)
            await db.commit()

        return {"status": "ok", "new_interactions": new_count}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("sync_gmail_for_user: invalid user_id %r", user_id)
        return {"status": "invalid_user_id", "new_interactions": 0}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_gmail_for_user failed for %s, retrying.", user_id)
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_gmail_all")
def sync_gmail_all() -> dict:
    """
    Beat-scheduled task: enqueue a ``sync_gmail_for_user`` task for every user
    that has a google_refresh_token set.

    Returns:
        A dict with ``queued`` count.
    """
    async def _get_user_ids() -> list[str]:
        async with task_session() as db:
            result = await db.execute(
                select(User.id).where(User.google_refresh_token.isnot(None))
            )
            return [str(row) for row in result.scalars().all()]

    user_ids = _run(_get_user_ids())
    for uid in user_ids:
        sync_gmail_for_user.delay(uid)

    logger.info("sync_gmail_all: queued %d user(s).", len(user_ids))
    return {"queued": len(user_ids)}
