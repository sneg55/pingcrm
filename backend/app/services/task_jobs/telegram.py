"""Telegram sync Celery tasks."""
from __future__ import annotations

import uuid
from datetime import datetime

from celery import shared_task
from sqlalchemy import select

from app.core.database import task_session
from app.models.user import User
from app.services.task_jobs.common import (
    _run,
    dismiss_suggestions_for_contacts,
    logger,
    notify_sync_failure,
)

BATCH_SIZE = 50  # dialogs per batch for initial Telegram sync

# Lua compare-and-delete script: only deletes the key if its value matches ARGV[1].
# Returns 1 if deleted, 0 if the token didn't match (lock belongs to a different task).
_RELEASE_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def _release_lock(user_id: str, lock_token: str) -> bool:
    """Release the Telegram sync lock only if we still own it (token matches).

    Uses a Lua compare-and-delete script to prevent a stale task from
    deleting a lock acquired by a newer task.

    Returns True if the lock was released, False if the token didn't match.
    """
    if not lock_token:
        return False
    try:
        from app.core.config import settings
        import redis as _redis
        _r = _redis.from_url(settings.REDIS_URL)
        lock_key = f"tg_sync_lock:{user_id}"
        result = _r.eval(_RELEASE_LOCK_LUA, 1, lock_key, lock_token)
        return bool(result)
    except Exception:
        logger.warning("_release_lock: failed to release lock for %s", user_id, exc_info=True)
        return False


