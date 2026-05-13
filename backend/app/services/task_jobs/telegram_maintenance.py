"""Telegram maintenance Celery tasks: lock cleanup, periodic bio recheck, batch dispatch."""
from __future__ import annotations

from celery import shared_task
from sqlalchemy import select

from app.core.database import task_session
from app.models.user import User
from app.services.task_jobs.common import _run, logger


@shared_task(name="app.services.tasks.cleanup_stale_telegram_locks")
def cleanup_stale_telegram_locks() -> dict:
    """Hourly watchdog: delete Telegram sync locks that have no matching progress key.

    A lock is considered stale when:
      - No ``tg_sync_progress:{user_id}`` key exists (the sync chain never started
        or the progress key already expired), AND
      - The lock TTL is below 2700 seconds (i.e. the lock has been held for at least
        15 minutes of its 3600-second lifetime).

    This cleans up locks left behind by tasks that crashed before releasing them.
    """
    from app.core.config import settings
    import redis as _redis

    deleted = 0
    scanned = 0
    try:
        _r = _redis.from_url(settings.REDIS_URL)
        for lock_key in _r.scan_iter("tg_sync_lock:*"):
            scanned += 1
            key_str = lock_key.decode() if isinstance(lock_key, bytes) else lock_key
            user_id = key_str.split(":", 1)[1]
            progress_key = f"tg_sync_progress:{user_id}"

            has_progress = _r.exists(progress_key)
            if has_progress:
                continue

            ttl = _r.ttl(lock_key)
            if ttl == -2:
                continue
            if ttl < 2700:
                _r.delete(lock_key)
                deleted += 1
                logger.info(
                    "cleanup_stale_telegram_locks: deleted stale lock %s (TTL=%d, no progress key)",
                    key_str, ttl,
                )
    except Exception:
        logger.exception("cleanup_stale_telegram_locks: unexpected error during scan")
        return {"scanned": scanned, "deleted": deleted, "error": True}

    logger.info(
        "cleanup_stale_telegram_locks: scanned=%d deleted=%d",
        scanned, deleted,
    )
    return {"scanned": scanned, "deleted": deleted}


@shared_task(name="app.services.tasks.recheck_telegram_bios_all")
def recheck_telegram_bios_all() -> dict:
    """Periodic task (every 3 days): recheck Telegram bios for non-2nd-tier contacts
    whose telegram_bio_checked_at is older than 3 days or NULL."""
    from app.services.task_jobs.telegram import sync_telegram_bios_for_user

    async def _run_recheck() -> int:
        async with task_session() as db:
            result = await db.execute(
                select(User.id).where(User.telegram_session.isnot(None))
            )
            user_ids = [str(uid) for uid in result.scalars().all()]

        count = 0
        for uid in user_ids:
            sync_telegram_bios_for_user.delay(uid, exclude_2nd_tier=True, stale_days=3)
            count += 1
        return count

    queued = _run(_run_recheck())
    logger.info("recheck_telegram_bios_all: queued %d user(s).", queued)
    return {"queued": queued}


@shared_task(name="app.services.tasks.sync_telegram_all")
def sync_telegram_all() -> dict:
    """Beat-scheduled task: enqueue Telegram sync for every connected user."""
    from app.services.task_jobs.telegram import sync_telegram_for_user

    async def _get_user_ids() -> list[str]:
        async with task_session() as db:
            result = await db.execute(
                select(User.id).where(User.telegram_session.isnot(None))
            )
            return [str(row) for row in result.scalars().all()]

    user_ids = _run(_get_user_ids())
    for uid in user_ids:
        sync_telegram_for_user(uid)

    logger.info("sync_telegram_all: queued %d user(s).", len(user_ids))
    return {"queued": len(user_ids)}
