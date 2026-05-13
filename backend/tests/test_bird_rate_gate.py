"""Tests for the bird rate-gate (Fix 2 for the 429 storm)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.bird import (
    _gate_key,
    _is_rate_gated,
    _set_rate_gate,
    fetch_user_tweets_bird,
)


def test_gate_key_hashes_ct0():
    """Gate key must hash ct0 — the cookie should never appear in the key."""
    key = _gate_key("secret_cookie_value")
    assert "secret_cookie_value" not in key
    assert key.startswith("bird_rate_gate:")
    assert len(key.split(":", 1)[1]) == 16


def test_gate_key_stable():
    """Same ct0 should produce the same key (so the gate persists across calls)."""
    assert _gate_key("foo") == _gate_key("foo")
    assert _gate_key("foo") != _gate_key("bar")


@pytest.mark.asyncio
async def test_rate_gate_set_and_check():
    """Setting the gate makes _is_rate_gated return True for the same ct0."""
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(side_effect=[None, b"1"])
    fake_redis.set = AsyncMock()
    with patch("app.core.redis.get_redis", return_value=fake_redis):
        assert await _is_rate_gated("ct0_value") is False
        await _set_rate_gate("ct0_value")
        assert await _is_rate_gated("ct0_value") is True
    fake_redis.set.assert_awaited_once()
    set_args = fake_redis.set.await_args
    assert set_args.args[0] == _gate_key("ct0_value")
    assert set_args.kwargs["ex"] == 15 * 60


@pytest.mark.asyncio
async def test_run_bird_short_circuits_when_gated():
    """If the gate is set, _run_bird returns an error without shelling out."""
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=b"1")  # gated
    with patch("app.core.redis.get_redis", return_value=fake_redis), \
         patch("asyncio.create_subprocess_exec", side_effect=AssertionError(
             "should not exec when gated"
         )):
        tweets, err = await fetch_user_tweets_bird(
            "anyhandle", auth_token="t", ct0="ct0_value",
        )
    assert tweets == []
    assert err is not None
    assert "rate-gated" in err


@pytest.mark.asyncio
async def test_run_bird_trips_gate_on_429():
    """A bird exit-code-1 with '429' in stderr should set the gate."""
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)  # not gated initially
    fake_redis.set = AsyncMock()

    # Mock asyncio.create_subprocess_exec to return a proc whose stderr has the 429 marker
    fake_proc = AsyncMock()
    fake_proc.returncode = 1
    fake_proc.communicate = AsyncMock(return_value=(
        b"",
        b"\xe2\x9d\x8c Failed to fetch tweets: HTTP 429: Rate limit exceeded\n",
    ))

    with patch("app.core.redis.get_redis", return_value=fake_redis), \
         patch("shutil.which", return_value="/usr/bin/bird"), \
         patch(
             "asyncio.create_subprocess_exec",
             AsyncMock(return_value=fake_proc),
         ):
        tweets, err = await fetch_user_tweets_bird(
            "anyhandle", auth_token="t", ct0="ct0_value",
        )

    assert tweets == []
    assert err is not None
    fake_redis.set.assert_awaited_once()
    set_call = fake_redis.set.await_args
    assert set_call.args[0] == _gate_key("ct0_value")
