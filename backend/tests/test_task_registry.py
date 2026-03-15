import pytest
from app.core.celery_app import celery_app

# Import tasks module to trigger registration
import app.services.tasks  # noqa: F401


def test_celery_task_registry():
    """All expected Celery task names must be registered."""
    registered = set(celery_app.tasks.keys())

    expected_tasks = {
        "app.services.tasks.notify_sync_failure",
        "app.services.tasks.notify_tagging_failure",
        "app.services.tasks.sync_gmail_for_user",
        "app.services.tasks.sync_gmail_all",
        "app.services.tasks.sync_telegram_chats_for_user",
        "app.services.tasks.sync_telegram_chats_batch_task",
        "app.services.tasks.sync_telegram_groups_for_user",
        "app.services.tasks.sync_telegram_bios_for_user",
        "app.services.tasks.recheck_telegram_bios_all",
        "app.services.tasks.sync_telegram_notify",
        "app.services.tasks.sync_telegram_all",
        "app.services.tasks.generate_weekly_suggestions",
        "app.services.tasks.send_weekly_digests",
        "app.services.tasks.generate_suggestions_all",
        "app.services.tasks.update_relationship_scores",
        "app.services.tasks.poll_twitter_activity",
        "app.services.tasks.sync_twitter_dms_for_user",
        "app.services.tasks.poll_twitter_all",
        "app.services.tasks.sync_google_contacts_for_user",
        "app.services.tasks.sync_google_calendar_for_user",
        "app.services.tasks.sync_google_calendar_all",
        "app.services.tasks.reactivate_snoozed_suggestions",
        "app.services.tasks.refresh_org_stats",
        "app.services.tasks.backfill_org_logos_task",
    }

    missing = expected_tasks - registered
    assert not missing, f"Missing Celery tasks: {missing}"


def test_beat_schedule_tasks_are_registered():
    """Every task in the beat schedule must be importable."""
    for name, entry in celery_app.conf.beat_schedule.items():
        task_name = entry["task"]
        assert task_name in celery_app.tasks, (
            f"Beat schedule task '{task_name}' (schedule entry '{name}') is not registered"
        )
