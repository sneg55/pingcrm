"""Tests for sync history API endpoints."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_event import SyncEvent
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    user_id: uuid.UUID,
    platform: str = "telegram",
    status: str = "success",
    sync_type: str = "manual",
    records_created: int = 5,
    duration_ms: int = 1000,
    started_at: datetime | None = None,
) -> SyncEvent:
    return SyncEvent(
        user_id=user_id,
        platform=platform,
        sync_type=sync_type,
        status=status,
        records_created=records_created,
        duration_ms=duration_ms,
        started_at=started_at or datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/sync-history — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sync_events_empty(client: AsyncClient, auth_headers: dict):
    """Returns an empty list when no sync events exist."""
    resp = await client.get("/api/v1/sync-history", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["error"] is None
    assert body["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_list_sync_events_returns_events(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Creates SyncEvent records directly in DB and verifies the API returns them."""
    events = [
        _make_event(test_user.id, platform="telegram"),
        _make_event(test_user.id, platform="gmail"),
    ]
    for e in events:
        db.add(e)
    await db.commit()

    resp = await client.get("/api/v1/sync-history", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 2
    platforms = {item["platform"] for item in body["data"]}
    assert platforms == {"telegram", "gmail"}


@pytest.mark.asyncio
async def test_list_sync_events_filters_by_platform(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """filter by platform=telegram returns only telegram events."""
    db.add(_make_event(test_user.id, platform="telegram"))
    db.add(_make_event(test_user.id, platform="gmail"))
    db.add(_make_event(test_user.id, platform="telegram"))
    await db.commit()

    resp = await client.get(
        "/api/v1/sync-history?platform=telegram", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 2
    for item in body["data"]:
        assert item["platform"] == "telegram"


@pytest.mark.asyncio
async def test_list_sync_events_filters_by_status(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """filter by status=success returns only successful events."""
    db.add(_make_event(test_user.id, status="success"))
    db.add(_make_event(test_user.id, status="failed"))
    db.add(_make_event(test_user.id, status="success"))
    await db.commit()

    resp = await client.get(
        "/api/v1/sync-history?status=success", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 2
    for item in body["data"]:
        assert item["status"] == "success"


@pytest.mark.asyncio
async def test_list_sync_events_pagination(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """limit and offset query params work correctly."""
    now = datetime.now(UTC)
    for i in range(5):
        db.add(_make_event(
            test_user.id,
            platform="telegram",
            started_at=now - timedelta(minutes=i),
        ))
    await db.commit()

    # First page: limit=2, offset=0
    resp1 = await client.get(
        "/api/v1/sync-history?limit=2&offset=0", headers=auth_headers
    )
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1["meta"]["total"] == 5
    assert len(body1["data"]) == 2

    # Second page: limit=2, offset=2
    resp2 = await client.get(
        "/api/v1/sync-history?limit=2&offset=2", headers=auth_headers
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["data"]) == 2

    # Pages must not overlap
    ids1 = {item["id"] for item in body1["data"]}
    ids2 = {item["id"] for item in body2["data"]}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_list_sync_events_requires_auth(client: AsyncClient):
    """401 when no token is provided."""
    resp = await client.get("/api/v1/sync-history")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/sync-history/stats — per-platform stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_stats_returns_per_platform_stats(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Create mixed events across platforms and verify stats breakdown."""
    # telegram: 2 success, 1 failed
    db.add(_make_event(test_user.id, platform="telegram", status="success"))
    db.add(_make_event(test_user.id, platform="telegram", status="success"))
    db.add(_make_event(test_user.id, platform="telegram", status="failed"))
    # gmail: 1 success
    db.add(_make_event(test_user.id, platform="gmail", status="success"))
    await db.commit()

    resp = await client.get("/api/v1/sync-history/stats", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    data = body["data"]

    assert "telegram" in data
    tg = data["telegram"]
    assert tg["total_syncs"] == 3
    assert tg["success_count"] == 2
    assert tg["failed_count"] == 1
    assert tg["success_rate"] == pytest.approx(66.7, abs=0.1)

    assert "gmail" in data
    gm = data["gmail"]
    assert gm["total_syncs"] == 1
    assert gm["success_count"] == 1
    assert gm["failed_count"] == 0
    assert gm["success_rate"] == 100.0


@pytest.mark.asyncio
async def test_sync_stats_empty_returns_empty_dict(
    client: AsyncClient, auth_headers: dict
):
    """No sync events returns an empty stats dict."""
    resp = await client.get("/api/v1/sync-history/stats", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == {}


@pytest.mark.asyncio
async def test_sync_stats_requires_auth(client: AsyncClient):
    """401 when no token is provided for stats endpoint."""
    resp = await client.get("/api/v1/sync-history/stats")
    assert resp.status_code == 401
