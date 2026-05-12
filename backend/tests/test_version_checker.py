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
