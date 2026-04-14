from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_map_config_returns_public_token(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MAPBOX_PUBLIC_TOKEN", "pk.test")
    resp = await client.get("/api/v1/map/config", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["mapbox_public_token"] == "pk.test"


@pytest.mark.asyncio
async def test_map_config_empty_when_unset(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MAPBOX_PUBLIC_TOKEN", "")
    resp = await client.get("/api/v1/map/config", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["mapbox_public_token"] == ""


@pytest.mark.asyncio
async def test_map_config_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/map/config")
    # 401 or 403 depending on project auth dep behavior — anything non-200 is fine
    assert resp.status_code in (401, 403)
