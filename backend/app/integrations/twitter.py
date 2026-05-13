"""Twitter / X API v2 integration for PingCRM."""
from __future__ import annotations

import asyncio
import logging
import os
import urllib.parse
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.twitter_contacts import (
    _build_twitter_id_to_contact_map,
    _cached_resolve_handles,
)
from app.integrations.twitter_auth import (
    _TOKEN_REFRESH_BUFFER_SECONDS,
    _refresh_and_retry,
    _user_bearer_headers,
    build_twitter_oauth2_url,
    exchange_twitter_code,
    generate_pkce_pair,
    refresh_twitter_token,
    store_tokens,
)
from app.models.contact import Contact
from app.models.user import User
from app.services.contact_resolver import find_or_create_contact_by_twitter_user_id

logger = logging.getLogger(__name__)

AVATARS_DIR = Path(os.environ.get(
    "AVATARS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "static" / "avatars"),
))

_TWITTER_API_BASE = "https://api.twitter.com/2"

ALLOWED_AVATAR_DOMAINS = {"pbs.twimg.com", "abs.twimg.com", "si0.twimg.com"}


def _parse_twitter_ts(ts: str | None) -> datetime:
    """Parse an ISO-8601 timestamp from the Twitter API into a datetime."""
    if not ts:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(UTC)




async def download_twitter_avatar(
    profile_image_url: str, contact_id: uuid.UUID
) -> str | None:
    """Download a Twitter profile image and save to static/avatars/.

    Twitter returns ``_normal`` (48×48) by default; we swap to ``_200x200``
    for a sharper image.  Returns the local URL path, or ``None`` on failure.
    """
    url = profile_image_url.replace("_normal.", "_200x200.")
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname not in ALLOWED_AVATAR_DOMAINS:
        logger.warning(
            "download_twitter_avatar: rejected URL with disallowed domain %r for contact %s",
            parsed.hostname,
            contact_id,
        )
        return None
    try:
        AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{contact_id}.jpg"
        filepath = AVATARS_DIR / filename
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
        return f"/static/avatars/{filename}"
    except Exception:
        logger.debug("Failed to download Twitter avatar for contact %s", contact_id)
    return None


# ---------------------------------------------------------------------------
# Poll contacts
# ---------------------------------------------------------------------------


async def poll_contacts_activity(
    user: User,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """For each contact with a twitter_handle, fetch profile/bio.

    Detects bio changes by comparing the fetched description with the
    contact's ``twitter_bio`` column.  When a change is detected the column
    is updated and a Notification record is created.

    NOTE: Tweet fetching and LLM classification are NOT done here.
    Tweets are fetched on-demand when composing follow-up suggestions
    (see message_composer._fetch_twitter_context with 12h Redis cache).

    Returns:
        A list of activity dicts, one per contact that has a twitter_handle.
    """
    from app.models.notification import Notification
    from app.integrations.bird import fetch_user_profile_bird
    from app.services.bird_session import get_cookies, handle_bird_failure

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user.id,
            Contact.twitter_handle.isnot(None),
            Contact.priority_level != "archived",
        )
    )
    contacts: list[Contact] = list(result.scalars().all())

    activity_records: list[dict[str, Any]] = []

    cookies = get_cookies(user)
    if cookies is None:
        return activity_records  # user hasn't connected bird cookies

    auth_token, ct0 = cookies

    _POLL_CONCURRENCY = 5
    semaphore = asyncio.Semaphore(_POLL_CONCURRENCY)

    async def _poll_contact(contact: Contact) -> dict | None:
        handle = (contact.twitter_handle or "").lstrip("@").strip()
        if not handle:
            return None

        async with semaphore:
            profile, bird_error = await fetch_user_profile_bird(
                handle, auth_token=auth_token, ct0=ct0,
            )
        if bird_error:
            await handle_bird_failure(user, db, bird_error, operation="bios")
            return None

        current_bio = profile.get("description", "")

        # Update location from Twitter profile (respects user-edited fields)
        twitter_location = profile.get("location", "")
        if twitter_location:
            from app.services.sync_utils import sync_set_field
            sync_set_field(contact, "location", twitter_location)

        # Download Twitter avatar if the contact doesn't have one yet
        if not contact.avatar_url:
            image_url = profile.get("profileImageUrl") or profile.get("profile_image_url")
            if image_url:
                avatar_path = await download_twitter_avatar(image_url, contact.id)
                if avatar_path:
                    contact.avatar_url = avatar_path
                    await db.flush()

        stored_bio = contact.twitter_bio or ""
        bio_changed = bool(current_bio and current_bio != stored_bio)

        if bio_changed:
            contact.twitter_bio = current_bio
            # Create a notification for the bio change
            display_name = contact.full_name or handle
            notif = Notification(
                user_id=user.id,
                notification_type="bio_change",
                title=f"@{handle} updated their Twitter bio",
                body=f"{display_name} changed their bio to: {current_bio[:200]}",
                link=f"/contacts/{contact.id}",
            )
            db.add(notif)
            from datetime import UTC, datetime
            from app.models.interaction import Interaction
            db.add(Interaction(
                contact_id=contact.id,
                user_id=user.id,
                platform="twitter",
                direction="event",
                content_preview=f"Bio updated: {current_bio[:500]}",
                raw_reference_id=f"bio_change:twitter:{contact.id}:{datetime.now(UTC).isoformat()}",
                occurred_at=datetime.now(UTC),
            ))
            await db.flush()
        elif current_bio and not contact.twitter_bio:
            # First time we see a bio — store it without notification
            contact.twitter_bio = current_bio
            await db.flush()

        return {
            "contact_id": str(contact.id),
            "twitter_handle": handle,
            "current_bio": current_bio,
            "previous_bio": stored_bio,
            "bio_changed": bio_changed,
        }

    results = await asyncio.gather(*(_poll_contact(c) for c in contacts))
    activity_records = [r for r in results if r is not None]

    return activity_records





