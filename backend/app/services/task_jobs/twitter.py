"""Twitter/X activity polling and DM sync Celery tasks."""
from __future__ import annotations

import uuid

import httpx

from celery import shared_task
from sqlalchemy import select

from app.core.database import task_session
from app.models.contact import Contact
from app.models.user import User
from app.services.task_jobs.common import _run, logger, notify_sync_failure


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
        from app.integrations import bird
        from app.integrations.twitter import poll_contacts_activity
        from app.models.notification import Notification

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("poll_twitter_activity: user %s not found.", uid)
                return {"status": "user_not_found", "contacts_processed": 0}

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

            bio_changes = sum(1 for r in activity_records if r.get("bio_changed"))
            await db.commit()

        return {
            "status": "ok",
            "contacts_processed": len(activity_records),
            "bio_changes": bio_changes,
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
        )
        from app.integrations.twitter_contacts import _build_twitter_id_to_contact_map
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

            from app.services.sync_history import record_sync_start, record_sync_complete, record_sync_failure
            sync_event = await record_sync_start(uid, "twitter", "scheduled", db)

            id_map = await _build_twitter_id_to_contact_map(user, db, headers)

            try:
                dm_result = await sync_twitter_dms(user, db, _id_map=id_map, _headers=headers)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    # Token expired during call — refresh and retry once
                    headers = await _refresh_and_retry(user, db)
                    if not headers:
                        await record_sync_failure(sync_event, "Token refresh failed (401)", db=db)
                        await db.commit()
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
                logger.warning("sync_twitter: score recalc failed for %s", uid, exc_info=True)

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
            total_new = dm_interactions + mentions + replies
            await record_sync_complete(
                sync_event,
                records_created=total_new,
                details={"dms": dm_interactions, "mentions": mentions, "replies": replies, "new_contacts": new_contacts},
                db=db,
            )
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Twitter sync completed",
                body=", ".join(parts) if parts else "No new activity",
                link="/settings",
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
