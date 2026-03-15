"""Celery tasks for Ping CRM background processing."""
from __future__ import annotations

import asyncio
import logging
import uuid

import httpx

from celery import shared_task
from sqlalchemy import select

from app.core.celery_app import celery_app  # noqa: F401 — registers the app
from app.core.database import task_session
from app.models.contact import Contact
from app.models.user import User

logger = logging.getLogger(__name__)


def _run(coro):
    """Run an async coroutine synchronously inside a Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def dismiss_suggestions_for_contacts(contact_ids: list[uuid.UUID]) -> int:
    """Dismiss pending follow-up suggestions for contacts that just received new interactions."""
    if not contact_ids:
        return 0
    from sqlalchemy import update
    from app.models.follow_up import FollowUpSuggestion

    async with task_session() as db:
        result = await db.execute(
            update(FollowUpSuggestion)
            .where(
                FollowUpSuggestion.contact_id.in_(contact_ids),
                FollowUpSuggestion.status == "pending",
            )
            .values(status="dismissed")
        )
        await db.commit()
        return result.rowcount  # type: ignore[return-value]


@shared_task(name="app.services.tasks.notify_sync_failure")
def notify_sync_failure(user_id: str, platform: str, error: str) -> None:
    """Create a notification when a background sync exhausts retries."""
    from app.models.notification import Notification

    async def _create(uid: uuid.UUID) -> None:
        async with task_session() as db:
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title=f"{platform} sync failed",
                body=f"Sync failed after multiple retries: {error[:200]}",
                link="/settings",
            ))
            await db.commit()

    _run(_create(uuid.UUID(user_id)))


@shared_task(name="app.services.tasks.notify_tagging_failure")
def notify_tagging_failure(user_id: str, error: str) -> None:
    """Create a notification when auto-tagging fails outside the main loop."""
    from app.models.notification import Notification

    async def _create(uid: uuid.UUID) -> None:
        async with task_session() as db:
            db.add(Notification(
                user_id=uid,
                notification_type="tagging",
                title="Auto-tagging failed",
                body=error[:500],
                link="/settings?tab=tags",
            ))
            await db.commit()

    _run(_create(uuid.UUID(user_id)))


# ---------------------------------------------------------------------------
# Gmail sync tasks
# ---------------------------------------------------------------------------


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

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("sync_gmail_for_user: user %s not found.", uid)
                return {"status": "user_not_found", "new_interactions": 0}

            new_count = await _gmail_sync(user, db)

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
                        logger.warning("gmail: score recalc failed for contact %s", cid)

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


# ---------------------------------------------------------------------------
# Telegram sync tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.sync_telegram_chats_for_user", bind=True, max_retries=3, soft_time_limit=900, time_limit=1200)
def sync_telegram_chats_for_user(self, user_id: str, max_dialogs: int = 100) -> dict:
    """Sync Telegram DM chats for a single user (incremental: most recent N dialogs)."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.telegram import sync_telegram_chats
        from app.services.scoring import calculate_score

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            chat_result = await sync_telegram_chats(user, db, max_dialogs=max_dialogs)
            chat_info = chat_result if isinstance(chat_result, dict) else {
                "new_interactions": chat_result, "new_contacts": 0, "affected_contact_ids": [],
            }

            affected = [uuid.UUID(str(cid)) for cid in chat_info.get("affected_contact_ids", [])]
            for cid in affected:
                try:
                    await calculate_score(cid, db)
                except Exception:
                    logger.warning("telegram_chats: score recalc failed for contact %s", cid)

            if affected:
                await dismiss_suggestions_for_contacts(affected)

            # Mark sync timestamp
            from datetime import UTC, datetime
            user.telegram_last_synced_at = datetime.now(UTC)
            await db.commit()

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
            # FloodWait: return partial result so the chain (groups → bios → notify) continues
            logger.warning("sync_telegram_chats: FloodWait for %s (%ds) — returning partial result to preserve chain.", user_id, exc.seconds)
            return {"status": "partial_flood_wait", "new_interactions": 0, "new_contacts": 0}
        logger.exception("sync_telegram_chats failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Telegram chats", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


BATCH_SIZE = 50  # dialogs per batch for initial Telegram sync


@shared_task(name="app.services.tasks.sync_telegram_chats_batch_task", bind=True, max_retries=2, soft_time_limit=300, time_limit=420)
def sync_telegram_chats_batch_task(self, user_id: str, entity_ids: list[int]) -> dict:
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
                    logger.warning("telegram_chats_batch: score recalc failed for %s", cid)

            if affected:
                await dismiss_suggestions_for_contacts(affected)

            await db.commit()

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
            logger.warning("sync_telegram_chats_batch: FloodWait for %s (%ds) — returning partial result to preserve chain.", user_id, exc.seconds)
            return {"status": "partial_flood_wait", "new_interactions": 0, "new_contacts": 0}
        logger.exception("sync_telegram_chats_batch failed for %s (batch of %d), retrying.", user_id, len(entity_ids))
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(user_id, "telegram", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_telegram_groups_for_user", bind=True, max_retries=3, soft_time_limit=600, time_limit=900)
def sync_telegram_groups_for_user(self, user_id: str) -> dict:
    """Sync Telegram group members for a single user."""
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
                    logger.warning("telegram_groups: score recalc failed for contact %s", cid)

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
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import or_

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
def sync_telegram_notify(user_id: str) -> dict:
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
                link="/contacts",
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

    # Release the sync lock so the next sync is not blocked
    try:
        from app.core.config import settings
        import redis as _redis
        _r = _redis.from_url(settings.REDIS_URL)
        _r.delete(f"tg_sync_lock:{user_id}")
    except Exception:
        logger.warning("sync_telegram_notify: failed to release lock for %s", user_id)

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
    if not _r.set(lock_key, "1", nx=True, ex=21600):  # 6 hour TTL
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
            _r.delete(lock_key)  # Release lock on early return
            return

        # Chunk into batches
        batches = [all_entity_ids[i:i + BATCH_SIZE] for i in range(0, len(all_entity_ids), BATCH_SIZE)]
        logger.info(
            "sync_telegram_for_user: first sync for %s — %d dialogs in %d batches.",
            user_id, len(all_entity_ids), len(batches),
        )

        # Build chain: batch1 → batch2 → ... → groups → bios → notify (releases lock)
        tasks = [sync_telegram_chats_batch_task.si(user_id, batch) for batch in batches]
        tasks.extend([
            sync_telegram_groups_for_user.si(user_id),
            sync_telegram_bios_for_user.si(user_id),
            sync_telegram_notify.si(user_id),
        ])
        chain(*tasks).apply_async()
    else:
        # Incremental sync: most recent 100 dialogs
        # Groups and bios are fetched on-demand (contact detail page visit / Refresh Details)
        # and via periodic recheck tasks — not in the daily chain.
        chain(
            sync_telegram_chats_for_user.si(user_id, 100),
            sync_telegram_notify.si(user_id),
        ).apply_async()


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


# ---------------------------------------------------------------------------
# Follow-up suggestion tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.generate_weekly_suggestions", bind=True, max_retries=3)
def generate_weekly_suggestions(self, user_id: str) -> dict:
    """Generate follow-up suggestions for a single user.

    Args:
        user_id: String representation of the user's UUID.

    Returns:
        A dict with ``generated`` count and ``status``.
    """
    async def _generate(uid: uuid.UUID) -> dict:
        from app.services.followup_engine import generate_suggestions
        from app.services.notifications import notify_new_suggestions

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("generate_weekly_suggestions: user %s not found.", uid)
                return {"status": "user_not_found", "generated": 0}

            ps = user.priority_settings
            suggestions = await generate_suggestions(uid, db, priority_settings=ps)
            if suggestions:
                await notify_new_suggestions(uid, len(suggestions), db)
            await db.commit()

        return {"status": "ok", "generated": len(suggestions)}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("generate_weekly_suggestions: invalid user_id %r", user_id)
        return {"status": "invalid_user_id", "generated": 0}

    try:
        return _run(_generate(uid))
    except Exception as exc:
        logger.exception("generate_weekly_suggestions failed for %s, retrying.", user_id)
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.send_weekly_digests")
def send_weekly_digests() -> dict:
    """Beat-scheduled task: send weekly digest emails to all users (Mondays 09:00 UTC).

    Returns:
        A dict with ``sent`` and ``errors`` counts.
    """
    async def _send_all() -> dict:
        from app.services.digest_email import send_weekly_digest

        sent = 0
        errors = 0

        async with task_session() as db:
            result = await db.execute(select(User.id))
            user_ids = result.scalars().all()

            for uid in user_ids:
                try:
                    await send_weekly_digest(uid, db)
                    sent += 1
                except Exception:
                    logger.exception("send_weekly_digests: failed for user %s.", uid)
                    errors += 1

        return {"sent": sent, "errors": errors}

    result = _run(_send_all())
    logger.info(
        "send_weekly_digests: sent=%d errors=%d", result["sent"], result["errors"]
    )
    return result


@shared_task(name="app.services.tasks.generate_suggestions_all")
def generate_suggestions_all() -> dict:
    """Daily task: generate follow-up suggestions (incl. birthday) for all users."""
    async def _generate_all() -> dict:
        from app.services.followup_engine import generate_suggestions
        from app.services.notifications import notify_new_suggestions

        generated = 0
        errors = 0

        async with task_session() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()

            for user in users:
                try:
                    suggestions = await generate_suggestions(
                        user.id, db, priority_settings=user.priority_settings,
                    )
                    if suggestions:
                        await notify_new_suggestions(user.id, len(suggestions), db)
                    generated += len(suggestions)
                except Exception:
                    logger.exception("generate_suggestions_all: failed for user %s.", user.id)
                    errors += 1

            await db.commit()

        return {"generated": generated, "errors": errors}

    result = _run(_generate_all())
    logger.info(
        "generate_suggestions_all: generated=%d errors=%d",
        result["generated"], result["errors"],
    )
    return result


# ---------------------------------------------------------------------------
# Relationship scoring task
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.update_relationship_scores")
def update_relationship_scores() -> dict:
    """
    Beat-scheduled task: recalculate relationship scores for all contacts.

    Returns:
        A dict with ``updated`` count and ``errors`` count.
    """
    async def _update_all() -> dict:
        from app.services.scoring import calculate_score

        updated = 0
        errors = 0

        async with task_session() as db:
            user_result = await db.execute(select(User.id))
            user_ids = user_result.scalars().all()

            for user_id in user_ids:
                contact_result = await db.execute(
                    select(Contact.id).where(Contact.user_id == user_id)
                )
                contact_ids = contact_result.scalars().all()

                for contact_id in contact_ids:
                    try:
                        await calculate_score(contact_id, db)
                        updated += 1
                    except Exception:
                        logger.exception(
                            "update_relationship_scores: failed for contact %s.", contact_id
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


# ---------------------------------------------------------------------------
# Twitter activity polling tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.poll_twitter_activity", bind=True, max_retries=3, soft_time_limit=900, time_limit=1200)
def poll_twitter_activity(self, user_id: str) -> dict:
    """Poll Twitter activity for all contacts of a single user.

    Fetches recent tweets and bio changes, then runs LLM classification to
    detect noteworthy events (job changes, fundraising, etc.).

    Args:
        user_id: String representation of the user's UUID.

    Returns:
        A dict with ``contacts_processed`` and ``events_created`` counts.
    """
    async def _poll(uid: uuid.UUID) -> dict:
        import uuid as _uuid_mod

        from app.integrations import bird
        from app.integrations.twitter import poll_contacts_activity
        from app.models.notification import Notification
        from app.services.event_classifier import process_contact_activity
        from app.services.notifications import notify_detected_event

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("poll_twitter_activity: user %s not found.", uid)
                return {"status": "user_not_found", "contacts_processed": 0, "events_created": 0}

            activity_records = await poll_contacts_activity(user, db)

            # Surface bird CLI failures to the user (at most once per 24h)
            bird_error = bird.last_error
            if bird_error and not activity_records:
                import redis.asyncio as aioredis
                from app.core.config import settings as _cfg
                _r = aioredis.from_url(_cfg.REDIS_URL)
                dedup_key = f"bird_error_notified:{uid}"
                if not await _r.exists(dedup_key):
                    db.add(Notification(
                        user_id=uid,
                        notification_type="system",
                        title="Twitter enrichment unavailable",
                        body=bird_error[:200],
                        link="/settings",
                    ))
                    await _r.setex(dedup_key, 86400, "1")  # 24h dedup
                await _r.aclose()

            total_events = 0
            for record in activity_records:
                contact_name = record.get("twitter_handle", "Unknown")
                bio_change_payload = None
                if record.get("bio_changed"):
                    bio_change_payload = {
                        "old_bio": record.get("previous_bio", ""),
                        "new_bio": record.get("current_bio", ""),
                        "contact_name": contact_name,
                    }

                contact_uuid = _uuid_mod.UUID(record["contact_id"])
                events = await process_contact_activity(
                    contact_id=contact_uuid,
                    tweets=record.get("tweets", []),
                    bio_change=bio_change_payload,
                    db=db,
                )
                total_events += len(events)

                # Create notifications for detected events
                for event in events:
                    await notify_detected_event(
                        user_id=uid,
                        event_summary=event.summary,
                        contact_name=contact_name,
                        contact_id=contact_uuid,
                        db=db,
                    )

            await db.commit()

        return {
            "status": "ok",
            "contacts_processed": len(activity_records),
            "events_created": total_events,
            "bird_error": bird_error,
        }

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("poll_twitter_activity: invalid user_id %r", user_id)
        return {"status": "invalid_user_id", "contacts_processed": 0, "events_created": 0}

    try:
        return _run(_poll(uid))
    except Exception as exc:
        logger.exception("poll_twitter_activity failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Twitter activity", str(exc))
        raise self.retry(exc=exc, countdown=120) from exc


@shared_task(name="app.services.tasks.sync_twitter_dms_for_user", bind=True, max_retries=3, soft_time_limit=900, time_limit=1200)
def sync_twitter_dms_for_user(self, user_id: str) -> dict:
    """Twitter sync: DMs + mentions + replies + scores + notification."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.twitter import (
            sync_twitter_dms,
            sync_twitter_mentions,
            sync_twitter_replies,
            _user_bearer_headers,
            _refresh_and_retry,
            _build_twitter_id_to_contact_map,
        )
        from app.models.notification import Notification
        from app.services.scoring import calculate_score

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            # Skip DM sync if user has no Twitter OAuth token (Bird CLI handles tweets/profiles separately)
            if not user.twitter_access_token:
                return {"status": "skipped", "reason": "no_twitter_token", "new_interactions": 0}

            headers = await _user_bearer_headers(user, db)
            if not headers:
                return {"status": "skipped", "reason": "no_twitter_token", "new_interactions": 0}

            id_map = await _build_twitter_id_to_contact_map(user, db, headers)

            try:
                dm_result = await sync_twitter_dms(user, db, _id_map=id_map, _headers=headers)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    # Token expired during call — refresh and retry once
                    headers = await _refresh_and_retry(user, db)
                    if not headers:
                        return {"status": "auth_failed", "new_interactions": 0}
                    id_map = await _build_twitter_id_to_contact_map(user, db, headers)
                    dm_result = await sync_twitter_dms(user, db, _id_map=id_map, _headers=headers)
                else:
                    raise

            mentions = await sync_twitter_mentions(user, db, _id_map=id_map, _headers=headers)
            replies = await sync_twitter_replies(user, db, _id_map=id_map, _headers=headers)

            dm_interactions = dm_result["new_interactions"] if isinstance(dm_result, dict) else dm_result
            new_contacts = dm_result.get("new_contacts", 0) if isinstance(dm_result, dict) else 0

            # Bio sync handled by poll_twitter_activity (runs in same beat cycle)

            # Recalculate scores
            try:
                contacts_result = await db.execute(
                    select(Contact.id).where(Contact.user_id == uid)
                )
                for (cid,) in contacts_result.all():
                    await calculate_score(cid, db)
            except Exception:
                logger.warning("sync_twitter: score recalc failed for %s", uid)

            # Notification
            parts = []
            if dm_interactions:
                parts.append(f"{dm_interactions} DMs")
            if mentions:
                parts.append(f"{mentions} mentions")
            if replies:
                parts.append(f"{replies} replies")
            if new_contacts:
                parts.append(f"{new_contacts} new contacts")
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Twitter sync completed",
                body=", ".join(parts) if parts else "No new activity",
                link="/contacts",
            ))
            await db.commit()

        return {"status": "ok", "dms": dm_interactions, "mentions": mentions, "replies": replies, "new_contacts": new_contacts}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_twitter_dms_for_user failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Twitter", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.poll_twitter_all")
def poll_twitter_all() -> dict:
    """Beat-scheduled task (daily): enqueue poll_twitter_activity + DM sync for every user
    that has a twitter_refresh_token set.

    Only users with Twitter connected (twitter_refresh_token IS NOT NULL) are
    enqueued, matching the pattern used by sync_gmail_all().

    Returns:
        A dict with ``queued`` count.
    """
    async def _get_user_ids() -> list[str]:
        async with task_session() as db:
            result = await db.execute(
                select(User.id).where(User.twitter_refresh_token.isnot(None))
            )
            return [str(row) for row in result.scalars().all()]

    user_ids = _run(_get_user_ids())
    for uid in user_ids:
        poll_twitter_activity.delay(uid)
        sync_twitter_dms_for_user.delay(uid)

    logger.info("poll_twitter_all: queued %d user(s) for activity + DMs.", len(user_ids))
    return {"queued": len(user_ids)}


# ---------------------------------------------------------------------------
# Google sync tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.sync_google_contacts_for_user", bind=True, max_retries=3)
def sync_google_contacts_for_user(self, user_id: str) -> dict:
    """Sync Google Contacts for a single user in background."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.google_auth import refresh_access_token
        from app.integrations.google_contacts import fetch_google_contacts
        from app.models.google_account import GoogleAccount
        from app.models.notification import Notification

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            ga_result = await db.execute(
                select(GoogleAccount).where(GoogleAccount.user_id == uid)
            )
            refresh_tokens = [(ga.email, ga.refresh_token) for ga in ga_result.scalars().all()]
            if not refresh_tokens and user.google_refresh_token:
                refresh_tokens = [(user.email, user.google_refresh_token)]
            if not refresh_tokens:
                return {"status": "not_connected"}

            created_count = 0
            updated_count = 0
            archived_count = 0
            errors: list[str] = []
            seen_resource_names: set[str] = set()

            for account_email, token in refresh_tokens:
                try:
                    access_token = refresh_access_token(token)
                    google_contacts = fetch_google_contacts(access_token)
                except Exception as exc:
                    errors.append(f"{account_email}: {exc}")
                    continue

                for fields in google_contacts:
                    try:
                        resource_name = fields.get("resource_name")
                        if resource_name:
                            seen_resource_names.add(resource_name)

                        raw_name = fields.get("full_name")
                        # Parse "Name | Company" patterns
                        if raw_name and not fields.get("company"):
                            import re as _re
                            _name_org_re = _re.compile(r"^(.+?)\s*(?:\||@|/|—|–|-\s)\s*(.+)$")
                            m = _name_org_re.match(raw_name)
                            if m:
                                fields["full_name"] = m.group(1).strip()
                                fields["company"] = m.group(2).strip()

                        emails = fields.get("emails") or []
                        existing = None

                        # Match by google_resource_name first
                        if resource_name:
                            r = await db.execute(
                                select(Contact).where(
                                    Contact.user_id == uid,
                                    Contact.google_resource_name == resource_name,
                                ).limit(1)
                            )
                            existing = r.scalar_one_or_none()

                        # Fall back to email matching
                        if not existing and emails:
                            for email in emails:
                                r = await db.execute(
                                    select(Contact).where(
                                        Contact.user_id == uid,
                                        Contact.emails.any(email),
                                    ).limit(1)
                                )
                                existing = r.scalar_one_or_none()
                                if existing:
                                    break

                        if existing:
                            if raw_name and not existing.full_name:
                                existing.full_name = raw_name
                            if fields.get("given_name") and not existing.given_name:
                                existing.given_name = fields["given_name"]
                            if fields.get("family_name") and not existing.family_name:
                                existing.family_name = fields["family_name"]
                            if fields.get("company") and not existing.company:
                                existing.company = fields["company"]
                            if fields.get("title") and not existing.title:
                                existing.title = fields["title"]
                            new_phones = [p for p in fields.get("phones", []) if p not in (existing.phones or [])]
                            if new_phones:
                                existing.phones = list(existing.phones or []) + new_phones
                            # Stamp resource_name on existing contacts
                            if resource_name and not existing.google_resource_name:
                                existing.google_resource_name = resource_name
                            updated_count += 1
                        else:
                            contact = Contact(
                                user_id=uid,
                                full_name=raw_name,
                                given_name=fields.get("given_name"),
                                family_name=fields.get("family_name"),
                                emails=emails,
                                phones=fields.get("phones", []),
                                company=fields.get("company"),
                                title=fields.get("title"),
                                source="google",
                                google_resource_name=resource_name,
                            )
                            db.add(contact)
                            created_count += 1
                    except Exception as exc:
                        name_hint = fields.get("full_name") or ", ".join(fields.get("emails", [])[:1]) or "unknown"
                        errors.append(f"{name_hint}: {exc}")

            # Archive contacts deleted from Google
            if seen_resource_names:
                stale_result = await db.execute(
                    select(Contact).where(
                        Contact.user_id == uid,
                        Contact.google_resource_name.isnot(None),
                        Contact.google_resource_name.notin_(seen_resource_names),
                        Contact.priority_level != "archived",
                    )
                )
                for stale in stale_result.scalars().all():
                    stale.priority_level = "archived"
                    archived_count += 1
                if archived_count:
                    logger.info(
                        "sync_google_contacts: archived %d contact(s) deleted from Google for user %s",
                        archived_count, uid,
                    )

            # Rescore contacts that have interactions
            if created_count or updated_count:
                from app.services.scoring import calculate_score

                score_result = await db.execute(
                    select(Contact.id).where(
                        Contact.user_id == uid,
                        Contact.last_interaction_at.isnot(None),
                    )
                )
                for (cid,) in score_result.all():
                    try:
                        await calculate_score(cid, db)
                    except Exception:
                        logger.warning("google_contacts: score recalc failed for contact %s", cid)

            parts = []
            if created_count:
                parts.append(f"{created_count} new")
            if updated_count:
                parts.append(f"{updated_count} updated")
            if archived_count:
                parts.append(f"{archived_count} archived")
            if errors:
                parts.append(f"{len(errors)} errors")
            body = ", ".join(parts) if parts else "No changes"
            if errors:
                body += "\n\nErrors:\n" + "\n".join(f"- {e}" for e in errors[:20])
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Google Contacts sync completed",
                body=body,
                link="/contacts",
            ))
            await db.commit()

        return {"status": "ok", "created": created_count, "updated": updated_count}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_google_contacts_for_user failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Google Contacts", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_google_calendar_for_user", bind=True, max_retries=3)
