"""Tests for GET /api/v1/version."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_version_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/version")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_version_returns_cached_status(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=json.dumps({
        "tag_name": "v1.7.0",
        "html_url": "https://github.com/sneg55/pingcrm/releases/tag/v1.7.0",
        "body": "notes",
        "name": "v1.7.0",
        "fetched_at": datetime(2026, 5, 12, tzinfo=timezone.utc).isoformat(),
    }))
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    resp = await client.get("/api/v1/version", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["current"] == "v1.6.0"
    assert data["latest"] == "v1.7.0"
    assert data["update_available"] is True
    assert data["release_url"].endswith("v1.7.0")
    assert data["disabled"] is False


@pytest.mark.asyncio
async def test_version_empty_cache_enqueues_refresh(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    fake_task = MagicMock()
    monkeypatch.setattr("app.api.version.check_for_updates", fake_task)

    resp = await client.get("/api/v1/version", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["update_available"] is None
    fake_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_version_empty_cache_with_failure_marker_does_not_enqueue(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(side_effect=[None, b"1"])
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    fake_task = MagicMock()
    monkeypatch.setattr("app.api.version.check_for_updates", fake_task)

    resp = await client.get("/api/v1/version", headers=auth_headers)

    assert resp.status_code == 200
    fake_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_version_disabled(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setenv("DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )
    resp = await client.get("/api/v1/version", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["disabled"] is True
    assert data["update_available"] is None
