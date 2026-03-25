"""Celery beat task: scan upcoming meetings and send prep emails."""
from __future__ import annotations

from collections import defaultdict

import redis as _redis
from celery import shared_task
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.core.config import settings
from app.core.database import task_session
from app.models.google_account import GoogleAccount
from app.models.notification import Notification
from app.models.user import User
from app.services.task_jobs.common import _run, logger


@shared_task(name="app.services.tasks.scan_meeting_preps", bind=True, max_retries=2)
def scan_meeting_preps(self) -> dict:
    """Scan for meetings starting in ~30 minutes and email prep briefs."""

    # Redis client created outside async function (sync context is correct here)
    r = _redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def _scan() -> dict:
        from app.integrations.gmail_send import send_email
        from app.services.meeting_prep import (
            build_prep_brief,
            compose_prep_email,
            generate_talking_points,
            get_upcoming_meetings,
        )

        now = datetime.now(UTC)
        window_start = now + timedelta(minutes=30)
        window_end = now + timedelta(minutes=40)

        sent = 0
        skipped = 0
        errors = 0

        async with task_session() as db:
            # Bulk-fetch all Google-connected user IDs (2 queries, not N+1)
            ga_result = await db.execute(
                select(GoogleAccount.user_id).distinct()
            )
            ga_user_ids = {row for row in ga_result.scalars().all()}

            legacy_result = await db.execute(
                select(User.id).where(User.google_refresh_token.isnot(None))
            )
            legacy_user_ids = {row for row in legacy_result.scalars().all()}

            all_user_ids = ga_user_ids | legacy_user_ids
            if not all_user_ids:
                return {"sent": 0, "skipped": 0, "errors": 0}

            # Bulk-fetch all users and Google accounts in 2 queries (not per-user)
            users_result = await db.execute(
                select(User).where(User.id.in_(all_user_ids))
            )
            users_by_id = {u.id: u for u in users_result.scalars().all()}

            ga_all_result = await db.execute(
                select(GoogleAccount).where(GoogleAccount.user_id.in_(all_user_ids))
            )
            ga_by_user: dict[object, list] = defaultdict(list)
            for ga in ga_all_result.scalars().all():
                ga_by_user[ga.user_id].append(ga)

            for user_id in all_user_ids:
                user = users_by_id.get(user_id)
                if user is None:
                    continue

                # Check meeting_prep_enabled setting (default True)
                sync_settings = user.sync_settings or {}
                gmail_settings = sync_settings.get("gmail", {})
                if not gmail_settings.get("meeting_prep_enabled", True):
                    skipped += 1
                    continue

                google_accounts = ga_by_user.get(user_id, [])

                meetings = await get_upcoming_meetings(
                    user_id, window_start, window_end, db
                )

                for meeting in meetings:
                    event_id = meeting["event_id"]
                    dedup_key = f"meeting_prep:{user_id}:{event_id}"

                    # Redis dedup check (sync call, OK in _run() context)
                    if r.exists(dedup_key):
                        skipped += 1
                        continue

                    contact_ids = meeting.get("contact_ids", [])
                    if not contact_ids:
                        skipped += 1
                        continue

                    briefs = await build_prep_brief(contact_ids, db)
                    if not briefs:
                        skipped += 1
                        continue

                    talking_points = await generate_talking_points(
                        briefs, meeting["title"]
                    )
                    subject, html = compose_prep_email(
                        meeting, briefs, talking_points
                    )

                    # Determine which Google account to use for sending
                    if google_accounts:
                        ga = google_accounts[0]
                    elif user.google_refresh_token:
                        ga = SimpleNamespace(
                            refresh_token=user.google_refresh_token,
                            email=user.email,
                        )
                    else:
                        skipped += 1
                        continue

                    result = send_email(ga, subject, html)

                    if result is True:
                        r.set(dedup_key, "1", ex=86400)  # 24h TTL
                        sent += 1
                    elif result == "auth_error":
                        db.add(Notification(
                            user_id=user_id,
                            notification_type="system",
                            title="Re-authorize Gmail for meeting prep emails",
                            body="Your Gmail credentials have expired. Please re-connect Gmail in Settings to continue receiving meeting prep emails.",
                            link="/settings",
                        ))
                        break  # Stop for this user
                    else:
                        errors += 1

            await db.commit()

        return {"sent": sent, "skipped": skipped, "errors": errors}

    try:
        return _run(_scan())
    except Exception as exc:
        logger.exception("scan_meeting_preps failed, retrying")
        raise self.retry(exc=exc, countdown=30) from exc
