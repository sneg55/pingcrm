"""Twitter / X API v2 integration for Ping CRM."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.user import User

logger = logging.getLogger(__name__)

AVATARS_DIR = Path(os.environ.get(
    "AVATARS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "static" / "avatars"),
))

_TWITTER_API_BASE = "https://api.twitter.com/2"


def _parse_twitter_ts(ts: str | None) -> datetime:
    """Parse an ISO-8601 timestamp from the Twitter API into a datetime."""
    if not ts:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(UTC)


# ---------------------------------------------------------------------------
# OAuth 1.0a helpers
# ---------------------------------------------------------------------------


def _percent_encode(value: str) -> str:
    return quote(str(value), safe="")


def _build_oauth_header(
    method: str,
    url: str,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Build an OAuth 1.0a Authorization header string."""
    nonce = base64.b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")
    timestamp = str(int(time.time()))

    oauth_params: dict[str, str] = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }

    all_params = {**oauth_params, **(extra_params or {})}
    sorted_params = sorted(all_params.items())
    param_string = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_params
    )

    base_string = "&".join([
        _percent_encode(method.upper()),
        _percent_encode(url),
        _percent_encode(param_string),
    ])

    signing_key = f"{_percent_encode(api_secret)}&{_percent_encode(access_token_secret)}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode("ascii"), base_string.encode("ascii"), hashlib.sha1).digest()
    ).decode("ascii")

    oauth_params["oauth_signature"] = signature
    header_parts = ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def build_twitter_client(
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str = "",
) -> httpx.AsyncClient:
    """Return an httpx.AsyncClient pre-configured with Twitter OAuth 1.0a credentials.

    The client stores the credentials as custom headers so callers can retrieve
    them when constructing per-request OAuth signatures.  Bearer token (app-only)
    auth is also supported by setting a ``Authorization: Bearer …`` header directly.
    """
    # For app-only auth (read-only endpoints) we can use Bearer token derived
    # from api_key + api_secret.
    client = httpx.AsyncClient(
        base_url=_TWITTER_API_BASE,
        headers={"User-Agent": "PingCRM/1.0"},
        timeout=30.0,
    )
    # Store credentials on client for later use.
    client._pingcrm_oauth = {  # type: ignore[attr-defined]
        "api_key": api_key,
        "api_secret": api_secret,
        "access_token": access_token,
        "access_token_secret": access_token_secret,
    }
    return client




async def download_twitter_avatar(
    profile_image_url: str, contact_id: uuid.UUID
) -> str | None:
    """Download a Twitter profile image and save to static/avatars/.

    Twitter returns ``_normal`` (48×48) by default; we swap to ``_200x200``
    for a sharper image.  Returns the local URL path, or ``None`` on failure.
    """
    url = profile_image_url.replace("_normal.", "_200x200.")
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
    """For each contact with a twitter_handle, fetch recent tweets and bio.

    Detects bio changes by comparing the fetched description with the
    contact's ``twitter_bio`` column.  When a change is detected the column
    is updated and a Notification record is created.

    Returns:
        A list of activity dicts, one per contact that has a twitter_handle.
    """
    from app.models.notification import Notification

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user.id,
            Contact.twitter_handle.isnot(None),
        )
    )
    contacts: list[Contact] = list(result.scalars().all())

    activity_records: list[dict[str, Any]] = []

    from app.integrations import bird
    from app.integrations.bird import fetch_user_tweets_bird, fetch_user_profile_bird

    bird.last_error = None  # reset before batch

    for contact in contacts:
        handle = (contact.twitter_handle or "").lstrip("@").strip()
        if not handle:
            continue

        tweets = await fetch_user_tweets_bird(handle)
        profile = await fetch_user_profile_bird(handle)
        current_bio = profile.get("description", "")

        # Update location from Twitter profile
        twitter_location = profile.get("location", "")
        if twitter_location and not contact.location:
            contact.location = twitter_location

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
            await db.flush()
        elif current_bio and not contact.twitter_bio:
            # First time we see a bio — store it without notification
            contact.twitter_bio = current_bio
            await db.flush()

        activity_records.append({
            "contact_id": str(contact.id),
            "twitter_handle": handle,
            "tweets": tweets,
            "current_bio": current_bio,
            "previous_bio": stored_bio,
            "bio_changed": bio_changed,
        })

    return activity_records


