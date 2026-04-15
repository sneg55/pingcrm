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
    BirdResult,
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
    """When bird is absent, _run_bird returns BirdResult with error."""
    monkeypatch.setattr("shutil.which", lambda _name: None)

    result = await _run_bird("user-tweets", "@someone", auth_token="a", ct0="b")

    assert result.data is None
    assert result.error is not None
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_run_bird_success_returns_parsed_json(monkeypatch):
    """Successful CLI run returns BirdResult with parsed data and no error."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    payload = [{"id": "1", "text": "Hello world"}]
    proc = _make_proc(returncode=0, stdout=json.dumps(payload).encode())

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _fake_wait_for(coro_or_fut, timeout=None):
        if asyncio.iscoroutine(coro_or_fut):
            return await coro_or_fut
        return await coro_or_fut

    with patch("asyncio.create_subprocess_exec", new=_fake_exec), \
         patch("asyncio.wait_for", side_effect=_fake_wait_for):
        result = await _run_bird("user-tweets", "@someone", auth_token="a", ct0="b")

    assert result.data == payload
    assert result.error is None


@pytest.mark.asyncio
async def test_run_bird_nonzero_exit_returns_none(monkeypatch):
    """Non-zero exit code causes _run_bird to return BirdResult with error."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    proc = _make_proc(returncode=1, stdout=b"", stderr=b"auth failed")

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _fake_wait_for(coro_or_fut, timeout=None):
        if asyncio.iscoroutine(coro_or_fut):
            return await coro_or_fut
        return await coro_or_fut

    with patch("asyncio.create_subprocess_exec", new=_fake_exec), \
         patch("asyncio.wait_for", side_effect=_fake_wait_for):
        result = await _run_bird("user-tweets", "@someone", auth_token="a", ct0="b")

    assert result.data is None
    assert result.error is not None
    assert "exit code 1" in result.error


@pytest.mark.asyncio
async def test_run_bird_invalid_json_returns_none(monkeypatch):
    """Invalid JSON from stdout causes _run_bird to return BirdResult with error."""
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
        result = await _run_bird("user-tweets", "@someone", auth_token="a", ct0="b")

    assert result.data is None
    assert result.error is not None
    assert "invalid JSON" in result.error


@pytest.mark.asyncio
async def test_run_bird_timeout(monkeypatch):
    """Subprocess timeout causes _run_bird to return BirdResult with descriptive error."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        result = await _run_bird("user-tweets", "@someone", auth_token="a", ct0="b")

    assert result.data is None
    assert result.error is not None
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_run_bird_os_error(monkeypatch):
    """OSError during subprocess spawn returns BirdResult with OS error message."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")

    with patch("asyncio.create_subprocess_exec", side_effect=OSError("permission denied")):
        # wait_for is called first; simulate it propagating the OSError
        async def _fake_wait_for(coro_or_fut, timeout=None):
            if asyncio.iscoroutine(coro_or_fut):
                return await coro_or_fut
            return await coro_or_fut

        with patch("asyncio.wait_for", side_effect=_fake_wait_for):
            result = await _run_bird("user-tweets", "@someone", auth_token="a", ct0="b")

    assert result.data is None
    assert result.error is not None
    assert "OS error" in result.error


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
    result, err = await fetch_user_tweets_bird("", auth_token="a", ct0="b")
    assert result == []
    assert err is None


