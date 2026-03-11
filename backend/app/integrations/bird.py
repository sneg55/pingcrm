"""bird CLI integration — cookie-based Twitter/X data access.

Uses the ``bird`` CLI (@steipete/bird) which authenticates via browser
cookies, bypassing X API rate limits and credit restrictions.

All functions are best-effort and return empty results on failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)

_BIRD_TIMEOUT = 20  # seconds


async def _run_bird(*args: str) -> dict | list | None:
    """Execute a bird CLI command and parse JSON output.

    Returns parsed JSON (dict or list) on success, None on failure.
    """
    bird_path = shutil.which("bird")
    if not bird_path:
        logger.warning("bird CLI not found on PATH")
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
    except (asyncio.TimeoutError, OSError) as exc:
        logger.warning("bird %s: timed out or failed: %s", args[0], exc)
        return None

    if proc.returncode != 0:
        logger.warning(
            "bird %s: exit code %d: %s",
            args[0], proc.returncode, stderr.decode(errors="replace")[:200],
        )
        return None

    try:
        return json.loads(stdout.decode())
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("bird %s: invalid JSON: %s", args[0], exc)
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


async def fetch_user_tweets_bird(handle: str, count: int = 5) -> list[dict[str, Any]]:
    """Fetch a user's recent tweets via ``bird search from:user``."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return []
    # bird 0.4.0 uses 'search from:user' instead of 'user-tweets'
    data = await _run_bird("search", f"from:{handle}", "-n", str(count))
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

    # Primary: bird search from:user → extract profile from _raw
    # bird 0.4.0 uses 'search from:user' instead of 'user-tweets'
    data = await _run_bird("search", f"from:{handle}", "-n", "1")
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

    # Note: bird 0.4.0 doesn't have 'about' command for user profiles
    # Location must come from the search result's user data

    return result


async def fetch_mentions_bird(handle: str, count: int = 50) -> list[dict[str, Any]]:
    """Fetch mentions of a user via ``bird mentions``."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return []
    data = await _run_bird("mentions", "--user", f"@{handle}", "-n", str(count))
    return _extract_tweets(data)


async def fetch_user_replies_bird(handle: str, count: int = 50) -> list[dict[str, Any]]:
    """Fetch a user's tweets and filter to replies only.

    bird returns ``inReplyToStatusId`` for replies. We use that as a proxy
    for ``in_reply_to_user_id`` since bird includes the parent tweet info.
    """
    handle = handle.lstrip("@").strip()
    if not handle:
        return []
    # bird 0.4.0 uses 'search from:user' instead of 'user-tweets'
    data = await _run_bird("search", f"from:{handle}", "-n", str(count))
    tweets = _extract_tweets(data)
    return [t for t in tweets if t.get("inReplyToStatusId")]