async def sync_twitter_bios(user: User, db: AsyncSession) -> dict[str, int]:
    """Fetch and store Twitter bios for all contacts with a twitter_handle.

    Creates notifications for bio changes. Returns counts.
    """
    from app.models.notification import Notification

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user.id,
            Contact.twitter_handle.isnot(None),
        )
    )
    contacts: list[Contact] = list(result.scalars().all())

    updated = 0
    bio_changes = 0

    for contact in contacts:
        handle = (contact.twitter_handle or "").lstrip("@").strip()
        if not handle:
            continue

        from app.integrations.bird import fetch_user_profile_bird
        profile = await fetch_user_profile_bird(handle)
        current_bio = profile.get("description", "")

        # Update location from Twitter profile
        twitter_location = profile.get("location", "")
        if twitter_location and not contact.location:
            contact.location = twitter_location

        if not current_bio:
            continue

        stored_bio = contact.twitter_bio or ""

        if current_bio != stored_bio:
            had_previous = bool(stored_bio)
            contact.twitter_bio = current_bio
            updated += 1

            if had_previous:
                bio_changes += 1
                display_name = contact.full_name or handle
                notif = Notification(
                    user_id=user.id,
                    notification_type="bio_change",
                    title=f"@{handle} updated their Twitter bio",
                    body=f"{display_name} changed their bio to: {current_bio[:200]}",
                    link=f"/contacts/{contact.id}",
                )
                db.add(notif)

    if updated:
        await db.flush()

    logger.info(
        "sync_twitter_bios for user %s: %d updated, %d bio changes.",
        user.id, updated, bio_changes,
    )
    return {"bios_updated": updated, "bio_changes": bio_changes}


# ---------------------------------------------------------------------------
# OAuth 2.0 PKCE helpers
# ---------------------------------------------------------------------------

import hashlib as _hashlib
import secrets as _secrets


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for OAuth 2.0 PKCE."""
    verifier = _secrets.token_urlsafe(64)[:128]
    digest = _hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_twitter_oauth2_url(state: str, code_challenge: str) -> str:
    """Build the Twitter OAuth 2.0 authorization URL (PKCE flow)."""
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": settings.TWITTER_CLIENT_ID,
        "redirect_uri": settings.TWITTER_REDIRECT_URI,
        "scope": "tweet.read users.read dm.read offline.access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"https://twitter.com/i/oauth2/authorize?{urlencode(params)}"


async def exchange_twitter_code(code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange an authorization code for OAuth 2.0 tokens."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.twitter.com/2/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.TWITTER_REDIRECT_URI,
                "code_verifier": code_verifier,
                "client_id": settings.TWITTER_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(settings.TWITTER_CLIENT_ID, settings.TWITTER_CLIENT_SECRET)
            if settings.TWITTER_CLIENT_SECRET
            else None,
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_twitter_token(refresh_token: str) -> dict[str, Any]:
    """Refresh an expired OAuth 2.0 access token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.twitter.com/2/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.TWITTER_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(settings.TWITTER_CLIENT_ID, settings.TWITTER_CLIENT_SECRET)
            if settings.TWITTER_CLIENT_SECRET
            else None,
        )
        resp.raise_for_status()
        return resp.json()


async def _user_bearer_headers(user: User, db: AsyncSession) -> dict[str, str] | None:
    """Get Bearer headers using user's OAuth 2.0 token, refreshing if needed.

    Creates a system notification when token refresh fails so the user
    knows to reconnect Twitter in Settings.
    """
    if not user.twitter_access_token:
        return None

    headers = {"Authorization": f"Bearer {user.twitter_access_token}"}

    # Try a simple /users/me call to check validity
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_TWITTER_API_BASE}/users/me", headers=headers)
            if resp.status_code == 200:
                return headers
    except Exception:
        pass

    # Token expired — refresh
    if not user.twitter_refresh_token:
        from app.models.notification import Notification
        db.add(Notification(
            user_id=user.id,
            notification_type="system",
            title="Twitter connection expired",
            body="Your Twitter access token has expired and no refresh token is available. Please reconnect in Settings.",
            link="/settings",
        ))
        await db.flush()
        return None

    try:
        tokens = await refresh_twitter_token(user.twitter_refresh_token)
        user.twitter_access_token = tokens["access_token"]
        if "refresh_token" in tokens:
            user.twitter_refresh_token = tokens["refresh_token"]
        await db.flush()
        return {"Authorization": f"Bearer {tokens['access_token']}"}
    except Exception:
        logger.exception("Failed to refresh Twitter token for user %s", user.id)
        from app.models.notification import Notification
        db.add(Notification(
            user_id=user.id,
            notification_type="system",
            title="Twitter connection expired",
            body="Failed to refresh your Twitter token. Please reconnect in Settings to restore Twitter sync.",
            link="/settings",
        ))
        await db.flush()
        return None


