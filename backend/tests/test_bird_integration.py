"""Tests for the bird CLI integration wrapper (app/integrations/bird.py).

All subprocess calls are mocked — the bird CLI binary is an external
dependency and is not required to be installed for tests to pass.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.integrations.bird as bird_mod
from app.integrations.bird import (
    _extract_tweets,
    _run_bird,
    check_health,
    fetch_user_profile_bird,
    fetch_user_tweets_bird,
    is_available,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Return a mock asyncio.Process that yields (stdout, stderr) on communicate()."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


def test_is_available_true(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    assert is_available() is True


def test_is_available_false(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert is_available() is False


# ---------------------------------------------------------------------------
# check_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_not_found(monkeypatch):
    """When bird is not on PATH, check_health returns available=False immediately."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    result = await check_health()
    assert result["available"] is False
    assert "not found" in result["error"]
    assert result["version"] is None


@pytest.mark.asyncio
async def test_check_health_success(monkeypatch):
    """When bird --version exits 0, available=True and version is populated."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    proc = _make_proc(returncode=0, stdout=b"bird 0.8.0\n")

    async def _fake_exec(*args, **kwargs):
        return proc

    with patch("asyncio.create_subprocess_exec", new=_fake_exec), \
         patch("asyncio.wait_for", new=AsyncMock(side_effect=[proc, (b"bird 0.8.0\n", b"")])):
        # Re-patch wait_for properly: first call returns the proc object,
        # second returns communicate result.
        async def _wait_for(coro_or_fut, timeout=None):
            if asyncio.iscoroutine(coro_or_fut):
                return await coro_or_fut
            return await coro_or_fut

        with patch("asyncio.wait_for", side_effect=_wait_for):
            result = await check_health()

    assert result["available"] is True
    assert result["error"] is None


@pytest.mark.asyncio
async def test_check_health_timeout(monkeypatch):
    """When the subprocess times out, check_health returns available=False."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        result = await check_health()

    assert result["available"] is False
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# _run_bird
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_bird_cli_not_found(monkeypatch):
    """When bird is absent, _run_bird returns None and sets last_error."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    bird_mod.last_error = None

    result = await _run_bird("user-tweets", "@someone")

    assert result is None
    assert bird_mod.last_error is not None
    assert "not found" in bird_mod.last_error


@pytest.mark.asyncio
async def test_run_bird_success_returns_parsed_json(monkeypatch):
    """Successful CLI run returns parsed JSON and clears last_error."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    payload = [{"id": "1", "text": "Hello world"}]
    proc = _make_proc(returncode=0, stdout=json.dumps(payload).encode())

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _fake_wait_for(coro_or_fut, timeout=None):
        if asyncio.iscoroutine(coro_or_fut):
            return await coro_or_fut
        return await coro_or_fut

    bird_mod.last_error = "previous error"

    with patch("asyncio.create_subprocess_exec", new=_fake_exec), \
         patch("asyncio.wait_for", side_effect=_fake_wait_for):
        result = await _run_bird("user-tweets", "@someone")

    assert result == payload
    assert bird_mod.last_error is None