# ---------------------------------------------------------------------------
# Mention sync (bird CLI — no OAuth API cost)
# ---------------------------------------------------------------------------


async def sync_twitter_mentions(
    user: User,
    db: AsyncSession,
    *,
    _id_map: dict[str, Contact] | None = None,
    _headers: dict[str, str] | None = None,
) -> int:
    """Sync Twitter mentions via bird CLI. Returns count of new interactions."""
    from app.models.interaction import Interaction
    from app.integrations.bird import fetch_mentions_bird, is_available as bird_available
    from app.services.bird_session import get_cookies, handle_bird_failure

    if not user.twitter_username:
        return 0

    if not bird_available():
        logger.error(
            "sync_twitter_mentions: bird CLI unavailable for user %s",
            user.id,
            extra={"provider": "twitter", "operation": "mentions"},
        )
        from app.models.notification import Notification
        db.add(Notification(
            user_id=user.id,
            notification_type="system",
            title="Twitter mention sync unavailable",
            body="bird CLI is not installed. Mention sync requires bird CLI.",
            link="/settings",
        ))
        await db.flush()
        return 0

    cookies = get_cookies(user)
    if cookies is None:
        # User has not connected bird cookies. Skip silently — settings row
        # already prompts them to connect.
        return 0
    auth_token, ct0 = cookies

    # Read cursor for delta sync
    sync_settings = user.sync_settings or {}
    mention_cursor = sync_settings.get("twitter_mention_cursor")

    mentions, bird_error = await fetch_mentions_bird(
        user.twitter_username, count=50, auth_token=auth_token, ct0=ct0,
    )
    if bird_error:
        await handle_bird_failure(user, db, bird_error, operation="mentions")
        return 0

    if not mentions:
        return 0

    # Apply cursor: only process tweets newer than the last seen ID
    if mention_cursor:
        mentions = [m for m in mentions if m["id"] > mention_cursor]

    if not mentions:
        return 0

    # Build or reuse Twitter user ID -> Contact mapping
    headers = _headers or await _user_bearer_headers(user, db)
    id_to_contact = _id_map if _id_map is not None else await _build_twitter_id_to_contact_map(user, db, headers or {})
    new_count = 0

    # Batch dedup: collect all ref IDs and query once
    all_ref_ids = [f"twitter_mention:{mention.get('id', '')}" for mention in mentions]
    existing_refs: set[str] = set()
    if all_ref_ids:
        dedup_result = await db.execute(
            select(Interaction.raw_reference_id).where(
                Interaction.raw_reference_id.in_(all_ref_ids),
                Interaction.user_id == user.id,
            )
        )
        existing_refs = {row[0] for row in dedup_result.all()}

    for mention in mentions:
        tweet_id = mention.get("id", "")
        author_id = mention.get("author_id", "")
        text = mention.get("text", "")

        if author_id == user.twitter_user_id:
            continue  # Skip self-mentions

        if f"twitter_mention:{tweet_id}" in existing_refs:
            continue

        # Match author to a specific contact by Twitter user ID
        contact = id_to_contact.get(author_id)
        if not contact:
            continue

        interaction = Interaction(
            contact_id=contact.id,
            user_id=user.id,
            platform="twitter",
            direction="inbound",
            content_preview=text[:500] if text else "",
            raw_reference_id=f"twitter_mention:{tweet_id}",
            occurred_at=_parse_twitter_ts(mention.get("created_at")),
        )
        db.add(interaction)
        if contact.last_interaction_at is None or contact.last_interaction_at < interaction.occurred_at:
            contact.last_interaction_at = interaction.occurred_at
        new_count += 1

    # Advance cursor to the newest tweet ID processed
    if mentions:
        newest = max(m["id"] for m in mentions)
        sync_settings = user.sync_settings or {}
        sync_settings["twitter_mention_cursor"] = newest
        user.sync_settings = sync_settings

    await db.flush()
    return new_count


