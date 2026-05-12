"""Self-hoster version-check: poll GitHub releases, compare, cache."""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version

from app.core.redis import get_redis
from app.core.version import APP_VERSION
from app.schemas.version import VersionData

logger = logging.getLogger(__name__)

GITHUB_RELEASES_URL = "https://api.github.com/repos/sneg55/pingcrm/releases/latest"
FETCH_TIMEOUT_S = 10.0
USER_AGENT = "pingcrm-version-check"


async def fetch_latest_release() -> dict[str, Any] | None:
    """Fetch the latest GitHub release JSON.

    Returns None on any failure (timeout, network error, non-2xx, malformed
    JSON). Failures are logged but never re-raised.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S) as client:
            response = await client.get(GITHUB_RELEASES_URL, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        remaining = e.response.headers.get("X-RateLimit-Remaining")
        logger.warning(
            "github release fetch failed",
            extra={
                "provider": "github",
                "status": e.response.status_code,
                "rate_limit_remaining": remaining,
            },
        )
        return None
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.warning(
            "github release fetch network error",
            extra={"provider": "github", "err": str(e)},
        )
        return None
    except ValueError:
        logger.exception(
            "github release fetch returned malformed JSON",
            extra={"provider": "github"},
        )
        return None
    except Exception:
        logger.exception(
            "github release fetch unexpected failure",
            extra={"provider": "github"},
        )
        return None


_SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+([-.+].*)?$")


def _parse(tag: str | None) -> Version | None:
    if not tag or not _SEMVER_RE.match(tag):
        return None
    try:
        return Version(tag.lstrip("v"))
    except InvalidVersion:
        return None


def compare_versions(current: str, latest_tag: str | None) -> bool | None:
    """Return True iff `latest_tag` is strictly newer than `current`.

    Returns None when comparison is impossible (current is dev/SHA, latest
    is missing or malformed).
    """
    current_v = _parse(current)
    latest_v = _parse(latest_tag)
    if current_v is None or latest_v is None:
        return None
    return latest_v > current_v


CACHE_KEY = "pingcrm:version:latest"
FAILURE_KEY = "pingcrm:version:failure"
CACHE_TTL_S = 12 * 60 * 60       # 12 hours
FAILURE_TTL_S = 5 * 60           # 5 minutes
DISABLE_ENV = "DISABLE_UPDATE_CHECK"


def is_disabled() -> bool:
    return bool(os.getenv(DISABLE_ENV))


async def refresh_cache() -> None:
    """Fetch latest release and persist to Redis, or write failure marker."""
    if is_disabled():
        return

    payload = await fetch_latest_release()
    redis = get_redis()

    if payload is None:
        await redis.set(FAILURE_KEY, "1", ex=FAILURE_TTL_S)
        return

    record = {
        "tag_name": payload.get("tag_name"),
        "name": payload.get("name"),
        "html_url": payload.get("html_url"),
        "body": payload.get("body"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.set(CACHE_KEY, json.dumps(record), ex=CACHE_TTL_S)


async def get_cached_status() -> VersionData:
    """Read cached release info and compute the user-facing status."""
    if is_disabled():
        return VersionData(current=APP_VERSION, disabled=True)

    redis = get_redis()
    raw = await redis.get(CACHE_KEY)
    if raw is None:
        return VersionData(current=APP_VERSION)

    if isinstance(raw, bytes):
        raw = raw.decode()
    record = json.loads(raw)
    latest_tag = record.get("tag_name")

    fetched_at = record.get("fetched_at")
    checked_at = datetime.fromisoformat(fetched_at) if fetched_at else None

    return VersionData(
        current=APP_VERSION,
        latest=latest_tag,
        release_url=record.get("html_url"),
        release_notes=record.get("body"),
        update_available=compare_versions(APP_VERSION, latest_tag),
        checked_at=checked_at,
    )


async def has_recent_failure() -> bool:
    """True if a recent GitHub fetch failure marker exists."""
    redis = get_redis()
    return bool(await redis.get(FAILURE_KEY))
