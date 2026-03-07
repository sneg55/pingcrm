"""Tests for Google OAuth callback in auth API."""
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_google_url_returns_oauth_url(client: AsyncClient, auth_headers: dict):
    """GET /auth/google/url returns an authorization URL when credentials are configured."""
    with patch("app.api.auth.settings") as mock_settings, \
         patch("app.api.auth.build_oauth_url", return_value=("https://accounts.google.com/o/oauth2/auth?mock=1", "state123")):
        mock_settings.GOOGLE_CLIENT_ID = "test-client-id"
        mock_settings.GOOGLE_CLIENT_SECRET = "test-client-secret"
        mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1440
        resp = await client.get("/api/v1/auth/google/url", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "url" in data
    assert data["url"].startswith("https://accounts.google.com")
    assert "state" in data


@pytest.mark.asyncio
async def test_google_url_without_credentials(client: AsyncClient, auth_headers: dict):
    """GET /auth/google/url returns 400 when GOOGLE_CLIENT_ID is not set."""
    with patch("app.api.auth.settings") as mock_settings:
        mock_settings.GOOGLE_CLIENT_ID = ""
        mock_settings.GOOGLE_CLIENT_SECRET = ""
        resp = await client.get("/api/v1/auth/google/url", headers=auth_headers)
    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_url_requires_auth(client: AsyncClient):
    """GET /auth/google/url returns 401 without auth headers."""
    resp = await client.get("/api/v1/auth/google/url")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_callback_exchange_fails(client: AsyncClient):
    """POST /auth/google/callback returns 400 when code exchange fails."""
    with patch("app.api.auth.exchange_code", side_effect=RuntimeError("bad code")):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "bad-code"},
        )
    assert resp.status_code == 400
    assert "Failed to exchange" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_callback_invalid_id_token(client: AsyncClient):
    """POST /auth/google/callback returns 400 when id_token verification fails."""
    mock_tokens = {"id_token": "fake", "refresh_token": "ref"}
    with patch("app.api.auth.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth.google_id_token.verify_oauth2_token", side_effect=ValueError("bad token")):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code"},
        )
    assert resp.status_code == 400
    assert "Invalid Google ID token" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_callback_no_email(client: AsyncClient):
    """POST /auth/google/callback returns 400 when id_token has no email."""
    mock_tokens = {"id_token": "fake", "refresh_token": "ref"}
    with patch("app.api.auth.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth.google_id_token.verify_oauth2_token", return_value={"sub": "123"}):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code"},
        )
    assert resp.status_code == 400
    assert "does not provide an email" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_callback_new_user(client: AsyncClient):
    """POST /auth/google/callback creates a new user when email not found."""
    mock_tokens = {"id_token": "fake", "refresh_token": "ref"}
    id_info = {"email": "google@example.com", "name": "Google User", "sub": "123"}
    with patch("app.api.auth.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth.google_id_token.verify_oauth2_token", return_value=id_info):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code"},
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_google_callback_existing_user(client: AsyncClient):
    """POST /auth/google/callback logs in existing user and updates refresh token."""
    # First create the user via register
    await client.post("/api/v1/auth/register", json={
        "email": "existing@example.com",
        "password": "securepass123",
    })

    mock_tokens = {"id_token": "fake", "refresh_token": "new_refresh"}
    id_info = {"email": "existing@example.com", "name": "Existing", "sub": "456"}
    with patch("app.api.auth.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth.google_id_token.verify_oauth2_token", return_value=id_info):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code"},
        )
    assert resp.status_code == 200
    assert "access_token" in resp.json()["data"]