# ---------------------------------------------------------------------------
# Reply sync (bird CLI — no OAuth API cost)
# ---------------------------------------------------------------------------


async def sync_twitter_replies(
    user: User,
    db: AsyncSession,
    *,
    _id_map: dict[str, Contact] | None = None,
    _headers: dict[str, str] | None = None,
) -> int:
    """Sync outbound replies to contacts' tweets via bird CLI. Returns count of new interactions."""
    from app.models.interaction import Interaction
    from app.integrations.bird import fetch_user_replies_bird, is_available as bird_available
    from app.services.bird_session import get_cookies, handle_bird_failure

    if not user.twitter_username:
        return 0

    if not bird_available():
        logger.error(
            "sync_twitter_replies: bird CLI unavailable for user %s",
            user.id,
            extra={"provider": "twitter", "operation": "replies"},
        )
        from app.models.notification import Notification
        db.add(Notification(
            user_id=user.id,
            notification_type="system",
            title="Twitter reply sync unavailable",
            body="bird CLI is not installed. Reply sync requires bird CLI.",
            link="/settings",
        ))
        await db.flush()
        return 0

    cookies = get_cookies(user)
    if cookies is None:
        return 0
    auth_token, ct0 = cookies

    # Read cursor for delta sync
    sync_settings = user.sync_settings or {}
    reply_cursor = sync_settings.get("twitter_reply_cursor")

    replies, bird_error = await fetch_user_replies_bird(
        user.twitter_username, count=50, auth_token=auth_token, ct0=ct0,
    )
    if bird_error:
        await handle_bird_failure(user, db, bird_error, operation="replies")
        return 0

    if not replies:
        return 0

    # Apply cursor: only process tweets newer than the last seen ID
    if reply_cursor:
        replies = [r for r in replies if r["id"] > reply_cursor]

    if not replies:
        return 0

    # Build or reuse Twitter user ID -> Contact mapping
    headers = _headers or await _user_bearer_headers(user, db)
    id_to_contact = _id_map if _id_map is not None else await _build_twitter_id_to_contact_map(user, db, headers or {})
    new_count = 0

    # Batch dedup: collect all ref IDs and query once
    all_ref_ids = [f"twitter_reply:{reply.get('id', '')}" for reply in replies]
    existing_refs: set[str] = set()
    if all_ref_ids:
        dedup_result = await db.execute(
            select(Interaction.raw_reference_id).where(
                Interaction.raw_reference_id.in_(all_ref_ids),
                Interaction.user_id == user.id,
            )
        )
        existing_refs = {row[0] for row in dedup_result.all()}

    for reply in replies:
        tweet_id = reply.get("id", "")
        reply_to_user_id = reply.get("in_reply_to_user_id", "")
        text = reply.get("text", "")

        # Skip self-replies (threads)
        if reply_to_user_id == user.twitter_user_id:
            continue

        # Match to a known contact
        contact = id_to_contact.get(reply_to_user_id)
        if not contact:
            continue

        if f"twitter_reply:{tweet_id}" in existing_refs:
            continue

        interaction = Interaction(
            contact_id=contact.id,
            user_id=user.id,
            platform="twitter",
            direction="outbound",
            content_preview=text[:500] if text else "",
            raw_reference_id=f"twitter_reply:{tweet_id}",
            occurred_at=_parse_twitter_ts(reply.get("created_at")),
        )
        db.add(interaction)
        if contact.last_interaction_at is None or contact.last_interaction_at < interaction.occurred_at:
            contact.last_interaction_at = interaction.occurred_at
        new_count += 1

    # Advance cursor to the newest tweet ID processed
    if replies:
        newest = max(r["id"] for r in replies)
        sync_settings = user.sync_settings or {}
        sync_settings["twitter_reply_cursor"] = newest
        user.sync_settings = sync_settings

    await db.flush()
    return new_count


# DM-sync functions live in twitter_dms.py. Re-export for backwards compat.
from app.integrations.twitter_dms import (  # noqa: E402,F401
    fetch_dm_conversation_with,
    fetch_dm_conversations,
    sync_twitter_contact_dms,
    sync_twitter_dms,
)
