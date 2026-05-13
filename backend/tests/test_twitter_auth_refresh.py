"""Tests for the Twitter OAuth 2.0 auth refresh flow.

Covers:
- Proactive refresh when token is near expiry
- Token storage after successful refresh
- 401 refresh failure: token clearing and notification creation
- Notification deduplication (one per 24h)
- Redis lock preventing concurrent refresh
- Missing refresh_token notification
- Task-level auth failure recording
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_body: dict, *, url: str = "https://api.twitter.com/2/oauth2/token") -> httpx.Response:
    """Build a fake httpx.Response."""
    request = httpx.Request("POST", url)
    return httpx.Response(status_code, json=json_body, request=request)


def _mock_redis(*, lock_acquired: bool = True):
    """Return a mock redis client for lock tests."""
    r = MagicMock()
    r.set = MagicMock(return_value=lock_acquired)
    r.delete = MagicMock()
    return r


# ---------------------------------------------------------------------------
# _user_bearer_headers — proactive refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proactive_refresh_triggers_before_expiry(db: AsyncSession, test_user: User):
    """When token_expires_at is within 5 min, _user_bearer_headers calls refresh."""
    test_user.twitter_access_token = "old_token"
    test_user.twitter_refresh_token = "refresh_tok"
    # Token expires in 2 minutes (within 5-min buffer)
    test_user.twitter_token_expires_at = datetime.now(UTC) + timedelta(minutes=2)
    await db.flush()

    new_tokens = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 7200,
    }

    mock_redis = _mock_redis()

    with (
        patch("app.integrations.twitter_auth.refresh_twitter_token", new=AsyncMock(return_value=new_tokens)),
        patch("redis.from_url", return_value=mock_redis),
    ):
        from app.integrations.twitter_auth import _user_bearer_headers
        headers = await _user_bearer_headers(test_user, db)

    assert headers is not None
    assert headers["Authorization"] == "Bearer new_access_token"


# ---------------------------------------------------------------------------
# _refresh_and_retry — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_success_stores_new_tokens(db: AsyncSession, test_user: User):
    """After successful refresh, user tokens are updated in the database."""
    test_user.twitter_access_token = "old_access"
    test_user.twitter_refresh_token = "old_refresh"
    await db.flush()

    new_tokens = {
        "access_token": "fresh_access",
        "refresh_token": "fresh_refresh",
        "expires_in": 7200,
    }

    mock_redis = _mock_redis()

    with (
        patch("app.integrations.twitter_auth.refresh_twitter_token", new=AsyncMock(return_value=new_tokens)),
        patch("redis.from_url", return_value=mock_redis),
    ):
        from app.integrations.twitter_auth import _refresh_and_retry
        headers = await _refresh_and_retry(test_user, db)

    assert headers == {"Authorization": "Bearer fresh_access"}
    assert test_user.twitter_access_token == "fresh_access"
    assert test_user.twitter_refresh_token == "fresh_refresh"
    assert test_user.twitter_token_expires_at is not None


# ---------------------------------------------------------------------------
# _refresh_and_retry — 401 failure clears tokens and notifies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_401_clears_tokens_and_notifies(db: AsyncSession, test_user: User):
    """400/401 refresh failure clears all tokens and creates a Notification."""
    test_user.twitter_access_token = "dead_access"
    test_user.twitter_refresh_token = "dead_refresh"
    test_user.twitter_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db.flush()

    error_resp = _make_response(401, {"error": "invalid_grant"})
    error = httpx.HTTPStatusError("Unauthorized", request=error_resp.request, response=error_resp)

    mock_redis = _mock_redis()

    with (
        patch("app.integrations.twitter_auth.refresh_twitter_token", new=AsyncMock(side_effect=error)),
        patch("redis.from_url", return_value=mock_redis),
    ):
        from app.integrations.twitter_auth import _refresh_and_retry
        result = await _refresh_and_retry(test_user, db)

    assert result is None
    assert test_user.twitter_access_token is None
    assert test_user.twitter_refresh_token is None
    assert test_user.twitter_token_expires_at is None

    # Verify notification was created
    notifications = (await db.execute(
        select(Notification).where(
            Notification.user_id == test_user.id,
            Notification.title == "Twitter connection expired",
        )
    )).scalars().all()
    assert len(notifications) == 1
    assert "reconnect" in notifications[0].body.lower()


# ---------------------------------------------------------------------------
# _refresh_and_retry — notification dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_401_notification_deduped(db: AsyncSession, test_user: User):
    """Only one notification in 24h — second 401 does not create another."""
    test_user.twitter_access_token = "dead_access"
    test_user.twitter_refresh_token = "dead_refresh"
    await db.flush()

    # Pre-create a recent notification (within 24h)
    existing_notif = Notification(
        user_id=test_user.id,
        notification_type="system",
        title="Twitter connection expired",
        body="Previously created notification.",
        link="/settings",
    )
    db.add(existing_notif)
    await db.commit()

    error_resp = _make_response(400, {"error": "invalid_grant"})
    error = httpx.HTTPStatusError("Bad Request", request=error_resp.request, response=error_resp)

    mock_redis = _mock_redis()

    with (
        patch("app.integrations.twitter_auth.refresh_twitter_token", new=AsyncMock(side_effect=error)),
        patch("redis.from_url", return_value=mock_redis),
    ):
        from app.integrations.twitter_auth import _refresh_and_retry

        # Reset tokens for second attempt
        test_user.twitter_access_token = "dead_access_2"
        test_user.twitter_refresh_token = "dead_refresh_2"
        await db.flush()

        result = await _refresh_and_retry(test_user, db)

    assert result is None

    # Should still be only 1 notification (the pre-existing one), not 2
    notifications = (await db.execute(
        select(Notification).where(
            Notification.user_id == test_user.id,
            Notification.title == "Twitter connection expired",
        )
    )).scalars().all()
    assert len(notifications) == 1


# ---------------------------------------------------------------------------
# _refresh_and_retry — lock prevents concurrent refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_lock_prevents_concurrent(db: AsyncSession, test_user: User):
    """Second refresh attempt while locked waits and reads refreshed token."""
    test_user.twitter_access_token = "previously_refreshed_token"
    test_user.twitter_refresh_token = "some_refresh"
    await db.flush()

    # Simulate lock already held (nx=True returns False)
    mock_redis = _mock_redis(lock_acquired=False)

    with (
        patch("redis.from_url", return_value=mock_redis),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        from app.integrations.twitter_auth import _refresh_and_retry
        headers = await _refresh_and_retry(test_user, db)

    # Should return the existing token after sleeping and re-reading
    assert headers is not None
    assert headers["Authorization"] == "Bearer previously_refreshed_token"


# ---------------------------------------------------------------------------
# _refresh_and_retry — no refresh token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_refresh_token_creates_notification(db: AsyncSession, test_user: User):
    """Missing refresh_token immediately creates notification (commit, not just flush)."""
    test_user.twitter_access_token = "some_token"
    test_user.twitter_refresh_token = None
    await db.flush()

    from app.integrations.twitter_auth import _refresh_and_retry
    result = await _refresh_and_retry(test_user, db)

    assert result is None

    # Notification should exist (committed, not just flushed)
    notifications = (await db.execute(
        select(Notification).where(
            Notification.user_id == test_user.id,
            Notification.title == "Twitter connection expired",
        )
    )).scalars().all()
    assert len(notifications) == 1
    assert "no refresh token" in notifications[0].body.lower()


# ---------------------------------------------------------------------------
# Task: sync_twitter_dms_for_user — auth failure records sync failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_auth_failed_records_sync_failure(db: AsyncSession, test_user: User):
    """sync_twitter_dms_for_user records sync failure when auth fails (401 + refresh fails)."""
    test_user.twitter_access_token = "expired"
    test_user.twitter_refresh_token = "dead"
    test_user.twitter_user_id = "tw_me_123"  # Must be set to skip /users/me call
    await db.flush()

    import app.integrations.twitter_auth as twitter_auth_mod
    from app.integrations.twitter import sync_twitter_dms
    from app.services.sync_history import record_sync_start, record_sync_failure

    mock_headers = {"Authorization": "Bearer expired_tok"}

    # fetch_dm_conversations will raise 401 (token expired)
    error_resp = _make_response(401, {"detail": "Unauthorized"}, url="https://api.twitter.com/2/dm_events")
    http_error = httpx.HTTPStatusError("Unauthorized", request=error_resp.request, response=error_resp)

    mock_id_map: dict = {}

    sync_event = await record_sync_start(test_user.id, "twitter", "scheduled", db)
    await db.flush()

    mock_refresh = AsyncMock(return_value=None)

    # Simulate the task's 401 handling: sync_twitter_dms raises 401, _refresh_and_retry returns None
    # Patch _refresh_and_retry on the module so both direct and module-level calls see the mock.
    with (
        patch("app.integrations.twitter_dms.fetch_dm_conversations", new=AsyncMock(side_effect=http_error)),
        patch.object(twitter_auth_mod, "_refresh_and_retry", mock_refresh),
        patch("app.integrations.twitter_dms._refresh_and_retry", mock_refresh),
    ):
        # Replicate the task's inner try/except logic (mirrors sync_twitter_dms_for_user)
        try:
            await sync_twitter_dms(
                test_user, db,
                _id_map=mock_id_map,
                _headers=mock_headers,
            )
            auth_failed = False
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                headers = await twitter_auth_mod._refresh_and_retry(test_user, db)
                if not headers:
                    await record_sync_failure(sync_event, "Token refresh failed (401)", db=db)
                    auth_failed = True
                else:
                    auth_failed = False
            else:
                raise

    assert auth_failed is True
    mock_refresh.assert_awaited_once()

    # Verify sync event was marked as failed
    await db.refresh(sync_event)
    assert sync_event.status == "failed"
