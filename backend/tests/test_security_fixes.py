"""Tests for security fixes: Task 8.1, 8.3, 8.5."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.models.user import User


# ---------------------------------------------------------------------------
# Shared Redis patch for Google OAuth state tests
# ---------------------------------------------------------------------------

_fake_redis_instance = None


@pytest.fixture(autouse=True)
def _patch_google_redis():
    """Patch get_redis to use fakeredis for all tests in this module."""
    global _fake_redis_instance
    fr = fakeredis.aioredis.FakeRedis(decode_responses=True)
    _fake_redis_instance = fr
    with patch("app.core.redis.get_redis", return_value=fr), \
         patch("app.api.auth_google.get_redis", return_value=fr), \
         patch("app.api.twitter.get_redis", return_value=fr):
        yield fr
    _fake_redis_instance = None


async def _inject_google_state(state: str, user_id: str | None) -> str:
    """Store a Google OAuth state in the fake Redis."""
    from app.api.auth_google import _store_google_state
    await _store_google_state(state, user_id)
    return state


# ===========================================================================
# Task 8.1: Google OAuth State Enforcement
# ===========================================================================


@pytest.mark.asyncio
async def test_google_callback_anonymous_state_is_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    state = await _inject_google_state("anon-state-001", None)

    mock_tokens = {"id_token": "fake_token", "refresh_token": "refresh_123"}
    id_info = {"email": "newuser@example.com", "name": "New User", "sub": "g-001"}

    with patch("app.api.auth_google.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth_google.google_id_token.verify_oauth2_token", return_value=id_info):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "auth-code", "state": state},
            headers=auth_headers,
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_google_callback_user_state_with_matching_user_succeeds(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """State bound to current user is accepted in connect-account flow."""
    state = await _inject_google_state("user-state-match", str(test_user.id))

    mock_tokens = {"id_token": "fake_token", "refresh_token": "refresh_abc"}
    id_info = {"email": test_user.email, "name": test_user.full_name, "sub": "g-002"}

    with patch("app.api.auth_google.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth_google.google_id_token.verify_oauth2_token", return_value=id_info):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "auth-code", "state": state},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert "access_token" in resp.json()["data"]


@pytest.mark.asyncio
async def test_google_callback_user_state_without_auth_returns_403(
    client: AsyncClient,
    test_user: User,
):
    """State bound to a user is rejected when no Bearer token is provided."""
    state = await _inject_google_state("user-state-no-auth", str(test_user.id))

    resp = await client.post(
        "/api/v1/auth/google/callback",
        json={"code": "auth-code", "state": state},
        # No auth headers
    )

    assert resp.status_code == 403
    assert "does not match the OAuth state" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_callback_user_state_with_different_user_returns_403(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """State bound to user A is rejected when the request is authenticated as user B."""
    from app.core.auth import hash_password

    # Create a second user
    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password=hash_password("pass"),
        full_name="Other User",
    )
    db.add(other_user)
    await db.commit()

    # State is bound to test_user, but request is authenticated as other_user
    state = await _inject_google_state("user-state-mismatch", str(test_user.id))
    other_token = create_access_token(data={"sub": str(other_user.id)})
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = await client.post(
        "/api/v1/auth/google/callback",
        json={"code": "auth-code", "state": state},
        headers=other_headers,
    )

    assert resp.status_code == 403
    assert "does not match the OAuth state" in resp.json()["detail"]


# ===========================================================================
# Task 8.3: Exception Detail Redaction
# ===========================================================================


@pytest.mark.asyncio
async def test_google_callback_exchange_error_does_not_leak_exception_class(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
):
    """auth.py: exchange_code error detail must not contain raw exception class names."""
    state = await _inject_google_state("redact-exchange-state", str(test_user.id))

    with patch("app.api.auth_google.exchange_code", side_effect=ValueError("internal detail here")):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "bad-code", "state": state},
            headers=auth_headers,
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "ValueError" not in detail
    assert "internal detail here" not in detail
    assert "Failed to exchange Google authorization code" in detail


@pytest.mark.asyncio
async def test_google_callback_id_token_error_does_not_leak_exception_class(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
):
    """auth.py: id_token error detail must not contain raw exception class names."""
    state = await _inject_google_state("redact-idtoken-state", str(test_user.id))
    mock_tokens = {"id_token": "fake", "refresh_token": "ref"}

    with patch("app.api.auth_google.exchange_code", return_value=mock_tokens), \
         patch(
             "app.api.auth_google.google_id_token.verify_oauth2_token",
             side_effect=Exception("KeyError: aud"),
         ):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code", "state": state},
            headers=auth_headers,
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "KeyError" not in detail
    assert "aud" not in detail
    assert "Invalid Google ID token" in detail


@pytest.mark.asyncio
async def test_twitter_callback_exchange_error_does_not_leak_exception_class(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
):
    """twitter.py: code exchange error detail must not contain raw exception class names."""
    from app.api.twitter import _store_pkce

    state = "tw-redact-state-001"
    await _store_pkce(state, "verifier", str(test_user.id))

    with patch(
        "app.api.twitter.exchange_twitter_code",
        new=AsyncMock(side_effect=RuntimeError("ConnectionRefusedError: port 443")),
    ):
        resp = await client.post(
            "/api/v1/auth/twitter/callback",
            json={"code": "bad-code", "state": state},
            headers=auth_headers,
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "RuntimeError" not in detail
    assert "ConnectionRefusedError" not in detail
    assert "Failed to exchange Twitter authorization code" in detail


@pytest.mark.asyncio
async def test_telegram_connect_generic_error_does_not_leak_exception_class(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """telegram.py: connect generic error detail must not contain raw exception class names."""
    with patch(
        "app.integrations.telegram.connect_telegram",
        new=AsyncMock(side_effect=RuntimeError("OSError: network unreachable")),
    ):
        resp = await client.post(
            "/api/v1/auth/telegram/connect",
            json={"phone": "+15551234567"},
            headers=auth_headers,
        )

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "RuntimeError" not in detail
    assert "OSError" not in detail
    assert "network unreachable" not in detail


@pytest.mark.asyncio
async def test_telegram_verify_error_does_not_leak_exception_class(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """telegram.py: verify error detail must not contain raw exception class names."""
    with patch(
        "app.integrations.telegram.verify_telegram",
        new=AsyncMock(side_effect=ValueError("PhoneCodeExpiredError: code expired")),
    ):
        resp = await client.post(
            "/api/v1/auth/telegram/verify",
            json={"phone": "+15551234567", "code": "12345", "phone_code_hash": "h"},
            headers=auth_headers,
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "ValueError" not in detail
    assert "PhoneCodeExpiredError" not in detail


# ===========================================================================
# Task 8.5: ENCRYPTION_KEY Startup Validation
# ===========================================================================


def test_encryption_key_empty_in_production_raises_runtime_error():
    """lifespan raises RuntimeError when ENCRYPTION_KEY is empty and ENVIRONMENT=production."""
    import asyncio
    from contextlib import asynccontextmanager

    from app.main import lifespan
    from fastapi import FastAPI

    _app = FastAPI()

    async def _run():
        with patch("app.main.settings") as mock_settings:
            mock_settings.SECRET_KEY = "a-very-long-secret-key-that-passes-the-32-char-minimum-check"
            mock_settings.ENCRYPTION_KEY = ""
            mock_settings.ENVIRONMENT = "production"
            async with lifespan(_app):
                pass

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        asyncio.get_event_loop().run_until_complete(_run())


def test_encryption_key_empty_in_development_logs_warning(caplog):
    """lifespan logs a warning (but does not raise) when ENCRYPTION_KEY is empty in development."""
    import asyncio
    import logging

    from app.main import lifespan
    from fastapi import FastAPI

    _app = FastAPI()

    async def _run():
        with patch("app.main.settings") as mock_settings:
            mock_settings.SECRET_KEY = "a-very-long-secret-key-that-passes-the-32-char-minimum-check"
            mock_settings.ENCRYPTION_KEY = ""
            mock_settings.ENVIRONMENT = "development"
            async with lifespan(_app):
                pass

    with caplog.at_level(logging.WARNING, logger="app.main"):
        asyncio.get_event_loop().run_until_complete(_run())

    assert any("ENCRYPTION_KEY" in r.message for r in caplog.records)


def test_encryption_key_set_does_not_raise():
    """lifespan does not raise when ENCRYPTION_KEY is properly set."""
    import asyncio

    from app.main import lifespan
    from fastapi import FastAPI

    _app = FastAPI()

    async def _run():
        with patch("app.main.settings") as mock_settings:
            mock_settings.SECRET_KEY = "a-very-long-secret-key-that-passes-the-32-char-minimum-check"
            mock_settings.ENCRYPTION_KEY = "HiuobeEdnSk93dMtnycRm8Kob9D3-7-vCw3_L0YG9Ek="
            mock_settings.ENVIRONMENT = "production"
            async with lifespan(_app):
                pass

    # Should not raise
    asyncio.get_event_loop().run_until_complete(_run())
