"""Per-user bird cookie state management.

Centralises:
- Reading cookies off the User model for a bird call.
- Running ``verify_cookies`` exactly once per sync run on failure.
- Flipping ``twitter_bird_status`` to ``expired`` + firing a single notification.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.bird import verify_cookies
from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)

# Per-process, per-user-id flag set: "did we already verify this user's cookies
# during the current sync run?". Reset by callers at the start of a sync run.
_verified_this_run: set[str] = set()


def reset_verification_cache() -> None:
    """Clear the per-process verification cache. Call at the start of each sync run."""
    _verified_this_run.clear()


def get_cookies(user: User) -> tuple[str, str] | None:
    """Return (auth_token, ct0) or None if the user has not connected."""
    if user.twitter_bird_auth_token and user.twitter_bird_ct0:
        return user.twitter_bird_auth_token, user.twitter_bird_ct0
    return None


async def handle_bird_failure(
    user: User,
    db: AsyncSession,
    error: str,
    *,
    operation: str,
) -> None:
    """Called once per failed bird call. Flips status to expired if whoami fails.

    Guarantees at most one ``verify_cookies`` + one notification per user per
    sync run, across all bird helpers.
    """
    key = str(user.id)
    if key in _verified_this_run:
        logger.warning(
            "bird %s failed for user %s (already verified this run): %s",
            operation, user.id, error,
            extra={"provider": "twitter", "operation": operation},
        )
        return

    _verified_this_run.add(key)

    cookies = get_cookies(user)
    if cookies is None:
        return

    auth_token, ct0 = cookies
    ok = await verify_cookies(auth_token, ct0)
    user.twitter_bird_checked_at = datetime.now(timezone.utc)

    if ok:
        logger.warning(
            "bird %s failed for user %s but whoami succeeded (transient): %s",
            operation, user.id, error,
            extra={"provider": "twitter", "operation": operation},
        )
        return

    user.twitter_bird_status = "expired"
    logger.error(
        "bird cookies expired for user %s (operation=%s, error=%s)",
        user.id, operation, error,
        extra={"provider": "twitter", "operation": operation},
    )
    db.add(Notification(
        user_id=user.id,
        notification_type="system",
        title="X cookies expired",
        body="Click to reconnect your X account.",
        link="/settings",
    ))
    await db.flush()