def sync_google_calendar_for_user(self, user_id: str) -> dict:
    """Sync Google Calendar events for a single user in background."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.google_calendar import sync_calendar_events
        from app.models.google_account import GoogleAccount
        from app.models.notification import Notification

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            ga_result = await db.execute(
                select(GoogleAccount).where(GoogleAccount.user_id == uid)
            )
            accounts = list(ga_result.scalars().all())

            if not accounts and not user.google_refresh_token:
                return {"status": "not_connected"}

            cal_result = {"new_contacts": 0, "new_interactions": 0, "events_processed": 0}
            if not accounts and user.google_refresh_token:
                cal_result = await sync_calendar_events(user, db)
            else:
                for ga in accounts:
                    original_token = user.google_refresh_token
                    user.google_refresh_token = ga.refresh_token
                    try:
                        r = await sync_calendar_events(user, db)
                        cal_result["new_contacts"] += r.get("new_contacts", 0)
                        cal_result["new_interactions"] += r.get("new_interactions", 0)
                        cal_result["events_processed"] += r.get("events_processed", 0)
                    except Exception as exc:
                        logger.warning("Calendar sync failed for %s: %s", ga.email, exc)
                    finally:
                        user.google_refresh_token = original_token

            # Rescore contacts that have interactions
            if cal_result.get("new_interactions") or cal_result.get("new_contacts"):
                from app.services.scoring import calculate_score

                score_result = await db.execute(
                    select(Contact.id).where(
                        Contact.user_id == uid,
                        Contact.last_interaction_at.isnot(None),
                    )
                )
                for (cid,) in score_result.all():
                    try:
                        await calculate_score(cid, db)
                    except Exception:
                        logger.warning("google_calendar: score recalc failed for contact %s", cid)

            parts = []
            if cal_result.get("new_contacts"):
                parts.append(f"{cal_result['new_contacts']} new contacts")
            if cal_result.get("new_interactions"):
                parts.append(f"{cal_result['new_interactions']} meetings")
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Google Calendar sync completed",
                body=", ".join(parts) if parts else "No new events",
                link="/contacts",
            ))
            await db.commit()

        return {"status": "ok", **cal_result}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_google_calendar_for_user failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Google Calendar", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_google_calendar_all")
def sync_google_calendar_all() -> dict:
    """Beat-scheduled task: enqueue a ``sync_google_calendar_for_user`` task for every
    user that has a google_refresh_token set.

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
        sync_google_calendar_for_user.delay(uid)

    logger.info("sync_google_calendar_all: queued %d user(s).", len(user_ids))
    return {"queued": len(user_ids)}


