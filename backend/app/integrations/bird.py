"""bird CLI integration — cookie-based Twitter/X data access.

Uses the ``bird`` CLI (@steipete/bird v0.8.0) which authenticates via browser
cookies, bypassing X API rate limits and credit restrictions.

All functions are best-effort and return empty results on failure.
Failures are tracked via ``last_error`` so callers can surface them to users.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)

_BIRD_TIMEOUT = 20  # seconds

# Tracks the last bird CLI error for the current process — callers can read
# this after a batch of bird calls to decide whether to notify the user.
last_error: str | None = None


def is_available() -> bool:
    """Check if the bird CLI is installed and on PATH."""
    return shutil.which("bird") is not None


async def check_health() -> dict[str, Any]:
    """Run a lightweight bird health check.

    Returns a dict with ``available``, ``version``, and ``error`` keys.
    """
    if not is_available():
        return {"available": False, "version": None, "error": "bird CLI not found on PATH"}

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                shutil.which("bird"), "--version",  # type: ignore[arg-type]
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=5,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        version = stdout.decode().strip() if proc.returncode == 0 else None
        return {"available": True, "version": version, "error": None}
    except (asyncio.TimeoutError, OSError) as exc:
        return {"available": False, "version": None, "error": str(exc)}


async def _run_bird(*args: str) -> dict | list | None:
    """Execute a bird CLI command and parse JSON output.

    Returns parsed JSON (dict or list) on success, None on failure.
    Sets ``last_error`` on failure so callers can inspect it.
    """
    global last_error

    bird_path = shutil.which("bird")
    if not bird_path:
        last_error = "bird CLI not found on PATH — Twitter enrichment is unavailable"
        logger.warning(last_error)
        return None

    cmd = [bird_path, *args]
    # Add --json unless --json-full is already present
    if "--json-full" not in args:
        cmd.append("--json")

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=_BIRD_TIMEOUT,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=_BIRD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        last_error = f"bird {args[0]}: timed out after {_BIRD_TIMEOUT}s"
        logger.warning(last_error)
        return None
    except OSError as exc:
        last_error = f"bird {args[0]}: OS error: {exc}"
        logger.warning(last_error)
        return None

    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")[:200]
        last_error = f"bird {args[0]}: exit code {proc.returncode}: {stderr_text}"
        logger.warning(last_error)
        return None

    try:
        last_error = None  # success — clear any previous error
        return json.loads(stdout.decode())
    except (json.JSONDecodeError, ValueError) as exc:
        last_error = f"bird {args[0]}: invalid JSON output: {exc}"
        logger.warning(last_error)
        return None


def _extract_tweets(data: dict | list | None) -> list[dict[str, Any]]:
    """Normalise bird output into a flat list of tweet dicts."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("tweets", [])
    return []


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


async def resolve_user_id_bird(handle: str) -> str | None:
    """Resolve a Twitter handle to a numeric user ID via bird CLI.

    Uses ``bird user-tweets --json-full`` to extract ``rest_id`` from the
    GraphQL user object.  Returns the ID string or None on failure.
    """
    handle = handle.lstrip("@").strip()
    if not handle:
        return None
    data = await _run_bird("user-tweets", f"@{handle}", "-n", "1", "--json-full")
    tweets = _extract_tweets(data)
    if not tweets:
        return None
    user = (
        tweets[0]
        .get("_raw", {})
        .get("core", {})
        .get("user_results", {})
        .get("result", {})
    )
    rest_id = user.get("rest_id")
    return str(rest_id) if rest_id else None


async def fetch_user_tweets_bird(handle: str, count: int = 5) -> list[dict[str, Any]]:
    """Fetch a user's recent tweets via ``bird user-tweets``."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return []
    data = await _run_bird("user-tweets", f"@{handle}", "-n", str(count))
    return _extract_tweets(data)


async def fetch_user_profile_bird(handle: str) -> dict[str, Any]:
    """Fetch a user's profile via ``bird user-tweets --json-full``.

    The ``--json-full`` flag includes the raw GraphQL response which contains
    the full user profile (bio, avatar, location, metrics) extracted from
    cookie-based auth — no API credits needed.

    Falls back to ``bird about`` (account origin) + Twitter API if the
    full response doesn't contain user data.

    Returns a dict with normalised keys:
    ``description``, ``location``, ``profileImageUrl``, ``profile_image_url``,
    ``name``, ``username``, ``public_metrics``.
    """
    handle = handle.lstrip("@").strip()
    if not handle:
        return {}

    result: dict[str, Any] = {}

    # Primary: bird user-tweets --json-full → extract profile from _raw
    data = await _run_bird("user-tweets", f"@{handle}", "-n", "1", "--json-full")
    tweets = _extract_tweets(data)
    if tweets:
        raw = tweets[0].get("_raw", {})
        user = raw.get("core", {}).get("user_results", {}).get("result", {})
        legacy = user.get("legacy", {})

        # Bio: user.profile_bio.description
        bio = user.get("profile_bio", {}).get("description", "")
        if bio:
            result["description"] = bio

        # Location: user.location.location
        loc = user.get("location", {}).get("location", "")
        if loc:
            result["location"] = loc

        # Avatar: user.avatar.image_url
        avatar = user.get("avatar", {}).get("image_url", "")
        if avatar:
            avatar_hires = avatar.replace("_normal.", "_400x400.")
            result["profile_image_url"] = avatar_hires
            result["profileImageUrl"] = avatar_hires

        # Name/username from legacy
        if legacy.get("name"):
            result["name"] = legacy["name"]
        if legacy.get("screen_name"):
            result["username"] = legacy["screen_name"]

        # Metrics from legacy
        metrics = {}
        for k in ("followers_count", "friends_count", "statuses_count", "listed_count"):
            if legacy.get(k) is not None:
                metrics[k] = legacy[k]
        if metrics:
            result["public_metrics"] = metrics

    # Note: bird CLI doesn't have an 'about' command for user profiles
    # Location must come from the user-tweets result's embedded user data

    return result


