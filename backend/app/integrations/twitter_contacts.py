"""Twitter contact mapping helpers for PingCRM."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.user import User

logger = logging.getLogger(__name__)

_HANDLE_CACHE_TTL = 30 * 24 * 3600  # 30 days


async def _cached_resolve_handles(
    handles: list[str],
    headers: dict[str, str],
    *,
    auth_token: str | None = None,
    ct0: str | None = None,
) -> dict[str, str]:
    """Resolve Twitter handles to user IDs via bird CLI.

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

    # Resolve via bird CLI (concurrent batches, no API credits needed)
    from app.integrations.bird import is_available as bird_available, resolve_user_id_bird

    if bird_available() and auth_token and ct0:
        _BIRD_CONCURRENCY = 5
        for i in range(0, len(to_resolve), _BIRD_CONCURRENCY):
            chunk = to_resolve[i : i + _BIRD_CONCURRENCY]
            results = await asyncio.gather(
                *(resolve_user_id_bird(h, auth_token=auth_token, ct0=ct0) for h in chunk)
            )
            for handle, (twitter_id, _err) in zip(chunk, results):
                if twitter_id:
                    result[handle.lower()] = twitter_id

    # No OAuth API fallback — cache misses from bird CLI
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
        from app.services.bird_session import get_cookies
        cookies = get_cookies(user)
        auth_token, ct0 = cookies if cookies else (None, None)
        handle_to_id = await _cached_resolve_handles(
            list(needs_resolve.keys()), headers, auth_token=auth_token, ct0=ct0,
        )
        for handle, twitter_id in handle_to_id.items():
            for contact in needs_resolve.get(handle, []):
                contact.twitter_user_id = twitter_id
                id_map[twitter_id] = contact
        await db.flush()

    return id_map
