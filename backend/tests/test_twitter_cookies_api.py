"""TDD tests for POST / DELETE / GET /api/v1/integrations/twitter/cookies."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_post_cookies_sets_status_connected_when_whoami_succeeds(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: object,
    test_user: User,
    monkeypatch,
):
    async def _fake_verify(a, c):
        return True

    monkeypatch.setattr("app.api.twitter_cookies.verify_cookies", _fake_verify)

    resp = await client.post(
        "/api/v1/integrations/twitter/cookies",
        json={"auth_token": "abc", "ct0": "xyz"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "connected"
    assert body["data"]["checked_at"] is not None

    await db.refresh(test_user)
    assert test_user.twitter_bird_auth_token == "abc"
    assert test_user.twitter_bird_ct0 == "xyz"
    assert test_user.twitter_bird_status == "connected"


@pytest.mark.asyncio
async def test_post_cookies_sets_status_expired_when_whoami_fails(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch,
):
    async def _fake_verify(a, c):
        return False

    monkeypatch.setattr("app.api.twitter_cookies.verify_cookies", _fake_verify)

    resp = await client.post(
        "/api/v1/integrations/twitter/cookies",
        json={"auth_token": "bad", "ct0": "bad"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "expired"


@pytest.mark.asyncio
async def test_delete_cookies_clears_state(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: object,
    test_user: User,
):
    test_user.twitter_bird_auth_token = "abc"
    test_user.twitter_bird_ct0 = "xyz"
    test_user.twitter_bird_status = "connected"
    await db.commit()

    resp = await client.delete(
        "/api/v1/integrations/twitter/cookies",
        headers=auth_headers,
    )
    assert resp.status_code == 200

    await db.refresh(test_user)
    assert test_user.twitter_bird_auth_token is None
    assert test_user.twitter_bird_ct0 is None
    assert test_user.twitter_bird_status == "disconnected"


@pytest.mark.asyncio
async def test_get_status_returns_current_state(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: object,
    test_user: User,
):
    test_user.twitter_bird_status = "expired"
    await db.commit()

    resp = await client.get(
        "/api/v1/integrations/twitter/cookies",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "expired"


@pytest.mark.asyncio
async def test_post_cookies_rejects_empty_tokens(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/integrations/twitter/cookies",
        json={"auth_token": "", "ct0": "xyz"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