@shared_task(name="app.services.tasks.sync_telegram_chats_for_user", bind=True, max_retries=3, soft_time_limit=900, time_limit=1200)
def sync_telegram_chats_for_user(self, user_id: str, max_dialogs: int = 100, lock_token: str = "") -> dict:
    """Sync Telegram DM chats for a single user (incremental: most recent N dialogs)."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.telegram import sync_telegram_chats
        from app.services.scoring import calculate_score
        from app.services.sync_history import record_sync_start, record_sync_complete, record_sync_failure

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            sync_event = await record_sync_start(uid, "telegram", "manual" if lock_token else "scheduled", db)

            try:
                chat_result = await sync_telegram_chats(user, db, max_dialogs=max_dialogs)
            except Exception as exc:
                await record_sync_failure(sync_event, str(exc), db=db)
                await db.commit()
                raise

            chat_info = chat_result if isinstance(chat_result, dict) else {
                "new_interactions": chat_result, "new_contacts": 0,
                "affected_contact_ids": [], "affected_contact_max_occurred_at": {},
            }

            affected = [uuid.UUID(str(cid)) for cid in chat_info.get("affected_contact_ids", [])]
            for cid in affected:
                try:
                    await calculate_score(cid, db)
                except Exception:
                    logger.warning("telegram_chats: score recalc failed for contact %s", cid, exc_info=True)

            occurred_map = {
                uuid.UUID(cid): datetime.fromisoformat(ts)
                for cid, ts in chat_info.get("affected_contact_max_occurred_at", {}).items()
            }
            if occurred_map:
                await dismiss_suggestions_for_contacts(occurred_map)

            await record_sync_complete(
                sync_event,
                records_created=chat_info.get("new_interactions", 0) + chat_info.get("new_contacts", 0),
                details=chat_info,
                db=db,
            )

            # Auto-merge deterministic duplicates (same email/phone/telegram)
            new_contacts = chat_info.get("new_contacts", 0)
            if new_contacts > 0:
                try:
                    from app.services.identity_resolution import find_deterministic_matches
                    merged = await find_deterministic_matches(uid, db)
                    if merged:
                        logger.info("telegram sync: auto-merged %d duplicate(s) for user %s", len(merged), uid)
                except Exception:
                    logger.warning("telegram sync: auto-merge failed for user %s", uid, exc_info=True)

            # Mark sync timestamp
            from datetime import UTC, datetime
            user.telegram_last_synced_at = datetime.now(UTC)
            await db.commit()

            from app.services.sync_progress import increment_progress
            await increment_progress(user_id, "batches_completed")
            await increment_progress(user_id, "dialogs_processed", max_dialogs)
            await increment_progress(user_id, "messages_synced", chat_info.get("new_interactions", 0))
            await increment_progress(user_id, "contacts_found", chat_info.get("new_contacts", 0))

        return {
            "status": "ok",
            "new_interactions": chat_info.get("new_interactions", 0),
            "new_contacts": chat_info.get("new_contacts", 0),
        }

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        from telethon.errors import FloodWaitError
        if isinstance(exc, FloodWaitError):
            # FloodWait: release lock and return partial result so the chain (groups → bios → notify) continues
            logger.warning("sync_telegram_chats: FloodWait for %s (%ds) — releasing lock and returning partial result to preserve chain.", user_id, exc.seconds)
            _release_lock(user_id, lock_token)
            return {"status": "partial_flood_wait", "new_interactions": 0, "new_contacts": 0}
        logger.exception("sync_telegram_chats failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            _release_lock(user_id, lock_token)
            notify_sync_failure.delay(str(uid), "Telegram chats", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_telegram_chats_batch_task", bind=True, max_retries=2, soft_time_limit=300, time_limit=420)
def sync_telegram_chats_batch_task(self, user_id: str, entity_ids: list[int], lock_token: str = "") -> dict:
    """Sync a batch of Telegram dialogs by entity ID (for chunked initial sync)."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.telegram import sync_telegram_chats_batch
        from app.services.scoring import calculate_score

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            batch_result = await sync_telegram_chats_batch(user, entity_ids, db)

            affected = [uuid.UUID(str(cid)) for cid in batch_result.get("affected_contact_ids", [])]
            for cid in affected:
                try:
                    await calculate_score(cid, db)
                except Exception:
                    logger.warning("telegram_chats_batch: score recalc failed for %s", cid, exc_info=True)

            occurred_map = {
                uuid.UUID(cid): datetime.fromisoformat(ts)
                for cid, ts in batch_result.get("affected_contact_max_occurred_at", {}).items()
            }
            if occurred_map:
                await dismiss_suggestions_for_contacts(occurred_map)

            await db.commit()

            from app.services.sync_progress import increment_progress
            await increment_progress(user_id, "batches_completed")
            await increment_progress(user_id, "dialogs_processed", len(entity_ids))
            await increment_progress(user_id, "messages_synced", batch_result.get("new_interactions", 0))
            await increment_progress(user_id, "contacts_found", batch_result.get("new_contacts", 0))

        return {
            "status": "ok",
            "new_interactions": batch_result.get("new_interactions", 0),
            "new_contacts": batch_result.get("new_contacts", 0),
        }

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        from telethon.errors import FloodWaitError
        if isinstance(exc, FloodWaitError):
            # FloodWait: release lock and return partial result so the chain continues
            logger.warning("sync_telegram_chats_batch: FloodWait for %s (%ds) — releasing lock and returning partial result to preserve chain.", user_id, exc.seconds)
            _release_lock(user_id, lock_token)
            return {"status": "partial_flood_wait", "new_interactions": 0, "new_contacts": 0}
        logger.exception("sync_telegram_chats_batch failed for %s (batch of %d), retrying.", user_id, len(entity_ids))
        if self.request.retries >= self.max_retries:
            _release_lock(user_id, lock_token)
            notify_sync_failure.delay(user_id, "telegram", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_telegram_groups_for_user", bind=True, max_retries=3, soft_time_limit=600, time_limit=900)
def sync_telegram_groups_for_user(self, user_id: str) -> dict:
    """Sync Telegram group members for a single user."""
    from app.services.sync_progress import set_progress
    _run(set_progress(user_id, phase="groups"))

    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.telegram import sync_telegram_group_members
        from app.services.scoring import calculate_score

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            group_result = await sync_telegram_group_members(user, db)

            for cid in group_result.get("affected_contact_ids", []):
                try:
                    await calculate_score(cid, db)
                except Exception:
                    logger.warning("telegram_groups: score recalc failed for contact %s", cid, exc_info=True)

            await db.commit()

        return {
            "status": "ok",
            "new_contacts": group_result.get("new_contacts", 0),
            "groups_scanned": group_result.get("groups_scanned", 0),
        }

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_telegram_groups failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Telegram groups", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_telegram_bios_for_user", bind=True, max_retries=3, soft_time_limit=600, time_limit=900)
def sync_telegram_bios_for_user(self, user_id: str, exclude_2nd_tier: bool = False, stale_days: int = 7) -> dict:
    """Sync Telegram bios (about text, birthdays, Twitter handles) for a single user."""
    from app.services.sync_progress import set_progress
    _run(set_progress(user_id, phase="bios"))

    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.telegram import sync_telegram_bios

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            await sync_telegram_bios(user, db, exclude_2nd_tier=exclude_2nd_tier, stale_days=stale_days)
            await db.commit()

        return {"status": "ok"}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_telegram_bios failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Telegram bios", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.recheck_telegram_bios_all")
