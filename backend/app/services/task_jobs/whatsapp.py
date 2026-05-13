"""WhatsApp Celery tasks — backfill sync and session health checks."""
from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.database import task_session
from app.models.user import User
from app.models.notification import Notification
from app.services.task_jobs.common import _run, logger, notify_sync_failure


@shared_task(
    name="app.services.tasks.sync_whatsapp_backfill",
    bind=True, max_retries=2, soft_time_limit=600, time_limit=900,
)
def sync_whatsapp_backfill(self, user_id: str) -> dict:
    """Trigger a WhatsApp message backfill for a single user.

    Calls the whatsapp-sidecar backfill endpoint and records a sync event.

    Args:
        user_id: String representation of the user's UUID.

    Returns:
        A dict with sync status and records_created count.
    """
    async def _backfill(uid: uuid.UUID) -> dict:
        from app.integrations.whatsapp import trigger_backfill
        from app.services.sync_history import (
            record_sync_start,
            record_sync_complete,
            record_sync_failure,
        )

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("sync_whatsapp_backfill: user %s not found.", uid)
                return {"status": "user_not_found", "records_created": 0}

            if not user.whatsapp_connected:
                logger.info("sync_whatsapp_backfill: user %s has no WhatsApp session.", uid)
                return {"status": "not_connected", "records_created": 0}

            sync_event = await record_sync_start(uid, "whatsapp", "manual", db)

            try:
                result_data = await trigger_backfill(str(uid))
                total = result_data.get("messages_imported", result_data.get("total", 0))
                await record_sync_complete(
                    sync_event,
                    records_created=total,
                    details=result_data,
                    db=db,
                )
                await db.commit()
            except Exception as exc:
                logger.exception(
                    "sync_whatsapp_backfill failed",
                    extra={"provider": "whatsapp", "user_id": str(uid)},
                )
                await record_sync_failure(sync_event, str(exc), db=db)
                await db.commit()
                raise

        return {"status": "ok", "records_created": total}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("sync_whatsapp_backfill: invalid user_id %r", user_id)
        return {"status": "invalid_user_id", "records_created": 0}

    try:
        return _run(_backfill(uid))
    except Exception as exc:
        logger.exception("sync_whatsapp_backfill failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(user_id, "WhatsApp backfill", str(exc))
        raise self.retry(exc=exc, countdown=120) from exc


@shared_task(
    name="app.services.tasks.check_whatsapp_sessions",
    soft_time_limit=120, time_limit=180,
)
def check_whatsapp_sessions() -> dict:
    """Health-check all WhatsApp sessions and mark dead ones disconnected.

    Queries every user with whatsapp_connected=True, polls the sidecar for
    status, and clears the flag + creates a notification for any dead sessions.

    Returns:
        A dict with ``checked`` and ``dead_sessions`` counts.
    """
    async def _check() -> dict:
        from app.integrations.whatsapp import get_status

        checked = 0
        dead_sessions = 0

        async with task_session() as db:
            result = await db.execute(
                select(User).where(User.whatsapp_connected.is_(True))
            )
            users = result.scalars().all()

            for user in users:
                checked += 1
                try:
                    status = await get_status(str(user.id))
                except Exception:
                    logger.warning(
                        "check_whatsapp_sessions: sidecar unreachable for user %s",
                        user.id,
                        exc_info=True,
                    )
                    status = "error"

                if status != "connected":
                    dead_sessions += 1
                    user.whatsapp_connected = False
                    db.add(Notification(
                        user_id=user.id,
                        notification_type="sync",
                        title="WhatsApp session disconnected",
                        body="Your WhatsApp session expired. Reconnect in Settings to resume syncing.",
                        link="/settings",
                    ))
                    logger.info(
                        "check_whatsapp_sessions: marked user %s disconnected (status=%r)",
                        user.id,
                        status,
                    )

            await db.commit()

        return {"checked": checked, "dead_sessions": dead_sessions}

    return _run(_check())
