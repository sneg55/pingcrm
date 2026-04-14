"""Unit tests for the bird CLI adapter functions in app.integrations.bird.

All tests mock _run_bird so no bird CLI binary is required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.bird import BirdResult


# ---------------------------------------------------------------------------
# fetch_mentions_bird
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_mentions_bird_success():
    """bird CLI returns mention tweets → normalized to {id, author_id, text, created_at}."""
    mock_data = [
        {"id": "123", "authorId": "456", "text": "Hey @sawinyh", "createdAt": "2026-03-24T10:00:00Z"},
        {"id": "124", "authorId": "789", "text": "Thanks @sawinyh!", "createdAt": "2026-03-24T11:00:00Z"},
    ]
    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data=mock_data, error=None)):
        from app.integrations.bird import fetch_mentions_bird
        result, err = await fetch_mentions_bird("sawinyh", count=10, auth_token="x", ct0="y")

    assert err is None
    assert len(result) == 2
    assert result[0]["id"] == "123"
    assert result[0]["author_id"] == "456"
    assert result[0]["text"] == "Hey @sawinyh"
    assert result[0]["created_at"] == "2026-03-24T10:00:00Z"
    assert result[1]["id"] == "124"
    assert result[1]["author_id"] == "789"


@pytest.mark.asyncio
async def test_fetch_mentions_bird_empty_on_failure():
    """bird CLI fails → empty list with error string."""
    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data=None, error="bird mentions: exit code 1")):
        from app.integrations.bird import fetch_mentions_bird
        result, err = await fetch_mentions_bird("sawinyh", auth_token="x", ct0="y")

    assert result == []
    assert err is not None


@pytest.mark.asyncio
async def test_fetch_mentions_bird_empty_handle():
    """Empty handle → short-circuits to empty list without calling _run_bird."""
    from app.integrations.bird import fetch_mentions_bird

    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock) as mock_run:
        result, err = await fetch_mentions_bird("", auth_token="x", ct0="y")

    assert result == []
    assert err is None
    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_mentions_bird_strips_at_prefix():
    """Handle with leading @ is stripped before passing to CLI."""
    mock_data = [
        {"id": "500", "authorId": "111", "text": "hi @sawinyh", "createdAt": "2026-03-24T10:00:00Z"},
    ]
    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data=mock_data, error=None)) as mock_run:
        from app.integrations.bird import fetch_mentions_bird
        result, err = await fetch_mentions_bird("@sawinyh", count=5, auth_token="x", ct0="y")

    assert len(result) == 1
    # The CLI should have been called with @sawinyh (re-prefixed inside the function)
    call_args = mock_run.call_args
    assert "sawinyh" in " ".join(str(a) for a in call_args[0])


# ---------------------------------------------------------------------------
# fetch_user_replies_bird
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_user_replies_bird_filters_to_replies():
    """bird CLI returns mixed tweets → only replies (those with inReplyToId) returned."""
    mock_data = [
        {"id": "100", "text": "Regular tweet", "createdAt": "2026-03-24T10:00:00Z"},
        {"id": "101", "text": "@someone reply", "createdAt": "2026-03-24T11:00:00Z", "inReplyToId": "999"},
    ]
    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data=mock_data, error=None)):
        from app.integrations.bird import fetch_user_replies_bird
        result, err = await fetch_user_replies_bird("sawinyh", auth_token="x", ct0="y")

    assert err is None
    assert len(result) == 1
    assert result[0]["id"] == "101"
    assert result[0]["in_reply_to_user_id"] == "999"


@pytest.mark.asyncio
async def test_fetch_user_replies_bird_no_replies():
    """All tweets are non-replies → empty list."""
    mock_data = [
        {"id": "200", "text": "Just a thought", "createdAt": "2026-03-24T10:00:00Z"},
        {"id": "201", "text": "Another tweet", "createdAt": "2026-03-24T11:00:00Z"},
    ]
    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data=mock_data, error=None)):
        from app.integrations.bird import fetch_user_replies_bird
        result, err = await fetch_user_replies_bird("sawinyh", auth_token="x", ct0="y")

    assert result == []
    assert err is None


@pytest.mark.asyncio
async def test_fetch_user_replies_bird_empty_on_failure():
    """bird CLI fails → empty list with error string."""
    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data=None, error="bird user-tweets: exit code 1")):
        from app.integrations.bird import fetch_user_replies_bird
        result, err = await fetch_user_replies_bird("sawinyh", auth_token="x", ct0="y")

    assert result == []
    assert err is not None


@pytest.mark.asyncio
async def test_fetch_user_replies_bird_empty_handle():
    """Empty handle → short-circuits to empty list."""
    from app.integrations.bird import fetch_user_replies_bird

    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock) as mock_run:
        result, err = await fetch_user_replies_bird("", auth_token="x", ct0="y")

    assert result == []
    assert err is None
    mock_run.assert_not_called()
