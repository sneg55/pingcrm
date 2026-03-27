"""Tests for the Twitter DM sync flow (fetch + sync integration).

Covers:
- fetch_dm_conversations: stale cursor retry, 400 without cursor
- sync_twitter_dms: interaction creation, dedup, cursor update,
  last_interaction_at update, auto-creation of unknown contacts,
  and 401 propagation from /users/me.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_body: dict, *, url: str = "https://api.twitter.com/2/dm_events") -> httpx.Response:
    """Build a fake httpx.Response with the given status and JSON body."""
    request = httpx.Request("GET", url)
    resp = httpx.Response(status_code, json=json_body, request=request)
    return resp


def _dm_event(event_id: str, sender_id: str, text: str, convo_id: str = "") -> dict:
    """Build a single DM event dict matching the Twitter API v2 shape."""
    return {
        "id": event_id,
        "sender_id": sender_id,
        "text": text,
        "created_at": "2025-06-15T10:00:00.000Z",
        "dm_conversation_id": convo_id,
        "participant_ids": [],
    }


# ---------------------------------------------------------------------------
# fetch_dm_conversations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_dm_stale_cursor_retries_without_since_id():
    """When fetch_dm_conversations gets 400 with since_id, it retries without since_id."""
    from app.integrations.twitter import fetch_dm_conversations

    call_count = 0

    async def _mock_get(url, *, headers=None, params=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call with since_id => 400
            assert "since_id" in params
            return _make_response(400, {"detail": "Invalid since_id"})
        else:
            # Retry without since_id => success
            assert "since_id" not in params
            return _make_response(200, {
                "data": [_dm_event("100", "sender1", "hello")],
                "meta": {},
            })

    mock_client = AsyncMock()
    mock_client.get = _mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        events = await fetch_dm_conversations(
            {"Authorization": "Bearer tok"},
            since_id="stale_cursor_999",
        )

    assert len(events) == 1
    assert events[0]["id"] == "100"
    assert call_count == 2


@pytest.mark.asyncio
async def test_fetch_dm_400_without_cursor_raises():
    """400 without since_id still raises HTTPStatusError."""
    from app.integrations.twitter import fetch_dm_conversations

    async def _mock_get(url, *, headers=None, params=None, **kwargs):
        return _make_response(400, {"detail": "Bad request"})

    mock_client = AsyncMock()
    mock_client.get = _mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_dm_conversations({"Authorization": "Bearer tok"})


# ---------------------------------------------------------------------------
# sync_twitter_dms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_twitter_dms_creates_interactions(db: AsyncSession, test_user: User, test_contact: Contact):
    """Basic flow: mock fetch returns 2 events, verify 2 Interaction records with correct direction/platform."""
    # Setup: link contact to a Twitter user ID
    test_contact.twitter_handle = "johndoe"
    test_contact.twitter_user_id = "tw_contact_1"
    test_user.twitter_user_id = "tw_me_123"
    test_user.twitter_access_token = "tok"
    await db.flush()

    events = [
        _dm_event("ev1", "tw_contact_1", "Hi there!", f"tw_contact_1-tw_me_123"),
        _dm_event("ev2", "tw_me_123", "Hello back!", f"tw_contact_1-tw_me_123"),
    ]

    id_map = {test_contact.twitter_user_id: test_contact}

    with patch("app.integrations.twitter.fetch_dm_conversations", new=AsyncMock(return_value=events)):
        from app.integrations.twitter import sync_twitter_dms
        result = await sync_twitter_dms(
            test_user, db,
            _id_map=id_map,
            _headers={"Authorization": "Bearer tok"},
        )

    assert result["new_interactions"] == 2

    interactions = (await db.execute(
        select(Interaction).where(Interaction.user_id == test_user.id)
    )).scalars().all()
    assert len(interactions) == 2

    directions = {i.direction for i in interactions}
    assert directions == {"inbound", "outbound"}

    for i in interactions:
        assert i.platform == "twitter"
        assert i.contact_id == test_contact.id


@pytest.mark.asyncio
async def test_sync_twitter_dms_dedup_skips_existing(db: AsyncSession, test_user: User, test_contact: Contact):
    """Events with existing raw_reference_id are skipped."""
    test_contact.twitter_handle = "johndoe"
    test_contact.twitter_user_id = "tw_contact_1"
    test_user.twitter_user_id = "tw_me_123"
    test_user.twitter_access_token = "tok"

    # Pre-create an interaction with the same ref ID
    existing = Interaction(
        contact_id=test_contact.id,
        user_id=test_user.id,
        platform="twitter",
        direction="inbound",
        content_preview="Already synced",
        raw_reference_id="twitter_dm:ev1",
        occurred_at=datetime.now(UTC),
    )
    db.add(existing)
    await db.flush()

    events = [
        _dm_event("ev1", "tw_contact_1", "Hi there!", f"tw_contact_1-tw_me_123"),
        _dm_event("ev2", "tw_contact_1", "Another msg", f"tw_contact_1-tw_me_123"),
    ]

    id_map = {test_contact.twitter_user_id: test_contact}

    with patch("app.integrations.twitter.fetch_dm_conversations", new=AsyncMock(return_value=events)):
        from app.integrations.twitter import sync_twitter_dms
        result = await sync_twitter_dms(
            test_user, db,
            _id_map=id_map,
            _headers={"Authorization": "Bearer tok"},
        )

    assert result["new_interactions"] == 1  # Only ev2 is new

    interactions = (await db.execute(
        select(Interaction).where(Interaction.user_id == test_user.id)
    )).scalars().all()
    assert len(interactions) == 2  # 1 pre-existing + 1 new


@pytest.mark.asyncio
async def test_sync_twitter_dms_updates_cursor(db: AsyncSession, test_user: User, test_contact: Contact):
    """After sync, user.twitter_dm_cursor is set to newest event ID."""
    test_contact.twitter_handle = "johndoe"
    test_contact.twitter_user_id = "tw_contact_1"
    test_user.twitter_user_id = "tw_me_123"
    test_user.twitter_access_token = "tok"
    test_user.twitter_dm_cursor = None
    await db.flush()

    events = [
        _dm_event("200", "tw_contact_1", "msg1", f"tw_contact_1-tw_me_123"),
        _dm_event("300", "tw_contact_1", "msg2", f"tw_contact_1-tw_me_123"),
        _dm_event("100", "tw_contact_1", "msg3", f"tw_contact_1-tw_me_123"),
    ]

    id_map = {test_contact.twitter_user_id: test_contact}

    with patch("app.integrations.twitter.fetch_dm_conversations", new=AsyncMock(return_value=events)):
        from app.integrations.twitter import sync_twitter_dms
        await sync_twitter_dms(
            test_user, db,
            _id_map=id_map,
            _headers={"Authorization": "Bearer tok"},
        )

    # Cursor should be max event ID (lexicographic comparison)
    assert test_user.twitter_dm_cursor == "300"


@pytest.mark.asyncio
async def test_sync_twitter_dms_updates_last_interaction_at(db: AsyncSession, test_user: User, test_contact: Contact):
    """Contact's last_interaction_at is updated after DM sync."""
    test_contact.twitter_handle = "johndoe"
    test_contact.twitter_user_id = "tw_contact_1"
    test_contact.last_interaction_at = datetime(2024, 1, 1, tzinfo=UTC)
    test_user.twitter_user_id = "tw_me_123"
    test_user.twitter_access_token = "tok"
    await db.flush()

    events = [
        _dm_event("ev1", "tw_contact_1", "Hello!", f"tw_contact_1-tw_me_123"),
    ]

    id_map = {test_contact.twitter_user_id: test_contact}

    with patch("app.integrations.twitter.fetch_dm_conversations", new=AsyncMock(return_value=events)):
        from app.integrations.twitter import sync_twitter_dms
        await sync_twitter_dms(
            test_user, db,
            _id_map=id_map,
            _headers={"Authorization": "Bearer tok"},
        )

    # last_interaction_at should be updated to the event timestamp (2025-06-15)
    assert test_contact.last_interaction_at is not None
    assert test_contact.last_interaction_at > datetime(2024, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_sync_twitter_dms_autocreates_contact(db: AsyncSession, test_user: User):
    """Unknown DM participant creates a new Contact via auto-create."""
    test_user.twitter_user_id = "tw_me_123"
    test_user.twitter_access_token = "tok"
    await db.flush()

    events = [
        _dm_event("ev1", "tw_unknown_999", "Hey!", f"tw_unknown_999-tw_me_123"),
    ]

    # Empty id_map => no contacts mapped
    id_map: dict[str, Contact] = {}

    # Mock the user lookup to return profile data for the unknown participant
    with (
        patch("app.integrations.twitter.fetch_dm_conversations", new=AsyncMock(return_value=events)),
        patch("app.integrations.twitter._lookup_twitter_users_by_ids", new=AsyncMock(return_value={
            "tw_unknown_999": {"username": "newuser", "name": "New User"},
        })),
    ):
        from app.integrations.twitter import sync_twitter_dms
        result = await sync_twitter_dms(
            test_user, db,
            _id_map=id_map,
            _headers={"Authorization": "Bearer tok"},
        )

    assert result["new_contacts"] == 1
    assert result["new_interactions"] == 1

    # Verify the contact was created in the DB
    contacts = (await db.execute(
        select(Contact).where(
            Contact.user_id == test_user.id,
            Contact.twitter_user_id == "tw_unknown_999",
        )
    )).scalars().all()
    assert len(contacts) == 1
    assert contacts[0].twitter_handle == "newuser"
    assert contacts[0].full_name == "New User"
    assert contacts[0].source == "twitter"


@pytest.mark.asyncio
async def test_sync_twitter_dms_users_me_401_propagates(db: AsyncSession, test_user: User):
    """When /users/me returns 401, HTTPStatusError is raised (not silently caught)."""
    test_user.twitter_user_id = None  # Force /users/me call
    test_user.twitter_access_token = "expired_token"
    await db.flush()

    resp_401 = _make_response(401, {"detail": "Unauthorized"}, url="https://api.twitter.com/2/users/me")

    async def _mock_get(url, *, headers=None, params=None, **kwargs):
        return resp_401

    mock_client = AsyncMock()
    mock_client.get = _mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        from app.integrations.twitter import sync_twitter_dms
        with pytest.raises(httpx.HTTPStatusError):
            await sync_twitter_dms(
                test_user, db,
                _headers={"Authorization": "Bearer expired_token"},
            )
