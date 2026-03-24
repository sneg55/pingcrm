"""Twitter contact mapping helpers for PingCRM."""
from __future__ import annotations

import asyncio
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.user import User

logger = logging.getLogger(__name__)

_TWITTER_API_BASE = "https://api.twitter.com/2"

_HANDLE_CACHE_TTL = 30 * 24 * 3600  # 30 days


async def _cached_resolve_handles(
    handles: list[str], headers: dict[str, str]
) -> dict[str, str]:
    """Resolve Twitter handles to user IDs via bird CLI (primary) + API (fallback).

    Returns {handle_lower: twitter_id}.

    Resolved IDs are persisted on the Contact row by the caller
    (_build_twitter_id_to_contact_map) so they never need re-resolving.
    Redis is only used to cache *misses* (deleted/invalid handles) for 30 days
    to avoid retrying them on every sync.
    """
    from app.core.redis import get_redis

    if not handles:
        return {}

    redis = get_redis()
    result: dict[str, str] = {}
    to_resolve: list[str] = []

    # Skip handles known to be unresolvable (cached as empty string in Redis)
    cache_keys = [f"tw:h2id:{h.lower()}" for h in handles]
    cached_values = await redis.mget(cache_keys)
    for handle, value in zip(handles, cached_values):
        if value is not None:
            decoded = value.decode() if isinstance(value, bytes) else value
            if decoded:
                # Legacy cached ID — use it but don't re-cache
                result[handle.lower()] = decoded
            # empty string = previously unresolvable — skip
        else:
            to_resolve.append(handle)

    # Primary: resolve via bird CLI (concurrent batches, no API credits needed)
    from app.integrations.bird import is_available as bird_available, resolve_user_id_bird

    still_unresolved: list[str] = []
    if bird_available():
        _BIRD_CONCURRENCY = 5
        for i in range(0, len(to_resolve), _BIRD_CONCURRENCY):
            chunk = to_resolve[i : i + _BIRD_CONCURRENCY]
            resolved = await asyncio.gather(
                *(resolve_user_id_bird(h) for h in chunk)
            )
            for handle, twitter_id in zip(chunk, resolved):
                if twitter_id:
                    result[handle.lower()] = twitter_id
                else:
                    still_unresolved.append(handle)
    else:
        still_unresolved = to_resolve

    # Fallback: batch resolve remaining via Twitter API
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
        except Exception:
            logger.exception("_cached_resolve_handles: API fallback failed at offset %d", i)
            continue

        # Cache misses as empty string so we don't re-query deleted/invalid handles
        resolved_in_batch = {h.lower() for h in batch if h.lower() in result}
        for handle in batch:
            if handle.lower() not in resolved_in_batch:
                await redis.set(f"tw:h2id:{handle.lower()}", "", ex=_HANDLE_CACHE_TTL)

    # Cache misses from bird CLI too
    all_resolved = set(result.keys())
    for handle in to_resolve:
        if handle.lower() not in all_resolved:
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
        select(Contact).where(
            Contact.user_id == user.id,
            Contact.twitter_handle.isnot(None),
            Contact.priority_level != "archived",
        )
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