# ---------------------------------------------------------------------------
# DM sync
# ---------------------------------------------------------------------------


MAX_DM_PAGES = 15  # safety cap: 15 pages * 100 = up to 1500 events


async def fetch_dm_conversations(headers: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch DM events using OAuth 2.0 user token (Twitter API v2).

    Paginates through all available pages (up to ~30 days of history).
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
                f"{_TWITTER_API_BASE}/dm_events",
                headers=headers,
                params=params,
            )
            body = resp.json()
            if resp.status_code != 200:
                error_detail = body.get("detail") or body.get("title") or str(body)
                logger.warning("fetch_dm_conversations: HTTP %s — %s", resp.status_code, error_detail)
                raise RuntimeError(f"Twitter DM API error ({resp.status_code}): {error_detail}")

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
            logger.warning("_lookup_twitter_users_by_ids: failed for batch starting at %d", i)
    return result


_HANDLE_CACHE_TTL = 30 * 24 * 3600  # 30 days


async def _cached_resolve_handles(
    handles: list[str], headers: dict[str, str]
) -> dict[str, str]:
    """Resolve Twitter handles to user IDs using Redis cache + batch API.

    Returns {handle_lower: twitter_id}.  Cached for 30 days per handle.
    """
    from app.core.redis import get_redis

    if not handles:
        return {}

    redis = get_redis()
    result: dict[str, str] = {}
    uncached: list[str] = []

    # Check cache first
    cache_keys = [f"tw:h2id:{h.lower()}" for h in handles]
    cached_values = await redis.mget(cache_keys)
    for handle, value in zip(handles, cached_values):
        if value is not None:
            decoded = value.decode() if isinstance(value, bytes) else value
            if decoded:  # non-empty means resolved
                result[handle.lower()] = decoded
            # empty string means previously unresolvable — skip API call
        else:
            uncached.append(handle)

    # Primary: resolve via bird CLI (concurrent batches, no API credits needed)
    from app.integrations.bird import is_available as bird_available, resolve_user_id_bird

    still_unresolved: list[str] = []
    if bird_available():
        _BIRD_CONCURRENCY = 5
        for i in range(0, len(uncached), _BIRD_CONCURRENCY):
            chunk = uncached[i : i + _BIRD_CONCURRENCY]
            resolved = await asyncio.gather(
                *(resolve_user_id_bird(h) for h in chunk)
            )
            for handle, twitter_id in zip(chunk, resolved):
                if twitter_id:
                    result[handle.lower()] = twitter_id
                    await redis.set(f"tw:h2id:{handle.lower()}", twitter_id, ex=_HANDLE_CACHE_TTL)
                else:
                    still_unresolved.append(handle)
    else:
        still_unresolved = uncached

    # Fallback: batch resolve remaining via Twitter API (if bird missed any)
    for i in range(0, len(still_unresolved), 100):
        batch = still_unresolved[i : i + 100]
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{_TWITTER_API_BASE}/users/by",
                    headers=headers,
                    params={"usernames": ",".join(batch), "user.fields": "username"},
                )
                resp.raise_for_status()
                for u in resp.json().get("data", []):
                    username = u.get("username", "").lower()
                    twitter_id = u["id"]
                    result[username] = twitter_id
                    await redis.set(f"tw:h2id:{username}", twitter_id, ex=_HANDLE_CACHE_TTL)
        except Exception:
            logger.warning("_cached_resolve_handles: API fallback failed at offset %d", i)
            continue

        # Cache misses as empty string so we don't re-query
        resolved_in_batch = {h.lower() for h in batch if h.lower() in result}
        for handle in batch:
            if handle.lower() not in resolved_in_batch:
                await redis.set(f"tw:h2id:{handle.lower()}", "", ex=_HANDLE_CACHE_TTL)

    return result


