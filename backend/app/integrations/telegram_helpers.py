"""DB lookup/write helpers for the Telegram integration."""
from __future__ import annotations

import re as _re
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction

_TWITTER_URL_RE = _re.compile(
    r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/(@?[\w]{1,15})\b",
    _re.IGNORECASE,
)
_TWITTER_MENTION_RE = _re.compile(r"@([\w]{1,15})\b")


def _extract_twitter_handle(bio: str) -> str | None:
    """Extract a Twitter/X handle from a bio string.

    Looks for twitter.com/handle or x.com/handle URLs first,
    then falls back to @handle mentions near twitter/X keywords.
    """
    # Direct URL match
    m = _TWITTER_URL_RE.search(bio)
    if m:
        handle = m.group(1).lstrip("@")
        if handle.lower() not in {"home", "search", "explore", "settings", "i"}:
            return handle

    # @handle near twitter/X keyword
    bio_lower = bio.lower()
    if any(kw in bio_lower for kw in ("twitter", "tw:", "𝕏", " x:", "x.com")):
        mentions = _TWITTER_MENTION_RE.findall(bio)
        for handle in mentions:
            if handle.lower() not in {"telegram", "email", "phone"}:
                return handle

    return None


async def _find_contact_by_telegram_user_id(
    tg_user_id: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Locate a Contact belonging to *user_id* whose telegram_user_id matches."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.telegram_user_id == tg_user_id,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _find_contact_by_username(
    username: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Locate a Contact belonging to *user_id* whose telegram_username matches."""
    username_lower = username.lower().lstrip("@")
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.telegram_username == username_lower,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _find_contact_by_phone(
    phone: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Locate a Contact belonging to *user_id* whose phones list contains *phone*."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.phones.contains([phone]),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _upsert_interaction(
    *,
    contact: Contact,
    user_id: uuid.UUID,
    message_id: str,
    direction: str,
    content_preview: str | None,
    occurred_at: datetime,
    db: AsyncSession,
    is_read_by_recipient: bool | None = None,
) -> tuple[Interaction, bool]:
    """
    Create an Interaction for *message_id* if it doesn't exist yet.

    Returns a (Interaction, is_new) tuple.
    """
    result = await db.execute(
        select(Interaction).where(
            Interaction.raw_reference_id == message_id,
            Interaction.contact_id == contact.id,
            Interaction.user_id == user_id,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user_id,
        platform="telegram",
        direction=direction,
        content_preview=content_preview[:500] if content_preview else None,
        raw_reference_id=message_id,
        occurred_at=occurred_at,
        is_read_by_recipient=is_read_by_recipient,
    )
    db.add(interaction)
    return interaction, True
