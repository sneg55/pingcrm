"""Tests for Twitter bird CLI sync functions.

Covers:
- sync_twitter_mentions: notification on bird unavailable, cursor persistence
- sync_twitter_replies: notification on bird unavailable
- No OAuth (httpx) calls when using bird CLI
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User


# ---------------------------------------------------------------------------
# Task 4.2: sync_twitter_mentions — notification on bird unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_mentions_creates_notification_on_bird_unavailable(db: AsyncSession, test_user: User):
    """When bird CLI is not available, sync_twitter_mentions creates a notification and returns 0."""
    test_user.twitter_username = "testuser"
    await db.commit()

    with patch("app.integrations.bird.is_available", return_value=False):
        from app.integrations.twitter import sync_twitter_mentions
        result = await sync_twitter_mentions(test_user, db)

    assert result == 0

    notifs_result = await db.execute(
        select(Notification).where(Notification.user_id == test_user.id)
    )
    notif = notifs_result.scalars().first()
    assert notif is not None
    assert "unavailable" in notif.title.lower()


@pytest.mark.asyncio
async def test_sync_mentions_notification_links_to_settings(db: AsyncSession, test_user: User):
    """Notification created when bird unavailable should link to /settings."""
    test_user.twitter_username = "testuser"
    await db.commit()

    with patch("app.integrations.bird.is_available", return_value=False):
        from app.integrations.twitter import sync_twitter_mentions
        await sync_twitter_mentions(test_user, db)

    notifs_result = await db.execute(
        select(Notification).where(Notification.user_id == test_user.id)
    )
    notif = notifs_result.scalars().first()
    assert notif is not None
    assert notif.link == "/settings"


@pytest.mark.asyncio
async def test_sync_mentions_no_username_returns_zero(db: AsyncSession, test_user: User):
    """sync_twitter_mentions returns 0 immediately when twitter_username is not set."""
    test_user.twitter_username = None
    await db.commit()

    from app.integrations.twitter import sync_twitter_mentions
    result = await sync_twitter_mentions(test_user, db)

    assert result == 0


# ---------------------------------------------------------------------------
# Task 4.3: sync_twitter_replies — notification on bird unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_replies_creates_notification_on_bird_unavailable(db: AsyncSession, test_user: User):
    """When bird CLI is not available, sync_twitter_replies creates a notification and returns 0."""
    test_user.twitter_username = "testuser"
    await db.commit()

    with patch("app.integrations.bird.is_available", return_value=False):
        from app.integrations.twitter import sync_twitter_replies
        result = await sync_twitter_replies(test_user, db)

    assert result == 0

    notifs_result = await db.execute(
        select(Notification).where(Notification.user_id == test_user.id)
    )
    notif = notifs_result.scalars().first()
    assert notif is not None
    assert "unavailable" in notif.title.lower()


@pytest.mark.asyncio
async def test_sync_replies_notification_links_to_settings(db: AsyncSession, test_user: User):
    """Notification created when bird unavailable should link to /settings."""
    test_user.twitter_username = "testuser"
    await db.commit()

    with patch("app.integrations.bird.is_available", return_value=False):
        from app.integrations.twitter import sync_twitter_replies
        await sync_twitter_replies(test_user, db)

    notifs_result = await db.execute(
        select(Notification).where(Notification.user_id == test_user.id)
    )
    notif = notifs_result.scalars().first()
    assert notif is not None
    assert notif.link == "/settings"


@pytest.mark.asyncio
async def test_sync_replies_no_username_returns_zero(db: AsyncSession, test_user: User):
    """sync_twitter_replies returns 0 immediately when twitter_username is not set."""
    test_user.twitter_username = None
    await db.commit()

    from app.integrations.twitter import sync_twitter_replies
    result = await sync_twitter_replies(test_user, db)

    assert result == 0


# ---------------------------------------------------------------------------
# Task 4.4: cursor persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mention_cursor_saved_after_sync(db: AsyncSession, test_user: User):
    """After a successful sync, the newest mention ID is saved to sync_settings."""
    test_user.twitter_username = "testuser"
    test_user.sync_settings = {}
    test_user.twitter_bird_auth_token = "tok"
    test_user.twitter_bird_ct0 = "ct0"
    await db.commit()

    mock_mentions = [
        {"id": "200", "author_id": "555", "text": "hey", "created_at": "2026-03-24T10:00:00Z"},
        {"id": "100", "author_id": "555", "text": "older", "created_at": "2026-03-24T09:00:00Z"},
    ]

    with (
        patch("app.integrations.bird.is_available", return_value=True),
        patch(
            "app.integrations.bird.fetch_mentions_bird",
            new_callable=AsyncMock,
            return_value=(mock_mentions, None),
        ),
        patch(
            "app.integrations.twitter._build_twitter_id_to_contact_map",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "app.integrations.twitter._user_bearer_headers",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        from app.integrations.twitter import sync_twitter_mentions
        await sync_twitter_mentions(test_user, db)

    await db.refresh(test_user)
    assert test_user.sync_settings is not None
    assert test_user.sync_settings.get("twitter_mention_cursor") == "200"


@pytest.mark.asyncio
async def test_reply_cursor_saved_after_sync(db: AsyncSession, test_user: User):
    """After a successful sync, the newest reply ID is saved to sync_settings."""
    test_user.twitter_username = "testuser"
    test_user.sync_settings = {}
    await db.commit()

    mock_replies = [
        {"id": "300", "text": "@friend hello", "created_at": "2026-03-24T12:00:00Z", "in_reply_to_user_id": "888"},
        {"id": "150", "text": "@friend earlier", "created_at": "2026-03-24T08:00:00Z", "in_reply_to_user_id": "888"},
    ]

    with (
        patch("app.integrations.bird.is_available", return_value=True),
        patch(
            "app.integrations.bird.fetch_user_replies_bird",
            new_callable=AsyncMock,
            return_value=mock_replies,
        ),
        patch(
            "app.integrations.twitter._build_twitter_id_to_contact_map",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "app.integrations.twitter._user_bearer_headers",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        from app.integrations.twitter import sync_twitter_replies
        await sync_twitter_replies(test_user, db)

    await db.refresh(test_user)
    assert test_user.sync_settings is not None
    assert test_user.sync_settings.get("twitter_reply_cursor") == "300"


@pytest.mark.asyncio
async def test_mention_cursor_not_saved_when_no_mentions(db: AsyncSession, test_user: User):
    """When bird returns no mentions, the cursor is not written."""
    test_user.twitter_username = "testuser"
    test_user.sync_settings = {}
    test_user.twitter_bird_auth_token = "tok"
    test_user.twitter_bird_ct0 = "ct0"
    await db.commit()

    with (
        patch("app.integrations.bird.is_available", return_value=True),
        patch(
            "app.integrations.bird.fetch_mentions_bird",
            new_callable=AsyncMock,
            return_value=([], None),
        ),
    ):
        from app.integrations.twitter import sync_twitter_mentions
        result = await sync_twitter_mentions(test_user, db)

    await db.refresh(test_user)
    assert result == 0
    assert test_user.sync_settings.get("twitter_mention_cursor") is None


# ---------------------------------------------------------------------------
# Task 4.5: no OAuth calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mentions_sync_makes_no_oauth_calls(db: AsyncSession, test_user: User):
    """sync_twitter_mentions should NOT instantiate httpx.AsyncClient for OAuth API calls."""
    test_user.twitter_username = "testuser"
    test_user.twitter_bird_auth_token = "tok"
    test_user.twitter_bird_ct0 = "ct0"
    await db.commit()

    with (
        patch("app.integrations.bird.is_available", return_value=True),
        patch(
            "app.integrations.bird.fetch_mentions_bird",
            new_callable=AsyncMock,
            return_value=([], None),
        ),
        patch("httpx.AsyncClient") as mock_httpx,
    ):
        from app.integrations.twitter import sync_twitter_mentions
        await sync_twitter_mentions(test_user, db)

    mock_httpx.assert_not_called()


@pytest.mark.asyncio
async def test_replies_sync_makes_no_oauth_calls(db: AsyncSession, test_user: User):
    """sync_twitter_replies should NOT instantiate httpx.AsyncClient for OAuth API calls."""
    test_user.twitter_username = "testuser"
    await db.commit()

    with (
        patch("app.integrations.bird.is_available", return_value=True),
        patch(
            "app.integrations.bird.fetch_user_replies_bird",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("httpx.AsyncClient") as mock_httpx,
    ):
        from app.integrations.twitter import sync_twitter_replies
        await sync_twitter_replies(test_user, db)

    mock_httpx.assert_not_called()


# ---------------------------------------------------------------------------
# Task 5: per-user cookies + expiry detection for mention sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mention_sync_flips_status_when_whoami_fails(db_session, user_factory, monkeypatch):
    """When bird mention call fails AND whoami also fails, status flips to expired + 1 notification."""
    from app.integrations.twitter import sync_twitter_mentions
    from app.services import bird_session

    user = await user_factory(
        twitter_username="alice",
        twitter_user_id="123",
        twitter_bird_auth_token="bad",
        twitter_bird_ct0="bad",
        twitter_bird_status="connected",
    )
    bird_session.reset_verification_cache()

    async def _fake_fetch(handle, count=50, *, auth_token, ct0):
        return [], "bird mentions: exit code 1: unauthorized"

    async def _fake_verify(auth_token, ct0):
        return False

    monkeypatch.setattr("app.integrations.bird.fetch_mentions_bird", _fake_fetch)
    monkeypatch.setattr("app.services.bird_session.verify_cookies", _fake_verify)
    monkeypatch.setattr("app.integrations.bird.is_available", lambda: True)

    await sync_twitter_mentions(user, db_session)

    await db_session.refresh(user)
    assert user.twitter_bird_status == "expired"

    from app.models.notification import Notification
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(Notification).where(Notification.user_id == user.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "X cookies expired"


@pytest.mark.asyncio
async def test_mention_sync_transient_failure_leaves_status_connected(
    db_session, user_factory, monkeypatch,
):
    """When bird fails but whoami succeeds → transient, no status change, no notification."""
    from app.integrations.twitter import sync_twitter_mentions
    from app.services import bird_session

    user = await user_factory(
        twitter_username="alice",
        twitter_user_id="123",
        twitter_bird_auth_token="good",
        twitter_bird_ct0="good",
        twitter_bird_status="connected",
    )
    bird_session.reset_verification_cache()

    async def _fake_fetch(handle, count=50, *, auth_token, ct0):
        return [], "bird mentions: timed out after 20s"

    async def _fake_verify(auth_token, ct0):
        return True

    monkeypatch.setattr("app.integrations.bird.fetch_mentions_bird", _fake_fetch)
    monkeypatch.setattr("app.services.bird_session.verify_cookies", _fake_verify)
    monkeypatch.setattr("app.integrations.bird.is_available", lambda: True)

    await sync_twitter_mentions(user, db_session)

    await db_session.refresh(user)
    assert user.twitter_bird_status == "connected"

    from app.models.notification import Notification
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(Notification).where(Notification.user_id == user.id)
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_mention_sync_skips_when_cookies_missing(
    db_session, user_factory, monkeypatch,
):
    from app.integrations.twitter import sync_twitter_mentions

    user = await user_factory(
        twitter_username="alice",
        twitter_user_id="123",
        twitter_bird_auth_token=None,
        twitter_bird_ct0=None,
        twitter_bird_status="disconnected",
    )

    called = {"n": 0}
    async def _fake_fetch(*a, **kw):
        called["n"] += 1
        return [], None

    monkeypatch.setattr("app.integrations.bird.fetch_mentions_bird", _fake_fetch)
    monkeypatch.setattr("app.integrations.bird.is_available", lambda: True)

    result = await sync_twitter_mentions(user, db_session)

    assert result == 0
    assert called["n"] == 0