def recheck_telegram_bios_all() -> dict:
    """Periodic task (every 3 days): recheck Telegram bios for non-2nd-tier contacts
    whose telegram_bio_checked_at is older than 3 days or NULL."""
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


@shared_task(name="app.services.tasks.sync_telegram_notify", ignore_result=True)
def sync_telegram_notify(user_id: str, lock_token: str = "") -> dict:
    """Send a summary notification and release the sync lock.

    Since Celery chain with .si() does not forward results, this task
    queries the DB directly to build the notification body.
    """
    async def _notify(uid: uuid.UUID) -> None:
        from datetime import UTC, datetime, timedelta
        from sqlalchemy import func as sa_func
        from app.models.notification import Notification
        from app.models.interaction import Interaction

        async with task_session() as db:
            # Count interactions created in the last hour (this sync window)
            one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
            new_count_result = await db.execute(
                select(sa_func.count())
                .select_from(Interaction)
                .where(
                    Interaction.user_id == uid,
                    Interaction.platform == "telegram",
                    Interaction.created_at >= one_hour_ago,
                )
            )
            new_interactions = new_count_result.scalar_one() or 0

            parts = []
            if new_interactions:
                parts.append(f"{new_interactions} messages")

            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Telegram sync completed",
                body=", ".join(parts) if parts else "No new activity",
                link="/settings",
            ))
            await db.commit()

    async def _mark_synced(uid: uuid.UUID) -> None:
        from datetime import datetime, timezone
        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user:
                user.telegram_last_synced_at = datetime.now(timezone.utc)
                await db.commit()

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    _run(_notify(uid))
    _run(_mark_synced(uid))

    # Mark progress as done with a short TTL so the frontend can see "done" briefly
    from app.services.sync_progress import set_progress
    from app.core.redis import get_redis

    async def _mark_done() -> None:
        await set_progress(user_id, phase="done")
        r = get_redis()
        await r.expire(f"tg_sync_progress:{user_id}", 300)

    _run(_mark_done())

    # Release the sync lock so the next sync is not blocked
    _release_lock(user_id, lock_token)

    return {"status": "ok"}


