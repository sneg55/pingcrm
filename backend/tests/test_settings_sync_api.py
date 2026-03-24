"""Tests for sync settings and telegram settings API endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_get_sync_settings_returns_defaults(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    """A new user should receive the hard-coded default sync settings."""
    resp = await client.get("/api/v1/settings/sync", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["telegram"] == {"auto_sync": True, "schedule": "daily"}
    assert data["gmail"] == {"auto_sync": True, "schedule": "6h"}
    assert data["twitter"] == {"auto_sync": True, "schedule": "daily"}
    assert data["linkedin"] == {"auto_sync": False, "schedule": "manual"}


@pytest.mark.asyncio
async def test_update_sync_settings_updates_platform(
    client: AsyncClient, auth_headers: dict
):
    """PUT telegram auto_sync=false should be reflected in subsequent GET."""
    put_resp = await client.put(
        "/api/v1/settings/sync",
        json={"telegram": {"auto_sync": False, "schedule": "daily"}},
        headers=auth_headers,
    )
    assert put_resp.status_code == 200

    get_resp = await client.get("/api/v1/settings/sync", headers=auth_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()["data"]
    assert data["telegram"]["auto_sync"] is False
    assert data["telegram"]["schedule"] == "daily"


@pytest.mark.asyncio
async def test_update_sync_settings_preserves_other_platforms(
    client: AsyncClient, auth_headers: dict
):
    """Updating telegram settings must not affect gmail settings."""
    await client.put(
        "/api/v1/settings/sync",
        json={"telegram": {"auto_sync": False}},
        headers=auth_headers,
    )

    get_resp = await client.get("/api/v1/settings/sync", headers=auth_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()["data"]
    # Gmail defaults should be intact
    assert data["gmail"]["auto_sync"] is True
    assert data["gmail"]["schedule"] == "6h"
    # Twitter defaults should be intact
    assert data["twitter"]["auto_sync"] is True


@pytest.mark.asyncio
async def test_get_telegram_settings_returns_default_true(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    """sync_2nd_tier defaults to true for a new user."""
    resp = await client.get("/api/v1/settings/telegram", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["sync_2nd_tier"] is True


@pytest.mark.asyncio
async def test_update_telegram_settings_toggle(
    client: AsyncClient, auth_headers: dict
):
    """Set sync_2nd_tier=false via PUT, verify GET returns the updated value."""
    put_resp = await client.put(
        "/api/v1/settings/telegram",
        json={"sync_2nd_tier": False},
        headers=auth_headers,
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["data"]["sync_2nd_tier"] is False

    get_resp = await client.get("/api/v1/settings/telegram", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["sync_2nd_tier"] is False


@pytest.mark.asyncio
async def test_settings_require_auth(client: AsyncClient):
    """All sync settings endpoints return 401 without a token."""
    for method, url in [
        ("get", "/api/v1/settings/sync"),
        ("put", "/api/v1/settings/sync"),
        ("get", "/api/v1/settings/telegram"),
        ("put", "/api/v1/settings/telegram"),
    ]:
        resp = await getattr(client, method)(url)
        assert resp.status_code == 401, f"{method.upper()} {url} should require auth"
