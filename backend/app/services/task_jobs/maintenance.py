"""Maintenance Celery tasks (org stats, logo backfill).

The Celery entrypoints (``refresh_org_stats`` / ``backfill_org_logos_task``)
are thin wrappers around the ``_refresh_org_stats`` / ``_backfill_org_logos``
coroutines so the maintenance logic is directly unit-testable against a real
``AsyncSession`` without spinning up a Celery broker or the ``task_session``
machinery.
"""
from __future__ import annotations

from celery import shared_task
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import task_session
from app.services.organization_service import backfill_org_logos
from app.services.task_jobs.common import _run, logger


async def _refresh_org_stats(db: AsyncSession) -> None:
    """Refresh the ``organization_stats_mv`` materialized view concurrently."""
    await db.execute(
        sa_text("REFRESH MATERIALIZED VIEW CONCURRENTLY organization_stats_mv")
    )
    await db.commit()


async def _backfill_org_logos(db: AsyncSession) -> int:
    """Download logos for orgs missing one. Returns the number updated."""
    count = await backfill_org_logos(db)
    await db.commit()
    return count


@shared_task(name="app.services.tasks.refresh_org_stats")
def refresh_org_stats() -> dict:
    """Hourly task: refresh the organization_stats_mv materialized view."""
    async def _runner() -> None:
        async with task_session() as db:
            await _refresh_org_stats(db)

    _run(_runner())
    logger.info("refresh_org_stats: materialized view refreshed.")
    return {"status": "ok"}


# cleanup_stale_telegram_locks lives in telegram.py (canonical version with TTL check)


@shared_task(name="app.services.tasks.backfill_org_logos_task")
def backfill_org_logos_task() -> dict:
    """One-time task: download logos for all orgs that have a domain/website but no logo."""
    async def _runner() -> int:
        async with task_session() as db:
            return await _backfill_org_logos(db)

    updated = _run(_runner())
    logger.info("backfill_org_logos_task: updated %d organizations.", updated)
    return {"status": "ok", "updated": updated}
