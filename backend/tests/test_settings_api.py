"""Tests for settings API endpoints."""
import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_get_priority_requires_auth(client: AsyncClient):
    """GET /priority returns 401 when no token is provided."""
    resp = await client.get("/api/v1/settings/priority")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_priority_returns_defaults_for_new_user(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    """A freshly created user should receive the hard-coded default intervals."""
    resp = await client.get("/api/v1/settings/priority", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["high"] == 30
    assert data["medium"] == 60
    assert data["low"] == 180


@pytest.mark.asyncio
async def test_get_priority_returns_saved_settings(
    client: AsyncClient, auth_headers: dict
):
    """After persisting custom settings via PUT, GET should return those values."""
    payload = {"high": 14, "medium": 45, "low": 90}
    put_resp = await client.put(
        "/api/v1/settings/priority", json=payload, headers=auth_headers
    )
    assert put_resp.status_code == 200

    resp = await client.get("/api/v1/settings/priority", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["high"] == 14
    assert data["medium"] == 45
    assert data["low"] == 90


@pytest.mark.asyncio
async def test_update_priority_requires_auth(client: AsyncClient):
    """PUT /priority returns 401 when no token is provided."""
    resp = await client.put(
        "/api/v1/settings/priority",
        json={"high": 14, "medium": 45, "low": 90},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_priority_persists_new_values(
    client: AsyncClient, auth_headers: dict
):
    """PUT /priority saves values and immediately returns them."""
    payload = {"high": 10, "medium": 30, "low": 120}
    resp = await client.put(
        "/api/v1/settings/priority", json=payload, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["high"] == 10
    assert data["medium"] == 30
    assert data["low"] == 120

    # A subsequent GET should reflect the persisted values.
    resp2 = await client.get("/api/v1/settings/priority", headers=auth_headers)
    assert resp2.status_code == 200
    data2 = resp2.json()["data"]
    assert data2["high"] == 10
    assert data2["medium"] == 30
    assert data2["low"] == 120


@pytest.mark.asyncio
async def test_update_priority_rejects_interval_below_minimum(
    client: AsyncClient, auth_headers: dict
):
    """Values below 7 days should be rejected with 422."""
    resp = await client.put(
        "/api/v1/settings/priority",
        json={"high": 6, "medium": 60, "low": 180},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_priority_rejects_interval_above_maximum(
    client: AsyncClient, auth_headers: dict
):
    """Values above 365 days should be rejected with 422."""
    resp = await client.put(
        "/api/v1/settings/priority",
        json={"high": 30, "medium": 60, "low": 366},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_priority_accepts_boundary_values(
    client: AsyncClient, auth_headers: dict
):
    """Minimum (7) and maximum (365) values must be accepted."""
    resp = await client.put(
        "/api/v1/settings/priority",
        json={"high": 7, "medium": 180, "low": 365},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["high"] == 7
    assert data["medium"] == 180
    assert data["low"] == 365


@pytest.mark.asyncio
async def test_update_suggestion_prefs_persists_consecutive_writes(
    client: AsyncClient, auth_headers: dict
):
    """Two consecutive PUTs must both persist.

    Regression for a silent-write bug where the JSONB column wasn't wrapped
    with MutableDict, so in-place mutations of the same dict reference were
    not detected by SQLAlchemy and subsequent UPDATEs were no-ops.
    """
    # First save — works even with the bug because the column was NULL.
    r1 = await client.put(
        "/api/v1/settings/suggestions",
        json={"dormancy_threshold_days": 730},
        headers=auth_headers,
    )
    assert r1.status_code == 200
    assert r1.json()["data"]["dormancy_threshold_days"] == 730

    g1 = await client.get("/api/v1/settings/suggestions", headers=auth_headers)
    assert g1.json()["data"]["dormancy_threshold_days"] == 730

    # Second save — this is what regressed: same dict reference, so the
    # change wasn't flagged and didn't persist.
    r2 = await client.put(
        "/api/v1/settings/suggestions",
        json={"dormancy_threshold_days": 1095},
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["dormancy_threshold_days"] == 1095

    g2 = await client.get("/api/v1/settings/suggestions", headers=auth_headers)
    assert g2.json()["data"]["dormancy_threshold_days"] == 1095
