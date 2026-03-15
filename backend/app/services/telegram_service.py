"""Telegram service — higher-level orchestration for Telegram API calls."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.user import User


async def get_common_groups_cached(
    contact: Contact,
    current_user: User,
    db: AsyncSession,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Return Telegram groups in common with *contact*, using a 24-hour cache.

    If the cached data on the contact is still fresh (< 24 hours old), it is
    returned directly without calling the Telegram API.  Otherwise, fresh data
    is fetched, persisted to *contact*, and returned.

    Args:
        contact: The contact whose common groups should be retrieved.
        current_user: Authenticated user (must have ``telegram_session``).
        db: Database session.
        force: Bypass the 24h cache and re-fetch from Telegram.

    Returns:
        A list of group dicts as returned by ``fetch_common_groups``.
    """
    now = datetime.now(UTC)

    if not force and (
        contact.telegram_common_groups is not None
        and contact.telegram_groups_fetched_at is not None
        and (now - contact.telegram_groups_fetched_at) < timedelta(hours=24)
    ):
        return contact.telegram_common_groups  # type: ignore[return-value]

    from app.integrations.telegram import fetch_common_groups

    groups, resolved_user_id = await fetch_common_groups(
        current_user,
        telegram_username=contact.telegram_username,
        telegram_user_id=contact.telegram_user_id,
    )

    contact.telegram_common_groups = groups
    contact.telegram_groups_fetched_at = now
    # Cache resolved numeric ID to avoid future rate-limited username lookups
    if resolved_user_id and not contact.telegram_user_id:
        contact.telegram_user_id = resolved_user_id
    await db.flush()

    return groups
