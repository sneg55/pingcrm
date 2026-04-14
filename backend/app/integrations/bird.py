"""bird CLI integration — cookie-based Twitter/X data access.

Uses the ``bird`` CLI (@steipete/bird v0.8.0) which authenticates via per-call
cookies passed as ``--auth-token`` and ``--ct0`` CLI flags, bypassing X API
rate limits and credit restrictions.

All functions are best-effort and return empty results on failure.
Failures are tracked via ``last_error`` (deprecated shim, removed in a later
task) so callers can surface them to users.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_BIRD_TIMEOUT = 20  # seconds

# Deprecated: module-level error shim kept for backward-compat until Task 7.
# _run_bird sets / clears this on each call so existing callers that read
# ``bird.last_error`` keep working.
last_error: str | None = None


@dataclass
class BirdResult:
    """Result from a bird CLI invocation."""

    data: dict | list | None
    error: str | None


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


async def _run_bird(*args: str, auth_token: str, ct0: str) -> BirdResult:
    """Execute a bird CLI command and parse JSON output.

    ``auth_token`` and ``ct0`` are required keyword arguments — they are
    injected as ``--auth-token`` / ``--ct0`` CLI flags before the subcommand
    so that concurrent per-user calls remain isolated.

    Returns a :class:`BirdResult` with ``data`` on success or ``error`` on
    failure.  Also writes to the module-global ``last_error`` for backward
    compatibility with callers that have not yet been migrated (Task 4+).
    """
    global last_error

    bird_path = shutil.which("bird")
    if not bird_path:
        msg = "bird CLI not found on PATH — Twitter enrichment is unavailable"
        last_error = msg
        logger.warning(msg)
        return BirdResult(data=None, error=msg)

    # Inject cookie flags before the subcommand (args[0] is the subcommand).
    cmd = [
        bird_path,
        "--auth-token", auth_token,
        "--ct0", ct0,
        *args,
    ]
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
        msg = f"bird {args[0]}: timed out after {_BIRD_TIMEOUT}s"
        last_error = msg
        logger.warning(msg)
        return BirdResult(data=None, error=msg)
    except OSError as exc:
        msg = f"bird {args[0]}: OS error: {exc}"
        last_error = msg
        logger.warning(msg)
        return BirdResult(data=None, error=msg)

    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")[:200]
        msg = f"bird {args[0]}: exit code {proc.returncode}: {stderr_text}"
        last_error = msg
        logger.warning(msg)
        return BirdResult(data=None, error=msg)

    try:
        last_error = None  # success — clear any previous error
        data = json.loads(stdout.decode())
        return BirdResult(data=data, error=None)
    except (json.JSONDecodeError, ValueError) as exc:
        msg = f"bird {args[0]}: invalid JSON output: {exc}"
        last_error = msg
        logger.warning(msg)
        return BirdResult(data=None, error=msg)


async def verify_cookies(auth_token: str, ct0: str) -> bool:
    """Verify that a set of Twitter cookies is valid by running ``bird whoami``.

    Calls ``bird --auth-token <auth_token> --ct0 <ct0> whoami --json`` and
    returns ``True`` iff the command exits with code 0.
    """
    result = await _run_bird("whoami", auth_token=auth_token, ct0=ct0)
    return result.error is None


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
# Transitional shim: read cookies from env vars when not explicitly supplied.
# Task 4 will thread per-user cookies through all callers and remove these
# os.getenv() fallbacks.


async def resolve_user_id_bird(handle: str) -> str | None:
    """Resolve a Twitter handle to a numeric user ID via bird CLI.

    Uses ``bird user-tweets --json-full`` to extract ``rest_id`` from the
    GraphQL user object.  Returns the ID string or None on failure.
    """
    handle = handle.lstrip("@").strip()
    if not handle:
        return None
    result = await _run_bird(
        "user-tweets", f"@{handle}", "-n", "1", "--json-full",
        auth_token=os.getenv("AUTH_TOKEN", ""),
        ct0=os.getenv("CT0", ""),
    )
    tweets = _extract_tweets(result.data)
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
    result = await _run_bird(
        "user-tweets", f"@{handle}", "-n", str(count),
        auth_token=os.getenv("AUTH_TOKEN", ""),
        ct0=os.getenv("CT0", ""),
    )
    return _extract_tweets(result.data)


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

    result_obj: dict[str, Any] = {}

    # Primary: bird user-tweets --json-full → extract profile from _raw
    result = await _run_bird(
        "user-tweets", f"@{handle}", "-n", "1", "--json-full",
        auth_token=os.getenv("AUTH_TOKEN", ""),
        ct0=os.getenv("CT0", ""),
    )
    tweets = _extract_tweets(result.data)
    if tweets:
        raw = tweets[0].get("_raw", {})
        user = raw.get("core", {}).get("user_results", {}).get("result", {})
        legacy = user.get("legacy", {})

        # Bio: user.profile_bio.description
        bio = user.get("profile_bio", {}).get("description", "")
        if bio:
            result_obj["description"] = bio

        # Location: user.location.location
        loc = user.get("location", {}).get("location", "")
        if loc:
            result_obj["location"] = loc

        # Avatar: user.avatar.image_url
        avatar = user.get("avatar", {}).get("image_url", "")
        if avatar:
            avatar_hires = avatar.replace("_normal.", "_400x400.")
            result_obj["profile_image_url"] = avatar_hires
            result_obj["profileImageUrl"] = avatar_hires

        # Name/username from legacy
        if legacy.get("name"):
            result_obj["name"] = legacy["name"]
        if legacy.get("screen_name"):
            result_obj["username"] = legacy["screen_name"]

        # Metrics from legacy
        metrics = {}
        for k in ("followers_count", "friends_count", "statuses_count", "listed_count"):
            if legacy.get(k) is not None:
                metrics[k] = legacy[k]
        if metrics:
            result_obj["public_metrics"] = metrics

    # Note: bird CLI doesn't have an 'about' command for user profiles
    # Location must come from the user-tweets result's embedded user data

    return result_obj


async def fetch_mentions_bird(handle: str, count: int = 50) -> list[dict[str, Any]]:
    """Fetch tweets mentioning a user via ``bird mentions``.

    Returns a normalized list of dicts with keys:
    ``id``, ``author_id``, ``text``, ``created_at``.
    Returns empty list on failure (last_error set).
    """
    handle = handle.lstrip("@").strip()
    if not handle:
        return []
    result = await _run_bird(
        "mentions", "-u", f"@{handle}", "-n", str(count),
        auth_token=os.getenv("AUTH_TOKEN", ""),
        ct0=os.getenv("CT0", ""),
    )
    tweets = _extract_tweets(result.data)
    out: list[dict[str, Any]] = []
    for t in tweets:
        tweet_id = t.get("id") or t.get("tweetId") or t.get("_raw", {}).get("rest_id")
        if not tweet_id:
            continue
        out.append({
            "id": str(tweet_id),
            "author_id": t.get("authorId") or t.get("author_id") or "",
            "text": t.get("text") or "",
            "created_at": t.get("createdAt") or t.get("created_at") or "",
        })
    return out


async def fetch_user_replies_bird(handle: str, count: int = 50) -> list[dict[str, Any]]:
    """Fetch a user's recent tweets via ``bird user-tweets``, filtered to replies only.

    Returns a normalized list of dicts with keys:
    ``id``, ``text``, ``created_at``, ``in_reply_to_user_id``.
    Returns empty list on failure (last_error set).
    """
    handle = handle.lstrip("@").strip()
    if not handle:
        return []
    result = await _run_bird(
        "user-tweets", f"@{handle}", "-n", str(count),
        auth_token=os.getenv("AUTH_TOKEN", ""),
        ct0=os.getenv("CT0", ""),
    )
    tweets = _extract_tweets(result.data)
    out: list[dict[str, Any]] = []
    for t in tweets:
        # Filter to replies only
        in_reply_to = t.get("inReplyToId") or t.get("in_reply_to_user_id")
        if not in_reply_to:
            # Check referenced_tweets for reply type
            refs = t.get("referenced_tweets") or t.get("referencedTweets") or []
            is_reply = any(r.get("type") == "replied_to" for r in refs)
            if not is_reply:
                continue
        tweet_id = t.get("id") or t.get("tweetId") or t.get("_raw", {}).get("rest_id")
        if not tweet_id:
            continue
        out.append({
            "id": str(tweet_id),
            "text": t.get("text") or "",
            "created_at": t.get("createdAt") or t.get("created_at") or "",
            "in_reply_to_user_id": str(in_reply_to) if in_reply_to else "",
        })
    return out