# ---------------------------------------------------------------------------
# Snooze reactivation task
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.reactivate_snoozed_suggestions")
def reactivate_snoozed_suggestions() -> dict:
    """Hourly task: set snoozed suggestions back to pending when their scheduled_for has passed."""
    async def _reactivate() -> int:
        from datetime import UTC, datetime

        from app.models.follow_up import FollowUpSuggestion
        from sqlalchemy import update

        async with task_session() as db:
            now = datetime.now(UTC)
            result = await db.execute(
                update(FollowUpSuggestion)
                .where(
                    FollowUpSuggestion.status == "snoozed",
                    FollowUpSuggestion.scheduled_for <= now,
                )
                .values(status="pending")
                .returning(FollowUpSuggestion.id)
            )
            reactivated = len(result.all())
            await db.commit()
            return reactivated

    count = _run(_reactivate())
    logger.info("reactivate_snoozed_suggestions: reactivated %d suggestion(s).", count)
    return {"reactivated": count}


# ---------------------------------------------------------------------------
# Organization stats refresh
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.refresh_org_stats")
def refresh_org_stats() -> dict:
    """Hourly task: refresh the organization_stats_mv materialized view."""
    from sqlalchemy import text as sa_text

    async def _refresh() -> None:
        async with task_session() as db:
            await db.execute(
                sa_text("REFRESH MATERIALIZED VIEW CONCURRENTLY organization_stats_mv")
            )
            await db.commit()

    _run(_refresh())
    logger.info("refresh_org_stats: materialized view refreshed.")
    return {"status": "ok"}