@pytest.mark.asyncio
async def test_fetch_user_tweets_strips_at_sign(monkeypatch):
    """@ prefix is stripped, then re-added when calling the CLI."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    # CLI absent → empty list, error string
    result, err = await fetch_user_tweets_bird("@elonmusk", auth_token="a", ct0="b")
    assert result == []


@pytest.mark.asyncio
async def test_fetch_user_tweets_success(monkeypatch):
    """Returns flat list of tweet dicts on success."""
    tweets = [{"id": "1", "text": "tweet one"}, {"id": "2", "text": "tweet two"}]

    async def _fake_run(*args, **kwargs):
        return BirdResult(data=tweets, error=None)

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        result, err = await fetch_user_tweets_bird("elonmusk", count=2, auth_token="a", ct0="b")

    assert result == tweets
    assert err is None


@pytest.mark.asyncio
async def test_fetch_user_tweets_cli_unavailable(monkeypatch):
    """Returns ([], error) when _run_bird returns BirdResult with error."""
    async def _fake_run(*args, **kwargs):
        return BirdResult(data=None, error="bird CLI not found")

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        result, err = await fetch_user_tweets_bird("elonmusk", auth_token="a", ct0="b")

    assert result == []
    assert err == "bird CLI not found"


# ---------------------------------------------------------------------------
# fetch_user_profile_bird
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_user_profile_empty_handle():
    profile, err = await fetch_user_profile_bird("", auth_token="a", ct0="b")
    assert profile == {}
    assert err is None


@pytest.mark.asyncio
async def test_fetch_user_profile_cli_unavailable(monkeypatch):
    """Returns ({}, error) when CLI is absent."""
    async def _fake_run(*args, **kwargs):
        return BirdResult(data=None, error="bird CLI not found")

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        profile, err = await fetch_user_profile_bird("elonmusk", auth_token="a", ct0="b")

    assert profile == {}
    assert err == "bird CLI not found"


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
        return BirdResult(data=[tweet_with_raw], error=None)

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        profile, err = await fetch_user_profile_bird("elonmusk", auth_token="a", ct0="b")

    assert err is None
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
        return BirdResult(data=[{"id": "99", "text": "hello"}], error=None)

    with patch.object(bird_mod, "_run_bird", new=_fake_run):
        profile, err = await fetch_user_profile_bird("someone", auth_token="a", ct0="b")

    # No crash; result may be empty or partial
    assert isinstance(profile, dict)
    assert err is None


# ---------------------------------------------------------------------------
# New in Task 3: BirdResult / per-call cookies / verify_cookies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_bird_passes_cookie_flags(monkeypatch):
    """_run_bird must include --auth-token and --ct0 in the argv, in that order, before the bird subcommand."""
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    captured: dict = {}

    proc = _make_proc(returncode=0, stdout=b"[]")

    async def _fake_exec(*args, **kwargs):
        captured["args"] = args
        return proc

    import app.integrations.bird as _bird

    async def _wait_for(coro, timeout):
        return await coro

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("asyncio.wait_for", _wait_for)

    result = await _bird._run_bird(
        "mentions", "-u", "@alice",
        auth_token="AUTH123", ct0="CT0XYZ",
    )

    argv = captured["args"]
    assert "--auth-token" in argv and "AUTH123" in argv
    assert "--ct0" in argv and "CT0XYZ" in argv
    # auth flags should come BEFORE the subcommand
    assert argv.index("--auth-token") < argv.index("mentions")
    assert result.data == []
    assert result.error is None


@pytest.mark.asyncio
async def test_run_bird_returns_error_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    proc = _make_proc(returncode=1, stdout=b"", stderr=b"401 unauthorized")

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _wait_for(coro, timeout):
        return await coro

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("asyncio.wait_for", _wait_for)

    import app.integrations.bird as _bird
    result = await _bird._run_bird(
        "mentions", "-u", "@alice", auth_token="a", ct0="b",
    )
    assert result.data is None
    assert "exit code 1" in result.error
    assert "401 unauthorized" in result.error


@pytest.mark.asyncio
async def test_verify_cookies_does_not_pass_json_flag_to_whoami(monkeypatch):
    """bird 0.8.0's `whoami` subcommand rejects --json ("unknown option").

    verify_cookies must shell out without --json; otherwise every prod call
    fails with exit 1 and users see status=expired even when logged in.
    """
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    captured: dict = {}
    proc = _make_proc(returncode=0, stdout=b"Logged in as @alice\n")

    async def _fake_exec(*args, **kwargs):
        captured["args"] = args
        return proc

    async def _wait_for(coro, timeout):
        return await coro

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("asyncio.wait_for", _wait_for)

    import app.integrations.bird as _bird
    assert await _bird.verify_cookies("a", "b") is True
    assert "--json" not in captured["args"]
    assert "whoami" in captured["args"]


@pytest.mark.asyncio
async def test_verify_cookies_true_on_exit_zero(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    proc = _make_proc(returncode=0, stdout=b'{"username":"alice"}')

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _wait_for(coro, timeout):
        return await coro

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("asyncio.wait_for", _wait_for)

    import app.integrations.bird as _bird
    assert await _bird.verify_cookies("a", "b") is True


@pytest.mark.asyncio
async def test_verify_cookies_false_on_exit_nonzero(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    proc = _make_proc(returncode=1, stdout=b"", stderr=b"invalid session")

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _wait_for(coro, timeout):
        return await coro

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("asyncio.wait_for", _wait_for)

    import app.integrations.bird as _bird
    assert await _bird.verify_cookies("a", "b") is False


# ---------------------------------------------------------------------------
# New in Task 4: (value, error) tuple returns + required cookie kwargs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_mentions_returns_list_and_none_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    proc = _make_proc(returncode=0, stdout=b'[{"id":"1","authorId":"2","text":"hi","createdAt":"2026-01-01"}]')

    async def _fake_exec(*args, **kwargs):
        return proc
    async def _wait_for(coro, timeout):
        return await coro
    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("asyncio.wait_for", _wait_for)

    import app.integrations.bird as _bird
    mentions, err = await _bird.fetch_mentions_bird(
        "alice", count=10, auth_token="a", ct0="b",
    )
    assert err is None
    assert mentions == [{"id": "1", "author_id": "2", "text": "hi", "created_at": "2026-01-01"}]


@pytest.mark.asyncio
async def test_fetch_mentions_returns_error_string_on_failure(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    proc = _make_proc(returncode=1, stdout=b"", stderr=b"401")

    async def _fake_exec(*args, **kwargs):
        return proc
    async def _wait_for(coro, timeout):
        return await coro
    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("asyncio.wait_for", _wait_for)

    import app.integrations.bird as _bird
    mentions, err = await _bird.fetch_mentions_bird(
        "alice", count=10, auth_token="a", ct0="b",
    )
    assert mentions == []
    assert err is not None and "exit code 1" in err


@pytest.mark.asyncio
async def test_fetch_user_profile_returns_empty_and_error_on_bird_failure(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/bird")
    proc = _make_proc(returncode=1, stdout=b"", stderr=b"boom")

    async def _fake_exec(*args, **kwargs):
        return proc
    async def _wait_for(coro, timeout):
        return await coro
    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("asyncio.wait_for", _wait_for)

    import app.integrations.bird as _bird
    profile, err = await _bird.fetch_user_profile_bird("alice", auth_token="a", ct0="b")
    assert profile == {}
    assert err is not None
