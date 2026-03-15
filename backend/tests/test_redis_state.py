"""Tests for Redis-backed state stores."""
import pytest
import fakeredis.aioredis

from unittest.mock import patch


@pytest.fixture
def fake_redis():
    """Provide a fakeredis instance and patch get_redis everywhere it's imported."""
    fr = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("app.core.redis.get_redis", return_value=fr), \
         patch("app.api.twitter.get_redis", return_value=fr), \
         patch("app.api.auth.get_redis", return_value=fr), \
         patch("app.api.contacts_routes.sync.get_redis", return_value=fr):
        yield fr


@pytest.mark.asyncio
async def test_pkce_store_roundtrip(fake_redis):
    from app.api.twitter import _store_pkce, _pop_pkce
    await _store_pkce("state123", "verifier456", "user789")
    result = await _pop_pkce("state123")
    assert result == ("verifier456", "user789")


@pytest.mark.asyncio
async def test_pkce_store_pop_deletes(fake_redis):
    from app.api.twitter import _store_pkce, _pop_pkce
    await _store_pkce("s1", "v1", "u1")
    await _pop_pkce("s1")
    assert await _pop_pkce("s1") is None


@pytest.mark.asyncio
async def test_pkce_store_missing_returns_none(fake_redis):
    from app.api.twitter import _pop_pkce
    assert await _pop_pkce("nonexistent") is None


@pytest.mark.asyncio
async def test_google_state_roundtrip(fake_redis):
    from app.api.auth import _store_google_state, _pop_google_state
    await _store_google_state("state_abc", "user_123")
    result = await _pop_google_state("state_abc")
    assert result == "user_123"


@pytest.mark.asyncio
async def test_google_state_pop_deletes(fake_redis):
    from app.api.auth import _store_google_state, _pop_google_state
    await _store_google_state("s1", "u1")
    await _pop_google_state("s1")
    assert await _pop_google_state("s1") is None


@pytest.mark.asyncio
async def test_google_state_missing_returns_none(fake_redis):
    from app.api.auth import _pop_google_state
    assert await _pop_google_state("missing") is None


@pytest.mark.asyncio
async def test_bio_check_cache(fake_redis):
    r = fake_redis
    key = "bio_check:test-contact-id"
    assert not await r.exists(key)
    await r.setex(key, 86400, "1")
    assert await r.exists(key)