@shared_task(name="app.services.tasks.backfill_org_logos_task")
def backfill_org_logos_task() -> dict:
    """One-time task: download logos for all orgs that have a domain/website but no logo."""
    async def _backfill() -> int:
        from app.services.organization_service import backfill_org_logos
        async with task_session() as db:
            count = await backfill_org_logos(db)
            await db.commit()
            return count

    updated = _run(_backfill())
    logger.info("backfill_org_logos_task: updated %d organizations.", updated)
    return {"status": "ok", "updated": updated}


# ---------------------------------------------------------------------------
# Auto-tagging task
# ---------------------------------------------------------------------------


@shared_task(
    name="app.services.tasks.apply_tags_to_contacts",
    bind=True,
    max_retries=2,
    soft_time_limit=3600,  # 60 minutes for large contact lists (5k+)
    time_limit=3900,       # 65 minutes hard limit
)
def apply_tags_to_contacts(self, user_id: str, contact_ids: list[str] | None = None) -> dict:
    """Apply approved taxonomy tags to contacts in bulk.

    Args:
        user_id: String representation of the user's UUID.
        contact_ids: Optional list of contact ID strings. If None, tags all non-archived contacts.

    Returns:
        A dict with ``tagged_count`` and ``status``.
    """
    async def _apply(uid: uuid.UUID) -> dict:
        import asyncio

        from app.models.interaction import Interaction
        from app.models.notification import Notification
        from app.models.tag_taxonomy import TagTaxonomy
        from app.services.auto_tagger import assign_tags, merge_tags

        async with task_session() as db:
            # Load taxonomy
            tax_result = await db.execute(
                select(TagTaxonomy).where(
                    TagTaxonomy.user_id == uid,
                    TagTaxonomy.status == "approved",
                )
            )
            taxonomy = tax_result.scalar_one_or_none()
            if not taxonomy:
                return {"status": "no_taxonomy", "tagged_count": 0}

            from app.core.config import settings as app_settings

            if not app_settings.ANTHROPIC_API_KEY:
                db.add(Notification(
                    user_id=uid,
                    notification_type="tagging",
                    title="Auto-tagging failed",
                    body="ANTHROPIC_API_KEY is not configured. Set it in your .env file.",
                    link="/settings?tab=tags",
                ))
                await db.commit()
                return {"status": "no_api_key", "tagged_count": 0}

            # Build set of all taxonomy tags for skip-detection
            all_taxonomy_tags = set()
            for tag_list in taxonomy.categories.values():
                all_taxonomy_tags.update(t.lower() for t in tag_list)

            # Load contacts — skip those that already have taxonomy tags
            if contact_ids:
                cid_uuids = [uuid.UUID(c) for c in contact_ids]
                result = await db.execute(
                    select(Contact).where(
                        Contact.id.in_(cid_uuids),
                        Contact.user_id == uid,
                    )
                )
            else:
                from sqlalchemy import or_
                result = await db.execute(
                    select(Contact).where(
                        Contact.user_id == uid,
                        Contact.priority_level != "archived",
                        or_(Contact.tags.is_(None), ~Contact.tags.contains(["2nd tier"])),
                    )
                )
            all_contacts = list(result.scalars().all())

            # Filter out contacts that already have at least one taxonomy tag
            contacts = []
            skipped = 0
            for c in all_contacts:
                if c.tags:
                    existing_lower = {t.lower() for t in c.tags}
                    if existing_lower & all_taxonomy_tags:
                        skipped += 1
                        continue
                contacts.append(c)

            total_eligible = len(contacts)
            logger.info(
                "apply_tags_to_contacts: %d eligible, %d already tagged, %d total for user %s",
                total_eligible, skipped, len(all_contacts), uid,
            )

            if not contacts:
                db.add(Notification(
                    user_id=uid,
                    notification_type="tagging",
                    title="Auto-tagging finished",
                    body=f"All {skipped} contacts already have taxonomy tags." if skipped else "No eligible contacts to tag.",
                    link="/settings?tab=tags",
                ))
                await db.commit()
                return {"status": "ok", "tagged_count": 0}

            # Create ONE shared Anthropic client to avoid connection pool leaks
            from app.services.auto_tagger import _get_anthropic_client
            anthropic_client = _get_anthropic_client()

            tagged = 0
            errors = 0
            BATCH_SIZE = 5  # concurrent API calls per batch
            DB_CHUNK = 200  # load interaction topics in chunks to avoid huge IN clause

            async def _tag_one(contact, topics):
                """Tag a single contact — returns (contact, new_tags) or (contact, None) on error."""
                try:
                    contact_data = {
                        "full_name": contact.full_name,
                        "title": contact.title,
                        "company": contact.company,
                        "twitter_bio": contact.twitter_bio,
                        "telegram_bio": contact.telegram_bio,
                        "notes": contact.notes,
                        "tags": contact.tags,
                        "location": contact.location,
                        "interaction_topics": topics,
                    }
                    new_tags = await assign_tags(
                        contact_data, taxonomy.categories, client=anthropic_client,
                    )
                    return (contact, new_tags)
                except Exception:
                    logger.warning(
                        "apply_tags_to_contacts: failed for contact %s", contact.id,
                        exc_info=True,
                    )
                    return (contact, None)

            # Process contacts in DB-level chunks
            for chunk_start in range(0, len(contacts), DB_CHUNK):
                chunk = contacts[chunk_start:chunk_start + DB_CHUNK]
                chunk_ids = [c.id for c in chunk]

                # Load interaction topics for this chunk only
                int_result = await db.execute(
                    select(Interaction.contact_id, Interaction.content_preview).where(
                        Interaction.contact_id.in_(chunk_ids),
                        Interaction.content_preview.isnot(None),
                    ).order_by(Interaction.occurred_at.desc())
                )
                topics_by_contact: dict[uuid.UUID, list[str]] = {}
                for row in int_result.all():
                    lst = topics_by_contact.setdefault(row[0], [])
                    if len(lst) < 10:
                        lst.append(row[1][:100])

                # Process in concurrent API batches
                for i in range(0, len(chunk), BATCH_SIZE):
                    batch = chunk[i:i + BATCH_SIZE]
                    results = await asyncio.gather(*[
                        _tag_one(c, topics_by_contact.get(c.id, []))
                        for c in batch
                    ])

                    for contact, new_tags in results:
                        if new_tags is None:
                            errors += 1
                        elif new_tags:
                            contact.tags = merge_tags(contact.tags, new_tags)
                            tagged += 1

                # Commit after each DB chunk to save progress
                await db.commit()
                logger.info(
                    "apply_tags_to_contacts: chunk %d-%d done, tagged=%d errors=%d for user %s",
                    chunk_start, chunk_start + len(chunk), tagged, errors, uid,
                )

            # Notification
            body = f"Tagged {tagged} of {total_eligible} contacts"
            if skipped:
                body += f" ({skipped} already tagged)"
            if errors:
                body += f" ({errors} errors — check worker logs)"
            db.add(Notification(
                user_id=uid,
                notification_type="tagging",
                title="Auto-tagging completed" if tagged > 0 else "Auto-tagging finished with issues",
                body=body,
                link="/settings?tab=tags",
            ))
            await db.commit()

        return {"status": "ok", "tagged_count": tagged}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id", "tagged_count": 0}

    try:
        return _run(_apply(uid))
    except Exception as exc:
        # Don't retry on soft time limit — partial results already committed
        from celery.exceptions import SoftTimeLimitExceeded
        if isinstance(exc, SoftTimeLimitExceeded):
            logger.warning("apply_tags_to_contacts: soft time limit hit for %s", user_id)
            # Notify user — partial progress was saved via periodic commits
            notify_tagging_failure.delay(str(uid), "Tagging timed out. Partial progress was saved. Try again to tag remaining contacts.")
            return {"status": "timeout", "tagged_count": 0}
        logger.exception("apply_tags_to_contacts failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_tagging_failure.delay(str(uid), f"Tagging failed after retries: {str(exc)[:200]}")
        raise self.retry(exc=exc, countdown=30) from exc
