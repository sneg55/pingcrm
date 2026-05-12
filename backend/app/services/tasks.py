"""Backward-compatible re-export of all Celery tasks.

Tasks are now organized in app.services.task_jobs/ by domain.
This module re-exports them so existing imports and Celery task names
continue to work unchanged.
"""
from app.services.task_jobs.common import (
    _run,
    logger,
    dismiss_suggestions_for_contacts,
    notify_sync_failure,
    notify_tagging_failure,
)
from app.services.task_jobs.gmail import (
    sync_gmail_for_user,
    sync_gmail_all,
)
from app.services.task_jobs.telegram import (
    sync_telegram_chats_for_user,
    sync_telegram_chats_batch_task,
    sync_telegram_groups_for_user,
    sync_telegram_bios_for_user,
    recheck_telegram_bios_all,
    sync_telegram_notify,
    sync_telegram_for_user,
    cleanup_stale_telegram_locks,
    sync_telegram_all,
)
from app.services.task_jobs.twitter import (
    poll_twitter_activity,
    sync_twitter_dms_for_user,
    poll_twitter_all,
)
from app.services.task_jobs.google import (
    sync_google_contacts_for_user,
    sync_google_calendar_for_user,
    sync_google_calendar_all,
)
from app.services.task_jobs.scoring import (
    update_relationship_scores,
)
from app.services.task_jobs.followups import (
    generate_weekly_suggestions,
    send_weekly_digests,
    generate_suggestions_all,
    reactivate_snoozed_suggestions,
)
from app.services.task_jobs.maintenance import (
    refresh_org_stats,
    backfill_org_logos_task,
)
from app.services.task_jobs.tagging import (
    apply_tags_to_contacts,
)
from app.services.task_jobs.meeting_prep import (
    scan_meeting_preps,
)
from app.services.task_jobs.whatsapp import (
    sync_whatsapp_backfill,
    check_whatsapp_sessions,
)
from app.services.task_jobs.geocoding import (
    geocode_contact,
    backfill_all_contacts,
)
from app.services.task_jobs.version_check import (
    check_for_updates,
)

__all__ = [
    # common
    "_run",
    "logger",
    "dismiss_suggestions_for_contacts",
    "notify_sync_failure",
    "notify_tagging_failure",
    # gmail
    "sync_gmail_for_user",
    "sync_gmail_all",
    # telegram
    "sync_telegram_chats_for_user",
    "sync_telegram_chats_batch_task",
    "sync_telegram_groups_for_user",
    "sync_telegram_bios_for_user",
    "recheck_telegram_bios_all",
    "sync_telegram_notify",
    "sync_telegram_for_user",
    "cleanup_stale_telegram_locks",
    "sync_telegram_all",
    # twitter
    "poll_twitter_activity",
    "sync_twitter_dms_for_user",
    "poll_twitter_all",
    # google
    "sync_google_contacts_for_user",
    "sync_google_calendar_for_user",
    "sync_google_calendar_all",
    # scoring
    "update_relationship_scores",
    # followups
    "generate_weekly_suggestions",
    "send_weekly_digests",
    "generate_suggestions_all",
    "reactivate_snoozed_suggestions",
    # maintenance
    "refresh_org_stats",
    "backfill_org_logos_task",
    # tagging
    "apply_tags_to_contacts",
    # meeting prep
    "scan_meeting_preps",
    # whatsapp
    "sync_whatsapp_backfill",
    "check_whatsapp_sessions",
    # geocoding
    "geocode_contact",
    "backfill_all_contacts",
    # version check
    "check_for_updates",
]
