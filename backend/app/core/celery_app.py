"""Celery application factory for PingCRM."""
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
        # Sync Telegram for all users once daily at 03:00 UTC
        "sync-telegram-all-daily": {
            "task": "app.services.tasks.sync_telegram_all",
            "schedule": crontab(minute=0, hour=3),
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
        # Sync Google Calendar for all users once daily at 06:00 UTC
        "sync-google-calendar-all-daily": {
            "task": "app.services.tasks.sync_google_calendar_all",
            "schedule": crontab(minute=0, hour=6),
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
        # Recheck Telegram bios every 3 days for non-2nd-tier contacts
        "recheck-telegram-bios-every-3d": {
            "task": "app.services.tasks.recheck_telegram_bios_all",
            "schedule": crontab(minute=0, hour=5, day_of_month="1,4,7,10,13,16,19,22,25,28"),
        },
        # Watchdog: remove orphaned Telegram sync locks every hour at :15
        "cleanup-stale-telegram-locks-hourly": {
            "task": "app.services.tasks.cleanup_stale_telegram_locks",
            "schedule": crontab(minute=15),
        },
        # Scan for upcoming meetings and send prep emails every 10 minutes
        "scan-meeting-preps-every-10m": {
            "task": "app.services.tasks.scan_meeting_preps",
            "schedule": crontab(minute="*/10"),
        },
        # Check WhatsApp session health daily at 01:00 UTC
        "check-whatsapp-sessions-daily": {
            "task": "app.services.tasks.check_whatsapp_sessions",
            "schedule": crontab(minute=0, hour=1),
        },
    },
)