async def _build_twitter_id_to_contact_map(
    user: User, db: AsyncSession, headers: dict[str, str]
) -> dict[str, Contact]:
    """Build a mapping of Twitter user ID -> Contact for all contacts with twitter_handle.

    Uses stored twitter_user_id when available; only resolves handles that
    haven't been resolved yet, then persists the result.
    """
    result = await db.execute(
        select(Contact).where(Contact.user_id == user.id, Contact.twitter_handle.isnot(None))
    )
    contacts = list(result.scalars().all())

    id_map: dict[str, Contact] = {}
    needs_resolve: dict[str, list[Contact]] = {}  # handle -> contacts

    for contact in contacts:
        # Use stored ID if available
        if contact.twitter_user_id:
            id_map[contact.twitter_user_id] = contact
            continue
        handle = (contact.twitter_handle or "").lstrip("@").strip().lower()
        if handle:
            needs_resolve.setdefault(handle, []).append(contact)

    # Batch resolve only the handles we don't have IDs for
    if needs_resolve:
        handle_to_id = await _cached_resolve_handles(list(needs_resolve.keys()), headers)
        for handle, twitter_id in handle_to_id.items():
            for contact in needs_resolve.get(handle, []):
                contact.twitter_user_id = twitter_id
                id_map[twitter_id] = contact
        await db.flush()

    return id_map


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
        except Exception:
            logger.exception("sync_twitter_dms: failed to get user's Twitter ID")
            return 0

    dm_events = await fetch_dm_conversations(headers)
    if not dm_events:
        logger.info("sync_twitter_dms: no DM events returned for user %s", user.id)
        return 0

    logger.info("sync_twitter_dms: processing %d DM events for user %s", len(dm_events), user.id)

    # Build or reuse Twitter user ID -> Contact mapping
    id_to_contact = _id_map if _id_map is not None else await _build_twitter_id_to_contact_map(user, db, headers)
    logger.info("sync_twitter_dms: contact map has %d entries", len(id_to_contact))
    new_count = 0
    created_contacts = 0
    skipped_duplicate = 0
    _pending_create: dict[str, list[dict]] = {}  # twitter_id -> events

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

        # Check if interaction already exists
        existing = await db.execute(
            select(Interaction).where(Interaction.raw_reference_id == f"twitter_dm:{event_id}")
        )
        existing_interaction = existing.scalar_one_or_none()
        if existing_interaction:
            skipped_duplicate += 1
            # Still reconcile last_interaction_at for duplicates
            contact = id_to_contact.get(participant_id)
            if contact and existing_interaction.occurred_at:
                if contact.last_interaction_at is None or contact.last_interaction_at < existing_interaction.occurred_at:
                    contact.last_interaction_at = existing_interaction.occurred_at
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
            raw_reference_id=f"twitter_dm:{event_id}",
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
                existing = await db.execute(
                    select(Interaction).where(Interaction.raw_reference_id == f"twitter_dm:{ev_id}")
                )
                if existing.scalar_one_or_none():
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

    await db.flush()
    logger.info(
        "sync_twitter_dms for user %s: %d new interactions, %d new contacts, %d duplicate (of %d events)",
        user.id, new_count, created_contacts, skipped_duplicate, len(dm_events),
    )
    return {"new_interactions": new_count, "new_contacts": created_contacts}


