"""Tests for app.services.version_checker."""
import httpx
import pytest
import respx

from app.services.version_checker import GITHUB_RELEASES_URL, fetch_latest_release


@pytest.mark.asyncio
async def test_fetch_returns_payload_on_200():
    with respx.mock(assert_all_called=True) as mock:
        mock.get(GITHUB_RELEASES_URL).respond(
            200,
            json={
                "tag_name": "v1.7.0",
                "name": "v1.7.0 — birthday suggestions",
                "html_url": "https://github.com/sneg55/pingcrm/releases/tag/v1.7.0",
                "body": "## What's new\n- birthday suggestions",
            },
        )
        result = await fetch_latest_release()

    assert result is not None
    assert result["tag_name"] == "v1.7.0"
    assert result["html_url"].endswith("v1.7.0")


@pytest.mark.asyncio
async def test_fetch_returns_none_on_403_rate_limit(caplog):
    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(
            403,
            headers={"X-RateLimit-Remaining": "0"},
            json={"message": "API rate limit exceeded"},
        )
        result = await fetch_latest_release()

    assert result is None
    assert any("github" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_fetch_returns_none_on_5xx(caplog):
    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(503)
        result = await fetch_latest_release()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_network_error():
    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).mock(side_effect=httpx.ConnectError("boom"))
        result = await fetch_latest_release()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_malformed_json(caplog):
    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(200, content=b"not json")
        result = await fetch_latest_release()
    assert result is None


from app.services.version_checker import compare_versions


@pytest.mark.parametrize(
    "current,latest_tag,expected",
    [
        ("v1.6.0", "v1.7.0", True),
        ("1.6.0", "1.7.0", True),
        ("v1.7.0", "v1.7.0", False),
        ("v1.8.0", "v1.7.0", False),
        ("v1.7.0-rc.1", "v1.7.0", True),
        ("dev", "v1.7.0", None),
        ("abc1234", "v1.7.0", None),
        ("v1.6.0", "garbage", None),
        ("v1.6.0", None, None),
    ],
)
def test_compare_versions(current, latest_tag, expected):
    assert compare_versions(current, latest_tag) is expected


import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.services.version_checker import (
    CACHE_KEY,
    CACHE_TTL_S,
    FAILURE_KEY,
    FAILURE_TTL_S,
    get_cached_status,
    refresh_cache,
)


@pytest.mark.asyncio
async def test_refresh_cache_stores_release_on_success(monkeypatch):
    fake_redis = AsyncMock()
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )

    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(
            200,
            json={
                "tag_name": "v1.7.0",
                "name": "v1.7.0",
                "html_url": "https://example.com",
                "body": "notes",
            },
        )
        await refresh_cache()

    fake_redis.set.assert_awaited()
    call_args = fake_redis.set.await_args
    key = call_args.args[0]
    payload = json.loads(call_args.args[1])
    assert key == CACHE_KEY
    assert payload["tag_name"] == "v1.7.0"
    assert payload["html_url"] == "https://example.com"
    assert "fetched_at" in payload
    assert call_args.kwargs["ex"] == CACHE_TTL_S


@pytest.mark.asyncio
async def test_refresh_cache_writes_failure_marker_on_error(monkeypatch):
    fake_redis = AsyncMock()
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )

    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(503)
        await refresh_cache()

    set_calls = [c.args[0] for c in fake_redis.set.await_args_list]
    assert FAILURE_KEY in set_calls
    assert CACHE_KEY not in set_calls


@pytest.mark.asyncio
async def test_get_cached_status_returns_data_when_cached(monkeypatch):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=json.dumps({
        "tag_name": "v1.7.0",
        "html_url": "https://example.com/v1.7.0",
        "body": "notes",
        "name": "v1.7.0",
        "fetched_at": datetime(2026, 5, 12, tzinfo=timezone.utc).isoformat(),
    }))
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    status = await get_cached_status()

    assert status.current == "v1.6.0"
    assert status.latest == "v1.7.0"
    assert status.update_available is True
    assert status.release_url == "https://example.com/v1.7.0"
    assert status.disabled is False


@pytest.mark.asyncio
async def test_get_cached_status_empty_cache(monkeypatch):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    status = await get_cached_status()

    assert status.current == "v1.6.0"
    assert status.latest is None
    assert status.update_available is None
    assert status.disabled is False


@pytest.mark.asyncio
async def test_get_cached_status_disabled_env(monkeypatch):
    monkeypatch.setenv("DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )
    status = await get_cached_status()
    assert status.disabled is True
    assert status.update_available is None
