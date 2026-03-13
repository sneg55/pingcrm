"""Celery application factory for Ping CRM."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "pingcrm",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.services.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Prevent tasks from hanging indefinitely
    task_soft_time_limit=300,  # 5 minutes
    task_time_limit=600,       # 10 minutes hard limit
    # Beat schedule
    beat_schedule={
        # Sync Gmail for all users every 6 hours
        "sync-gmail-all-every-6h": {
            "task": "app.services.tasks.sync_gmail_all",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        # Recalculate relationship scores every day at 02:00 UTC
        "update-relationship-scores-daily": {
            "task": "app.services.tasks.update_relationship_scores",
            "schedule": crontab(minute=0, hour=2),
        },
        # Sync Telegram for all users every 12 hours
        "sync-telegram-all-every-12h": {
            "task": "app.services.tasks.sync_telegram_all",
            "schedule": crontab(minute=0, hour="*/12"),
        },
        # Send weekly networking digest every Monday at 09:00 UTC
        "send-weekly-digests-monday": {
            "task": "app.services.tasks.send_weekly_digests",
            "schedule": crontab(minute=0, hour=9, day_of_week=1),
        },
        # Poll Twitter/X activity for all users once daily at 04:00 UTC
        "poll-twitter-all-daily": {
            "task": "app.services.tasks.poll_twitter_all",
            "schedule": crontab(minute=0, hour=4),
        },
        # Generate follow-up suggestions (incl. birthday) daily at 08:00 UTC
        "generate-suggestions-daily": {
            "task": "app.services.tasks.generate_suggestions_all",
            "schedule": crontab(minute=0, hour=8),
        },
        # Reactivate snoozed suggestions every hour
        "reactivate-snoozed-suggestions-hourly": {
            "task": "app.services.tasks.reactivate_snoozed_suggestions",
            "schedule": crontab(minute=0),
        },
        # Refresh organization stats materialized view every hour
        "refresh-org-stats-hourly": {
            "task": "app.services.tasks.refresh_org_stats",
            "schedule": crontab(minute=30),
        },
    },
)
