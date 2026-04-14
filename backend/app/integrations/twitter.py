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

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user.id,
            Contact.twitter_handle.isnot(None),
            Contact.priority_level != "archived",
        )
    )
    contacts: list[Contact] = list(result.scalars().all())

    activity_records: list[dict[str, Any]] = []

    from app.integrations import bird
    from app.integrations.bird import fetch_user_profile_bird

    bird.last_error = None  # reset before batch

    _POLL_CONCURRENCY = 5
    semaphore = asyncio.Semaphore(_POLL_CONCURRENCY)

    async def _poll_contact(contact: Contact) -> dict | None:
        handle = (contact.twitter_handle or "").lstrip("@").strip()
        if not handle:
            return None

        async with semaphore:
            profile = await fetch_user_profile_bird(handle)

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
# DM sync
# ---------------------------------------------------------------------------


MAX_DM_PAGES = 15  # safety cap: 15 pages * 100 = up to 1500 events


async def fetch_dm_conversations(
    headers: dict[str, str],
    *,
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch DM events using OAuth 2.0 user token (Twitter API v2).

    Args:
        headers: Bearer token headers.
        since_id: Only return events newer than this DM event ID (delta sync).
                  If None, fetches all available (up to ~30 days).
    """
    all_events: list[dict[str, Any]] = []
    pagination_token: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in range(MAX_DM_PAGES):
            params: dict[str, str] = {
                "dm_event.fields": "created_at,sender_id,text,dm_conversation_id,participant_ids",
                "event_types": "MessageCreate",
                "max_results": "100",
            }
            if since_id:
                params["since_id"] = since_id
            if pagination_token:
                params["pagination_token"] = pagination_token

            resp = await client.get(
                f"{_TWITTER_API_BASE}/dm_events",
                headers=headers,
                params=params,
            )
            if resp.status_code != 200:
                body = resp.json()
                error_detail = body.get("detail") or body.get("title") or str(body)
                logger.warning("fetch_dm_conversations: HTTP %s — %s", resp.status_code, error_detail)

                # 400 with since_id: cursor may be stale — retry without it
                if resp.status_code == 400 and since_id:
                    logger.info("fetch_dm_conversations: retrying without since_id (stale cursor)")
                    since_id = None
                    pagination_token = None
                    all_events.clear()
                    continue

                # Raise HTTPStatusError so the task's 401 handler can catch and refresh
                raise httpx.HTTPStatusError(
                    message=f"Twitter DM API error ({resp.status_code}): {error_detail}",
                    request=resp.request,
                    response=resp,
                )
            body = resp.json()

            events = body.get("data", [])
            all_events.extend(events)

            pagination_token = body.get("meta", {}).get("next_token")
            if not pagination_token:
                break

            logger.debug("fetch_dm_conversations: page %d fetched %d events, continuing...", page + 1, len(events))

    logger.info("fetch_dm_conversations: fetched %d DM events total", len(all_events))
    return all_events


async def _lookup_twitter_users_by_ids(
    ids: list[str], headers: dict[str, str]
) -> dict[str, dict[str, str]]:
    """Batch lookup Twitter users by IDs. Returns {id: {username, name}}."""
    if not ids:
        return {}
    result: dict[str, dict[str, str]] = {}
    # API allows up to 100 per request
    for i in range(0, len(ids), 100):
        batch = ids[i : i + 100]
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{_TWITTER_API_BASE}/users",
                    headers=headers,
                    params={"ids": ",".join(batch), "user.fields": "name,username"},
                )
                resp.raise_for_status()
                for u in resp.json().get("data", []):
                    result[u["id"]] = {"username": u.get("username", ""), "name": u.get("name", "")}
        except Exception:
            logger.exception("_lookup_twitter_users_by_ids: failed for batch starting at %d", i)
    return result


from app.integrations.twitter_contacts import (
    _build_twitter_id_to_contact_map,
    _cached_resolve_handles,
)


async def sync_twitter_dms(
    user: User,
    db: AsyncSession,
    *,
    _id_map: dict[str, Contact] | None = None,
    _headers: dict[str, str] | None = None,
) -> int:
    """Sync Twitter DMs for a user. Returns count of new interactions."""
    from app.models.interaction import Interaction

    headers = _headers or await _user_bearer_headers(user, db)
    if not headers:
        logger.info("sync_twitter_dms: no valid Twitter token for user %s", user.id)
        return 0

    # Get user's own Twitter ID
    if not user.twitter_user_id:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_TWITTER_API_BASE}/users/me", headers=headers)
                resp.raise_for_status()
                user.twitter_user_id = resp.json()["data"]["id"]
                await db.flush()
        except httpx.HTTPStatusError:
            # Re-raise HTTP errors (401/403) so the task's retry/refresh logic can handle them
            raise
        except Exception:
            logger.exception("sync_twitter_dms: failed to get user's Twitter ID")
            return 0

    dm_events = await fetch_dm_conversations(headers, since_id=user.twitter_dm_cursor)
    if not dm_events:
        logger.info("sync_twitter_dms: no new DM events for user %s (cursor: %s)", user.id, user.twitter_dm_cursor)
        return 0

    logger.info("sync_twitter_dms: processing %d DM events for user %s (cursor: %s)", len(dm_events), user.id, user.twitter_dm_cursor)

    # Build or reuse Twitter user ID -> Contact mapping
    id_to_contact = _id_map if _id_map is not None else await _build_twitter_id_to_contact_map(user, db, headers)
    logger.info("sync_twitter_dms: contact map has %d entries", len(id_to_contact))
    new_count = 0
    created_contacts = 0
    skipped_duplicate = 0
    _pending_create: dict[str, list[dict]] = {}  # twitter_id -> events

    # Batch dedup: collect all ref IDs and query once
    all_ref_ids = [f"twitter_dm:{event.get('id', '')}" for event in dm_events]
    existing_refs: set[str] = set()
    if all_ref_ids:
        dedup_result = await db.execute(
            select(Interaction.raw_reference_id).where(
                Interaction.raw_reference_id.in_(all_ref_ids),
                Interaction.user_id == user.id,
            )
        )
        existing_refs = {row[0] for row in dedup_result.all()}

    for event in dm_events:
        event_id = event.get("id", "")
        sender_id = event.get("sender_id", "")
        text = event.get("text", "")

        # Determine direction
        direction = "outbound" if sender_id == user.twitter_user_id else "inbound"

        # Find the other participant's Twitter user ID
        participant_id = sender_id if direction == "inbound" else ""
        if not participant_id or participant_id == user.twitter_user_id:
            # Try participant_ids field (group DMs)
            participant_ids = event.get("participant_ids", [])
            for pid in participant_ids:
                if pid != user.twitter_user_id:
                    participant_id = pid
                    break
        if not participant_id or participant_id == user.twitter_user_id:
            # Extract from dm_conversation_id (format: "{id1}-{id2}" for 1:1 DMs)
            convo_id = event.get("dm_conversation_id", "")
            parts = convo_id.split("-") if convo_id else []
            if len(parts) == 2:
                for part in parts:
                    if part != user.twitter_user_id:
                        participant_id = part
                        break
        if not participant_id or participant_id == user.twitter_user_id:
            continue

        ref_id = f"twitter_dm:{event_id}"
        if ref_id in existing_refs:
            skipped_duplicate += 1
            # Still reconcile last_interaction_at for duplicates
            contact = id_to_contact.get(participant_id)
            if contact:
                # Fetch occurred_at from the event itself (no extra DB query needed)
                occurred_at = _parse_twitter_ts(event.get("created_at"))
                if contact.last_interaction_at is None or contact.last_interaction_at < occurred_at:
                    contact.last_interaction_at = occurred_at
            continue

        # Match participant to a specific contact by Twitter user ID
        contact = id_to_contact.get(participant_id)
        if not contact:
            # Auto-create contact — collect ID for batch lookup later
            if participant_id not in _pending_create:
                _pending_create[participant_id] = []
            _pending_create[participant_id].append(event)
            continue

        interaction = Interaction(
            contact_id=contact.id,
            user_id=user.id,
            platform="twitter",
            direction=direction,
            content_preview=text[:500] if text else "",
            raw_reference_id=ref_id,
            occurred_at=_parse_twitter_ts(event.get("created_at")),
        )
        db.add(interaction)
        # Only update if this interaction is more recent
        if contact.last_interaction_at is None or contact.last_interaction_at < interaction.occurred_at:
            contact.last_interaction_at = interaction.occurred_at
        new_count += 1

    # Auto-create contacts for unmatched participants
    if _pending_create:
        profiles = await _lookup_twitter_users_by_ids(list(_pending_create.keys()), headers)
        for twitter_id, events in _pending_create.items():
            profile = profiles.get(twitter_id, {})
            username = profile.get("username", "")
            name = profile.get("name", "")

            # Create a new contact
            parts = name.split(None, 1) if name else []
            contact = Contact(
                user_id=user.id,
                given_name=parts[0] if parts else username or twitter_id,
                family_name=parts[1] if len(parts) > 1 else None,
                full_name=name or username or None,
                twitter_handle=username or None,
                twitter_user_id=twitter_id,
                source="twitter",
            )
            db.add(contact)
            await db.flush()
            created_contacts += 1
            id_to_contact[twitter_id] = contact

            # Now create interactions for this contact's events
            for ev in events:
                ev_id = ev.get("id", "")
                if f"twitter_dm:{ev_id}" in existing_refs:
                    continue
                sender_id = ev.get("sender_id", "")
                direction = "outbound" if sender_id == user.twitter_user_id else "inbound"
                interaction = Interaction(
                    contact_id=contact.id,
                    user_id=user.id,
                    platform="twitter",
                    direction=direction,
                    content_preview=(ev.get("text", "") or "")[:500],
                    raw_reference_id=f"twitter_dm:{ev_id}",
                    occurred_at=_parse_twitter_ts(ev.get("created_at")),
                )
                db.add(interaction)
                # Only update if this interaction is more recent
                if contact.last_interaction_at is None or contact.last_interaction_at < interaction.occurred_at:
                    contact.last_interaction_at = interaction.occurred_at
                new_count += 1

    # Update cursor to the newest event ID so next sync only fetches new DMs
    newest_id = max((e.get("id", "") for e in dm_events), default=None)
    if newest_id:
        user.twitter_dm_cursor = newest_id

    await db.flush()
    logger.info(
        "sync_twitter_dms for user %s: %d new interactions, %d new contacts, %d duplicate (of %d events), cursor: %s",
        user.id, new_count, created_contacts, skipped_duplicate, len(dm_events), newest_id,
    )
    return {"new_interactions": new_count, "new_contacts": created_contacts}


async def fetch_dm_conversation_with(
    participant_id: str, headers: dict[str, str]
) -> list[dict[str, Any]]:
    """Fetch DM events with a specific user using Twitter API v2.

    Uses GET /2/dm_conversations/with/:participant_id/dm_events
    which returns DMs for a 1-on-1 conversation. Paginates up to MAX_DM_PAGES.
    """
    all_events: list[dict[str, Any]] = []
    pagination_token: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in range(MAX_DM_PAGES):
            params: dict[str, str] = {
                "dm_event.fields": "created_at,sender_id,text,dm_conversation_id,participant_ids",
                "event_types": "MessageCreate",
                "max_results": "100",
            }
            if pagination_token:
                params["pagination_token"] = pagination_token

            resp = await client.get(
                f"{_TWITTER_API_BASE}/dm_conversations/with/{participant_id}/dm_events",
                headers=headers,
                params=params,
            )
            body = resp.json()
            if resp.status_code != 200:
                error_detail = body.get("detail") or body.get("title") or str(body)
                logger.warning("fetch_dm_conversation_with: HTTP %s — %s", resp.status_code, error_detail)
                if resp.status_code == 401:
                    raise httpx.HTTPStatusError("Unauthorized", request=resp.request, response=resp)
                break

            events = body.get("data", [])
            all_events.extend(events)

            pagination_token = body.get("meta", {}).get("next_token")
            if not pagination_token:
                break

    logger.info("fetch_dm_conversation_with(%s): fetched %d DM events", participant_id, len(all_events))
    return all_events


async def sync_twitter_contact_dms(
    user: User, contact: "Contact", db: AsyncSession
) -> dict[str, Any]:
    """Sync Twitter DMs for a single *contact*.

    Uses the per-conversation DM endpoint when the contact's twitter_user_id
    is known, falling back to the global DM fetch + filter approach.

    Returns ``{"new_interactions": N}``.
    """
    from app.models.interaction import Interaction

    headers = await _user_bearer_headers(user, db)
    if not headers:
        return {"new_interactions": 0, "skipped": True, "reason": "twitter_not_connected"}

    # Ensure we have the user's own Twitter ID
    if not user.twitter_user_id:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_TWITTER_API_BASE}/users/me", headers=headers)
                resp.raise_for_status()
                user.twitter_user_id = resp.json()["data"]["id"]
                await db.flush()
        except Exception:
            logger.exception("sync_twitter_contact_dms: failed to get user's Twitter ID")
            return {"new_interactions": 0, "skipped": True, "reason": "cannot_get_user_id"}

    # Resolve contact's twitter_user_id if missing
    contact_twitter_id = contact.twitter_user_id
    if not contact_twitter_id and contact.twitter_handle:
        handle = contact.twitter_handle.lstrip("@").strip().lower()
        handle_map = await _cached_resolve_handles([handle], headers)
        resolved = handle_map.get(handle)
        if resolved:
            contact.twitter_user_id = resolved
            contact_twitter_id = resolved
            await db.flush()

    if not contact_twitter_id:
        return {"new_interactions": 0, "skipped": True, "reason": "no_twitter_id"}

    import re
    if not re.fullmatch(r"\d+", contact_twitter_id):
        return {"new_interactions": 0, "skipped": True, "reason": "invalid_twitter_id"}

    # Use per-conversation endpoint (more efficient, targeted)
    try:
        dm_events = await fetch_dm_conversation_with(contact_twitter_id, headers)
    except httpx.HTTPStatusError:
        # Token may be expired — try refresh
        headers = await _refresh_and_retry(user, db)
        if not headers:
            return {"new_interactions": 0, "skipped": True, "reason": "auth_failed"}
        dm_events = await fetch_dm_conversation_with(contact_twitter_id, headers)

    if not dm_events:
        return {"new_interactions": 0}

    # Batch dedup: collect all ref IDs and query once
    all_ref_ids = [f"twitter_dm:{event.get('id', '')}" for event in dm_events]
    existing_refs: set[str] = set()
    if all_ref_ids:
        dedup_result = await db.execute(
            select(Interaction.raw_reference_id).where(
                Interaction.raw_reference_id.in_(all_ref_ids),
                Interaction.user_id == user.id,
            )
        )
        existing_refs = {row[0] for row in dedup_result.all()}

    new_count = 0
    for event in dm_events:
        event_id = event.get("id", "")
        sender_id = event.get("sender_id", "")
        text = event.get("text", "")

        direction = "outbound" if sender_id == user.twitter_user_id else "inbound"

        # Determine participant — same logic as sync_twitter_dms
        participant_id = sender_id if direction == "inbound" else ""
        if not participant_id or participant_id == user.twitter_user_id:
            participant_ids = event.get("participant_ids", [])
            for pid in participant_ids:
                if pid != user.twitter_user_id:
                    participant_id = pid
                    break
        if not participant_id or participant_id == user.twitter_user_id:
            convo_id = event.get("dm_conversation_id", "")
            parts = convo_id.split("-") if convo_id else []
            if len(parts) == 2:
                for part in parts:
                    if part != user.twitter_user_id:
                        participant_id = part
                        break

        # Only keep events involving this specific contact
        if participant_id != contact_twitter_id:
            continue

        # Dedup via batch set lookup
        if f"twitter_dm:{event_id}" in existing_refs:
            continue

        interaction = Interaction(
            contact_id=contact.id,
            user_id=user.id,
            platform="twitter",
            direction=direction,
            content_preview=text[:500] if text else "",
            raw_reference_id=f"twitter_dm:{event_id}",
            occurred_at=_parse_twitter_ts(event.get("created_at")),
        )
        db.add(interaction)
        if contact.last_interaction_at is None or contact.last_interaction_at < interaction.occurred_at:
            contact.last_interaction_at = interaction.occurred_at
        new_count += 1

    await db.flush()
    logger.info(
        "sync_twitter_contact_dms: contact %s — %d new interaction(s).",
        contact.id, new_count,
    )
    return {"new_interactions": new_count}


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
    import app.integrations.bird as bird_module

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

    # Read cursor for delta sync
    sync_settings = user.sync_settings or {}
    reply_cursor = sync_settings.get("twitter_reply_cursor")

    replies = await fetch_user_replies_bird(user.twitter_username, count=50)
    if not replies and bird_module.last_error:
        logger.error(
            "sync_twitter_replies: bird CLI failed for user %s: %s",
            user.id,
            bird_module.last_error,
            extra={"provider": "twitter", "operation": "replies"},
        )
        from app.models.notification import Notification
        db.add(Notification(
            user_id=user.id,
            notification_type="system",
            title="Twitter reply sync failed",
            body=f"bird CLI error: {bird_module.last_error[:200]}",
            link="/settings",
        ))
        await db.flush()
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
