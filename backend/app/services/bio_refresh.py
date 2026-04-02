"""Bio refresh service — fetch updated Twitter and Telegram bios for a contact."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)

_BIO_CHECK_TTL = 604800  # 7 days


async def refresh_contact_bios(
    contact: Contact,
    current_user: User,
    db: AsyncSession,
) -> dict[str, Any]:
    """Fetch updated bios from Twitter and Telegram for *contact*.

    Persists changes to *contact* in place and creates Notification rows when
    a bio has changed from a previously-known value.

    Args:
        contact: The contact whose bios should be refreshed (already loaded).
        current_user: The authenticated user (owner of the contact).
        db: Database session.

    Returns:
        A dict with keys ``twitter_bio_changed`` (bool) and
        ``telegram_bio_changed`` (bool).
    """
    changes: dict[str, Any] = {
        "twitter_bio_changed": False,
        "telegram_bio_changed": False,
    }

    # ------------------------------------------------------------------
    # Twitter bio check
    # ------------------------------------------------------------------
    if contact.twitter_handle:
        try:
            from app.integrations.bird import fetch_user_profile_bird
            from app.integrations.twitter import download_twitter_avatar

            handle = (contact.twitter_handle or "").lstrip("@").strip()
            if handle:
                profile = await fetch_user_profile_bird(handle)
                new_bio = profile.get("description", "")

                # Update location from Twitter profile
                twitter_location = profile.get("location", "")
                if twitter_location and not contact.location:
                    contact.location = twitter_location

                # Download Twitter avatar if the contact doesn't have one
                if not contact.avatar_url:
                    image_url = profile.get("profileImageUrl") or profile.get("profile_image_url")
                    if image_url:
                        avatar_path = await download_twitter_avatar(image_url, contact.id)
                        if avatar_path:
                            contact.avatar_url = avatar_path
                # Reset failure counter on successful fetch
                try:
                    from app.core.config import settings as _settings
                    import redis.asyncio as aioredis
                    _r = aioredis.from_url(_settings.REDIS_URL)
                    await _r.delete(f"twitter_bio_fail:{current_user.id}")
                    await _r.aclose()
                except Exception:
                    logger.exception("Failed to reset Twitter bio failure counter for user %s", current_user.id)

                if new_bio and new_bio != (contact.twitter_bio or ""):
                    old_bio = contact.twitter_bio
                    contact.twitter_bio = new_bio
                    changes["twitter_bio_changed"] = True
                    if old_bio:
                        from datetime import UTC, datetime
                        db.add(Notification(
                            user_id=current_user.id,
                            notification_type="bio_change",
                            title=f"@{handle} updated their Twitter bio",
                            body=(
                                f"{contact.full_name or handle} changed their bio to: "
                                f"{new_bio[:200]}"
                            ),
                            link=f"/contacts/{contact.id}",
                        ))
                        db.add(Interaction(
                            contact_id=contact.id,
                            user_id=current_user.id,
                            platform="twitter",
                            direction="event",
                            content_preview=f"Bio updated: {new_bio[:500]}",
                            raw_reference_id=f"bio_change:twitter:{contact.id}:{datetime.now(UTC).isoformat()}",
                            occurred_at=datetime.now(UTC),
                        ))
        except Exception:
            logger.exception(
                "bio_refresh: Twitter bio fetch failed for contact %s", contact.id
            )
            # Track consecutive failures per user; notify after 3+
            try:
                from app.core.config import settings
                import redis.asyncio as aioredis

                r = aioredis.from_url(settings.REDIS_URL)
                fail_key = f"twitter_bio_fail:{current_user.id}"
                count = await r.incr(fail_key)
                await r.expire(fail_key, 86400)  # 24h TTL
                if count == 3:
                    db.add(Notification(
                        user_id=current_user.id,
                        notification_type="system",
                        title="Twitter profile sync failing",
                        body=f"{count} consecutive Twitter bio fetches have failed. This may indicate an API issue or expired credentials.",
                        link="/settings",
                    ))
                await r.aclose()
            except Exception:
                logger.debug("bio_refresh: failed to update Twitter failure counter for user %s", current_user.id)

    # ------------------------------------------------------------------
    # Telegram bio check
    # ------------------------------------------------------------------
    if contact.telegram_username and current_user.telegram_session:
        try:
            from app.integrations.telegram import make_client, ensure_connected
            from telethon.tl.functions.users import GetFullUserRequest

            username = (contact.telegram_username or "").lstrip("@").strip()
            if username:
                client = make_client(current_user.telegram_session)
                await ensure_connected(client)
                try:
                    input_user = await client.get_input_entity(username)
                    full = await client(GetFullUserRequest(input_user))
                    new_bio = getattr(full.full_user, "about", None) or ""
                    # Extract last seen status
                    from app.integrations.telegram_helpers import _extract_last_seen
                    tg_user = full.users[0] if full.users else None
                    last_seen = _extract_last_seen(tg_user) if tg_user else None
                    if last_seen:
                        contact.telegram_last_seen_at = last_seen
                    # Extract birthday if available
                    if not contact.birthday:
                        bday = getattr(full.full_user, "birthday", None)
                        if bday:
                            day = getattr(bday, "day", None)
                            month = getattr(bday, "month", None)
                            year = getattr(bday, "year", None)
                            if day and month:
                                contact.birthday = (
                                    f"{year}-{month:02d}-{day:02d}" if year
                                    else f"{month:02d}-{day:02d}"
                                )
                    # Extract Twitter handle from Telegram bio if not already set
                    if not contact.twitter_handle and new_bio:
                        from app.integrations.telegram_helpers import _extract_twitter_handle
                        twitter_handle = _extract_twitter_handle(new_bio)
                        if twitter_handle:
                            contact.twitter_handle = twitter_handle

                    if new_bio and new_bio != (contact.telegram_bio or ""):
                        old_bio = contact.telegram_bio
                        contact.telegram_bio = new_bio
                        changes["telegram_bio_changed"] = True
                        if old_bio:
                            from datetime import UTC, datetime
                            db.add(Notification(
                                user_id=current_user.id,
                                notification_type="bio_change",
                                title=f"@{username} updated their Telegram bio",
                                body=(
                                    f"{contact.full_name or username} changed their bio to: "
                                    f"{new_bio[:200]}"
                                ),
                                link=f"/contacts/{contact.id}",
                            ))
                            db.add(Interaction(
                                contact_id=contact.id,
                                user_id=current_user.id,
                                platform="telegram",
                                direction="event",
                                content_preview=f"Bio updated: {new_bio[:500]}",
                                raw_reference_id=f"bio_change:telegram:{contact.id}:{datetime.now(UTC).isoformat()}",
                                occurred_at=datetime.now(UTC),
                            ))
                finally:
                    await client.disconnect()
        except Exception:
            logger.exception(
                "bio_refresh: Telegram bio fetch failed for contact %s", contact.id
            )

    await db.flush()
    return changes
