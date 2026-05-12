"""Celery task: poll GitHub for latest release and cache result."""
import asyncio
import logging

from celery import shared_task

from app.services.version_checker import is_disabled, refresh_cache

logger = logging.getLogger(__name__)


@shared_task(name="app.services.tasks.check_for_updates")
def check_for_updates() -> None:
    """Periodic task: refresh the version-check cache from GitHub."""
    if is_disabled():
        return
    try:
        asyncio.run(refresh_cache())
    except Exception:
        logger.exception(
            "version check task failed",
            extra={"provider": "github"},
        )