async def sync_twitter_contact_dms(
    user: User, contact: "Contact", db: AsyncSession
) -> dict[str, Any]:
    """Sync Twitter DMs for a single *contact*.

    Fetches all DM events, filters to those involving the contact's
    twitter_user_id, and creates/deduplicates Interaction rows.

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

    dm_events = await fetch_dm_conversations(headers)
    if not dm_events:
        return {"new_interactions": 0}

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

        # Dedup
        existing = await db.execute(
            select(Interaction).where(Interaction.raw_reference_id == f"twitter_dm:{event_id}")
        )
        if existing.scalar_one_or_none():
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
# Mention sync
# ---------------------------------------------------------------------------


async def fetch_mentions(
    twitter_user_id: str,
    headers: dict[str, str],
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch mentions for user using OAuth 2.0, with pagination."""
    all_mentions: list[dict[str, Any]] = []
    pagination_token: str | None = None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(MAX_DM_PAGES):
                params: dict[str, str] = {
                    "tweet.fields": "created_at,author_id,text",
                    "max_results": "100",
                }
                if since_id:
                    params["since_id"] = since_id
                if pagination_token:
                    params["pagination_token"] = pagination_token

                resp = await client.get(
                    f"{_TWITTER_API_BASE}/users/{twitter_user_id}/mentions",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()
                all_mentions.extend(body.get("data", []))

                pagination_token = body.get("meta", {}).get("next_token")
                if not pagination_token:
                    break

        return all_mentions
    except httpx.HTTPStatusError as exc:
        logger.warning("fetch_mentions: HTTP %s — %s", exc.response.status_code, exc.response.text)
        return all_mentions  # return what we got so far
    except Exception:
        logger.exception("fetch_mentions: unexpected error.")
        return all_mentions


async def sync_twitter_mentions(
    user: User,
    db: AsyncSession,
    *,
    _id_map: dict[str, Contact] | None = None,
    _headers: dict[str, str] | None = None,
) -> int:
    """Sync Twitter mentions for a user. Returns count of new interactions."""
    from app.models.interaction import Interaction

    headers = _headers or await _user_bearer_headers(user, db)
    if not headers or not user.twitter_user_id:
        return 0

    mentions = await fetch_mentions(user.twitter_user_id, headers)
    if not mentions:
        return 0

    # Build or reuse Twitter user ID -> Contact mapping
    id_to_contact = _id_map if _id_map is not None else await _build_twitter_id_to_contact_map(user, db, headers)
    new_count = 0

    for mention in mentions:
        tweet_id = mention.get("id", "")
        author_id = mention.get("author_id", "")
        text = mention.get("text", "")

        if author_id == user.twitter_user_id:
            continue  # Skip self-mentions

        # Check for existing
        existing = await db.execute(
            select(Interaction).where(Interaction.raw_reference_id == f"twitter_mention:{tweet_id}")
        )
        if existing.scalar_one_or_none():
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
        contact.last_interaction_at = interaction.occurred_at
        new_count += 1

    await db.flush()
    return new_count


# ---------------------------------------------------------------------------
# Reply sync — outbound replies to contacts' tweets
# ---------------------------------------------------------------------------

async def fetch_user_tweets_with_replies(
    twitter_user_id: str,
    headers: dict[str, str],
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch the authenticated user's recent tweets, including replies.

    Returns tweets that have ``in_reply_to_user_id`` set (i.e. replies).
    """
    all_tweets: list[dict[str, Any]] = []
    pagination_token: str | None = None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(MAX_DM_PAGES):
                params: dict[str, str] = {
                    "tweet.fields": "created_at,in_reply_to_user_id,text,referenced_tweets",
                    "max_results": "100",
                    "exclude": "retweets",
                }
                if since_id:
                    params["since_id"] = since_id
                if pagination_token:
                    params["pagination_token"] = pagination_token

                resp = await client.get(
                    f"{_TWITTER_API_BASE}/users/{twitter_user_id}/tweets",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()
                all_tweets.extend(body.get("data", []))

                pagination_token = body.get("meta", {}).get("next_token")
                if not pagination_token:
                    break

        # Filter to only replies (have in_reply_to_user_id)
        return [t for t in all_tweets if t.get("in_reply_to_user_id")]
    except httpx.HTTPStatusError as exc:
        logger.warning("fetch_user_tweets_with_replies: HTTP %s — %s", exc.response.status_code, exc.response.text)
        return [t for t in all_tweets if t.get("in_reply_to_user_id")]
    except Exception:
        logger.exception("fetch_user_tweets_with_replies: unexpected error.")
        return [t for t in all_tweets if t.get("in_reply_to_user_id")]


async def sync_twitter_replies(
    user: User,
    db: AsyncSession,
    *,
    _id_map: dict[str, Contact] | None = None,
    _headers: dict[str, str] | None = None,
) -> int:
    """Sync outbound replies to contacts' tweets. Returns count of new interactions."""
    from app.models.interaction import Interaction

    headers = _headers or await _user_bearer_headers(user, db)
    if not headers or not user.twitter_user_id:
        return 0

    replies = await fetch_user_tweets_with_replies(user.twitter_user_id, headers)
    if not replies:
        return 0

    # Build or reuse Twitter user ID -> Contact mapping
    id_to_contact = _id_map if _id_map is not None else await _build_twitter_id_to_contact_map(user, db, headers)
    new_count = 0

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

        # Dedup check
        existing = await db.execute(
            select(Interaction).where(Interaction.raw_reference_id == f"twitter_reply:{tweet_id}")
        )
        if existing.scalar_one_or_none():
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
        contact.last_interaction_at = interaction.occurred_at
        new_count += 1

    await db.flush()
    return new_count
