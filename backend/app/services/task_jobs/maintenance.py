"""Maintenance Celery tasks (org stats, logo backfill)."""
from __future__ import annotations

from celery import shared_task

from app.core.database import task_session
from app.services.task_jobs.common import _run, logger


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


# cleanup_stale_telegram_locks lives in telegram.py (canonical version with TTL check)


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
