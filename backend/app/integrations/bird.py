"""bird CLI integration — cookie-based Twitter/X data access.

Uses the ``bird`` CLI (@steipete/bird v0.8.0) which authenticates via per-call
cookies passed as ``--auth-token`` and ``--ct0`` CLI flags, bypassing X API
rate limits and credit restrictions.

All public helpers return ``(value, error)`` tuples — callers use the error
string to decide whether to surface a user-facing failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_BIRD_TIMEOUT = 20  # seconds


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
    failure.
    """
    bird_path = shutil.which("bird")
    if not bird_path:
        msg = "bird CLI not found on PATH — Twitter enrichment is unavailable"
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
        logger.warning(msg)
        return BirdResult(data=None, error=msg)
    except OSError as exc:
        msg = f"bird {args[0]}: OS error: {exc}"
        logger.warning(msg)
        return BirdResult(data=None, error=msg)

    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")[:200]
        msg = f"bird {args[0]}: exit code {proc.returncode}: {stderr_text}"
        logger.warning(msg)
        return BirdResult(data=None, error=msg)

    try:
        data = json.loads(stdout.decode())
        return BirdResult(data=data, error=None)
    except (json.JSONDecodeError, ValueError) as exc:
        msg = f"bird {args[0]}: invalid JSON output: {exc}"
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
# Public helpers — all return (value, error) tuples. error is None on success.
# ---------------------------------------------------------------------------


async def resolve_user_id_bird(
    handle: str, *, auth_token: str, ct0: str,
) -> tuple[str | None, str | None]:
    """Resolve a Twitter handle to a numeric user ID. Returns (id, error)."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return None, None
    result = await _run_bird(
        "user-tweets", f"@{handle}", "-n", "1", "--json-full",
        auth_token=auth_token, ct0=ct0,
    )
    if result.error:
        return None, result.error
    tweets = _extract_tweets(result.data)
    if not tweets:
        return None, None
    user = (
        tweets[0].get("_raw", {}).get("core", {}).get("user_results", {}).get("result", {})
    )
    rest_id = user.get("rest_id")
    return (str(rest_id) if rest_id else None), None


async def fetch_user_tweets_bird(
    handle: str, count: int = 5, *, auth_token: str, ct0: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch a user's recent tweets via ``bird user-tweets``."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return [], None
    result = await _run_bird(
        "user-tweets", f"@{handle}", "-n", str(count),
        auth_token=auth_token, ct0=ct0,
    )
    if result.error:
        return [], result.error
    return _extract_tweets(result.data), None


async def fetch_user_profile_bird(
    handle: str, *, auth_token: str, ct0: str,
) -> tuple[dict[str, Any], str | None]:
    """Fetch a user's profile via ``bird user-tweets --json-full``."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return {}, None

    result = await _run_bird(
        "user-tweets", f"@{handle}", "-n", "1", "--json-full",
        auth_token=auth_token, ct0=ct0,
    )
    if result.error:
        return {}, result.error

    out: dict[str, Any] = {}
    tweets = _extract_tweets(result.data)
    if not tweets:
        return out, None

    raw = tweets[0].get("_raw", {})
    user = raw.get("core", {}).get("user_results", {}).get("result", {})
    legacy = user.get("legacy", {})

    bio = user.get("profile_bio", {}).get("description", "")
    if bio:
        out["description"] = bio
    loc = user.get("location", {}).get("location", "")
    if loc:
        out["location"] = loc
    avatar = user.get("avatar", {}).get("image_url", "")
    if avatar:
        avatar_hires = avatar.replace("_normal.", "_400x400.")
        out["profile_image_url"] = avatar_hires
        out["profileImageUrl"] = avatar_hires
    if legacy.get("name"):
        out["name"] = legacy["name"]
    if legacy.get("screen_name"):
        out["username"] = legacy["screen_name"]
    metrics = {}
    for k in ("followers_count", "friends_count", "statuses_count", "listed_count"):
        if legacy.get(k) is not None:
            metrics[k] = legacy[k]
    if metrics:
        out["public_metrics"] = metrics

    return out, None


async def fetch_mentions_bird(
    handle: str, count: int = 50, *, auth_token: str, ct0: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch tweets mentioning a user. Returns (normalized list, error)."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return [], None
    result = await _run_bird(
        "mentions", "-u", f"@{handle}", "-n", str(count),
        auth_token=auth_token, ct0=ct0,
    )
    if result.error:
        return [], result.error
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
    return out, None


async def fetch_user_replies_bird(
    handle: str, count: int = 50, *, auth_token: str, ct0: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch a user's recent replies via ``bird user-tweets``, filtered."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return [], None
    result = await _run_bird(
        "user-tweets", f"@{handle}", "-n", str(count),
        auth_token=auth_token, ct0=ct0,
    )
    if result.error:
        return [], result.error
    tweets = _extract_tweets(result.data)
    out: list[dict[str, Any]] = []
    for t in tweets:
        in_reply_to = t.get("inReplyToId") or t.get("in_reply_to_user_id")
        if not in_reply_to:
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
    return out, None