def sync_telegram_for_user(user_id: str) -> None:
    """Orchestrate Telegram sync as sequential sub-tasks with a summary notification.

    First sync (telegram_last_synced_at is NULL): collect all dialogs, chunk into
    batches of BATCH_SIZE, dispatch as a chain of batch tasks + groups + bios + notify.

    Incremental sync: process most recent 100 dialogs + groups + bios + notify.
    """
    from app.core.config import settings
    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
        logger.warning("sync_telegram_for_user: skipping user %s — TELEGRAM_API_ID/HASH not configured.", user_id)
        return

    import redis as _redis
    _r = _redis.from_url(settings.REDIS_URL)
    lock_key = f"tg_sync_lock:{user_id}"
    lock_token = str(uuid.uuid4())
    if not _r.set(lock_key, lock_token, nx=True, ex=3600):  # 1 hour TTL
        logger.info("sync_telegram_for_user: skipping user %s — sync already in progress", user_id)
        return

    from celery import chain

    # Check if this is first sync
    async def _check_first_sync() -> bool:
        async with task_session() as db:
            result = await db.execute(select(User.telegram_last_synced_at).where(User.id == uuid.UUID(user_id)))
            last_synced = result.scalar_one_or_none()
            return last_synced is None

    is_first_sync = _run(_check_first_sync())

    if is_first_sync:
        # First sync: collect dialog IDs and chunk into batches
        from app.services.sync_progress import set_progress
        from datetime import UTC, datetime as _dt

        _run(set_progress(user_id,
            phase="collecting",
            total_dialogs=0,
            dialogs_processed=0,
            batches_total=0,
            batches_completed=0,
            contacts_found=0,
            messages_synced=0,
            started_at=_dt.now(UTC).isoformat(),
        ))

        async def _collect() -> list[int]:
            async with task_session() as db:
                result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
                user = result.scalar_one_or_none()
                if not user:
                    return []
                from app.integrations.telegram import collect_dialog_ids
                dialogs = await collect_dialog_ids(user)
                return [d["entity_id"] for d in dialogs]

        all_entity_ids = _run(_collect())
        if not all_entity_ids:
            logger.info("sync_telegram_for_user: no dialogs found for %s, skipping.", user_id)
            _release_lock(user_id, lock_token)  # Release lock on early return
            return

        # Chunk into batches
        batches = [all_entity_ids[i:i + BATCH_SIZE] for i in range(0, len(all_entity_ids), BATCH_SIZE)]
        logger.info(
            "sync_telegram_for_user: first sync for %s — %d dialogs in %d batches.",
            user_id, len(all_entity_ids), len(batches),
        )

        _run(set_progress(user_id,
            phase="chats",
            total_dialogs=len(all_entity_ids),
            dialogs_processed=0,
            batches_total=len(batches),
            batches_completed=0,
            contacts_found=0,
            messages_synced=0,
            started_at=_dt.now(UTC).isoformat(),
        ))

        # Build chain: batch1 → batch2 → ... → groups → bios → notify (releases lock)
        tasks = [sync_telegram_chats_batch_task.si(user_id, batch, lock_token) for batch in batches]
        tasks.extend([
            sync_telegram_groups_for_user.si(user_id),
            sync_telegram_bios_for_user.si(user_id),
            sync_telegram_notify.si(user_id, lock_token),
        ])
        chain(*tasks).apply_async()
    else:
        # Incremental sync: most recent 100 dialogs
        # Groups and bios are fetched on-demand (contact detail page visit / Refresh Details)
        # and via periodic recheck tasks — not in the daily chain.
        from app.services.sync_progress import set_progress
        from datetime import UTC, datetime as _dt
        _run(set_progress(user_id, phase="messages", total_dialogs=100, dialogs_processed=0, batches_total=1, batches_completed=0, contacts_found=0, messages_synced=0, started_at=_dt.now(UTC).isoformat()))
        chain(
            sync_telegram_chats_for_user.si(user_id, 100, lock_token),
            sync_telegram_notify.si(user_id, lock_token),
        ).apply_async()


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
            # lock_key may be bytes or str depending on decode_responses setting
            key_str = lock_key.decode() if isinstance(lock_key, bytes) else lock_key
            user_id = key_str.split(":", 1)[1]  # strip "tg_sync_lock:" prefix
            progress_key = f"tg_sync_progress:{user_id}"

            has_progress = _r.exists(progress_key)
            if has_progress:
                continue  # sync is active; leave the lock alone

            ttl = _r.ttl(lock_key)
            # TTL == -2 means the key disappeared between scan and ttl call — already gone
            if ttl == -2:
                continue
            # Only delete if the lock has been held for at least 15 minutes
            # (TTL < 2700 means more than 900 s have elapsed from the original 3600 s)
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


@shared_task(name="app.services.tasks.sync_telegram_all")
def sync_telegram_all() -> dict:
    """Beat-scheduled task: enqueue Telegram sync for every connected user."""
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