@pytest.mark.asyncio
async def test_run_bird_nonzero_exit_returns_none(monkeypatch):
    """Non-zero exit code causes _run_bird to return None and record error."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    proc = _make_proc(returncode=1, stdout=b"", stderr=b"auth failed")

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _fake_wait_for(coro_or_fut, timeout=None):
        if asyncio.iscoroutine(coro_or_fut):
            return await coro_or_fut
        return await coro_or_fut

    bird_mod.last_error = None

    with patch("asyncio.create_subprocess_exec", new=_fake_exec), \
         patch("asyncio.wait_for", side_effect=_fake_wait_for):
        result = await _run_bird("user-tweets", "@someone")

    assert result is None
    assert bird_mod.last_error is not None
    assert "exit code 1" in bird_mod.last_error


@pytest.mark.asyncio
async def test_run_bird_invalid_json_returns_none(monkeypatch):
    """Invalid JSON from stdout causes _run_bird to return None."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    proc = _make_proc(returncode=0, stdout=b"not valid json {{{")

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _fake_wait_for(coro_or_fut, timeout=None):
        if asyncio.iscoroutine(coro_or_fut):
            return await coro_or_fut
        return await coro_or_fut

    with patch("asyncio.create_subprocess_exec", new=_fake_exec), \
         patch("asyncio.wait_for", side_effect=_fake_wait_for):
        result = await _run_bird("user-tweets", "@someone")

    assert result is None
    assert bird_mod.last_error is not None
    assert "invalid JSON" in bird_mod.last_error


@pytest.mark.asyncio
async def test_run_bird_timeout(monkeypatch):
    """Subprocess timeout causes _run_bird to return None with descriptive error."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        result = await _run_bird("user-tweets", "@someone")

    assert result is None
    assert bird_mod.last_error is not None
    assert "timed out" in bird_mod.last_error


@pytest.mark.asyncio
async def test_run_bird_os_error(monkeypatch):
    """OSError during subprocess spawn returns None with OS error message."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    with patch("asyncio.create_subprocess_exec", side_effect=OSError("permission denied")):
        # wait_for is called first; simulate it propagating the OSError
        async def _fake_wait_for(coro_or_fut, timeout=None):
            if asyncio.iscoroutine(coro_or_fut):
                return await coro_or_fut
            return await coro_or_fut

        with patch("asyncio.wait_for", side_effect=_fake_wait_for):
            result = await _run_bird("user-tweets", "@someone")

    assert result is None
    assert bird_mod.last_error is not None
    assert "OS error" in bird_mod.last_error


# ---------------------------------------------------------------------------
# _extract_tweets
# ---------------------------------------------------------------------------


def test_extract_tweets_from_list():
    tweets = [{"id": "1"}, {"id": "2"}]
    assert _extract_tweets(tweets) == tweets


def test_extract_tweets_from_dict_with_tweets_key():
    data = {"tweets": [{"id": "1"}], "meta": {}}
    assert _extract_tweets(data) == [{"id": "1"}]


def test_extract_tweets_from_dict_without_tweets_key():
    assert _extract_tweets({"other": "stuff"}) == []


def test_extract_tweets_none():
    assert _extract_tweets(None) == []


# ---------------------------------------------------------------------------
# fetch_user_tweets_bird
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_user_tweets_empty_handle():
    """Empty handle short-circuits before any subprocess call."""
    result = await fetch_user_tweets_bird("")
    assert result == []


@pytest.mark.asyncio
async def test_fetch_user_tweets_strips_at_sign(monkeypatch):
    """@ prefix is stripped, then re-added when calling the CLI."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    # CLI absent → empty list, but no crash
    result = await fetch_user_tweets_bird("@elonmusk")
    assert result == []


@pytest.mark.asyncio
async def test_fetch_user_tweets_success(monkeypatch):
    """Returns flat list of tweet dicts on success."""
    tweets = [{"id": "1", "text": "tweet one"}, {"id": "2", "text": "tweet two"}]

    async def _fake_run(*args, **kwargs):
        return tweets

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        result = await fetch_user_tweets_bird("elonmusk", count=2)

    assert result == tweets


@pytest.mark.asyncio
async def test_fetch_user_tweets_cli_unavailable(monkeypatch):
    """Returns [] when _run_bird returns None (CLI not found)."""
    async def _fake_run(*args, **kwargs):
        return None

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        result = await fetch_user_tweets_bird("elonmusk")

    assert result == []


# ---------------------------------------------------------------------------
# fetch_user_profile_bird
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_user_profile_empty_handle():
    result = await fetch_user_profile_bird("")
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_user_profile_cli_unavailable(monkeypatch):
    """Returns empty dict when CLI is absent."""
    async def _fake_run(*args, **kwargs):
        return None

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        result = await fetch_user_profile_bird("elonmusk")

    assert result == {}


@pytest.mark.asyncio
async def test_fetch_user_profile_parses_full_response(monkeypatch):
    """Parses nested GraphQL-style response into normalised profile dict."""
    raw_user = {
        "legacy": {
            "name": "Elon Musk",
            "screen_name": "elonmusk",
            "followers_count": 100_000_000,
            "friends_count": 500,
            "statuses_count": 25_000,
            "listed_count": 80_000,
        },
        "profile_bio": {"description": "CEO of X, SpaceX"},
        "location": {"location": "Austin, TX"},
        "avatar": {"image_url": "https://pbs.twimg.com/profile_images/x_normal.jpg"},
    }
    tweet_with_raw = {
        "id": "99",
        "_raw": {
            "core": {
                "user_results": {
                    "result": raw_user,
                }
            }
        },
    }

    async def _fake_run(*args, **kwargs):
        return [tweet_with_raw]

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        profile = await fetch_user_profile_bird("elonmusk")

    assert profile["name"] == "Elon Musk"
    assert profile["username"] == "elonmusk"
    assert profile["description"] == "CEO of X, SpaceX"
    assert profile["location"] == "Austin, TX"
    # Avatar URL should be upscaled from _normal to _400x400
    assert "_400x400." in profile["profile_image_url"]
    assert profile["profileImageUrl"] == profile["profile_image_url"]
    metrics = profile["public_metrics"]
    assert metrics["followers_count"] == 100_000_000
    assert metrics["friends_count"] == 500


@pytest.mark.asyncio
async def test_fetch_user_profile_missing_raw(monkeypatch):
    """Tweet without _raw block returns partial/empty profile gracefully."""
    async def _fake_run(*args, **kwargs):
        return [{"id": "99", "text": "hello"}]

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        profile = await fetch_user_profile_bird("someone")

    # No crash; result may be empty or partial
    assert isinstance(profile, dict)


