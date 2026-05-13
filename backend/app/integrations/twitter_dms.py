"""Twitter / X DM sync functions extracted from twitter.py.

Public callers should import these via app.integrations.twitter for
backwards compatibility — twitter.py re-exports them.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.twitter_auth import (
    _refresh_and_retry,
    _user_bearer_headers,
)
from app.integrations.twitter_contacts import (
    _build_twitter_id_to_contact_map,
    _cached_resolve_handles,
)
from app.models.contact import Contact
from app.models.user import User
from app.services.contact_resolver import find_or_create_contact_by_twitter_user_id

logger = logging.getLogger(__name__)

_TWITTER_API_BASE = "https://api.twitter.com/2"
MAX_DM_PAGES = 15  # safety cap: 15 pages * 100 = up to 1500 events


def _parse_twitter_ts_local(ts: str | None):
    """Local import shim — defer to twitter._parse_twitter_ts."""
    from app.integrations.twitter import _parse_twitter_ts
    return _parse_twitter_ts(ts)


async def fetch_dm_conversations(
    headers: dict[str, str],
    *,
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch DM events using OAuth 2.0 user token (Twitter API v2)."""
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

                if resp.status_code == 400 and since_id:
                    logger.info("fetch_dm_conversations: retrying without since_id (stale cursor)")
                    since_id = None
                    pagination_token = None
                    all_events.clear()
                    continue

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
    """Batch lookup Twitter users by IDs."""
    if not ids:
        return {}
    result: dict[str, dict[str, str]] = {}
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

    if not user.twitter_user_id:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_TWITTER_API_BASE}/users/me", headers=headers)
                resp.raise_for_status()
                user.twitter_user_id = resp.json()["data"]["id"]
                await db.flush()
        except httpx.HTTPStatusError:
            raise
        except Exception:
            logger.exception("sync_twitter_dms: failed to get user's Twitter ID")
            return 0

    dm_events = await fetch_dm_conversations(headers, since_id=user.twitter_dm_cursor)
    if not dm_events:
        logger.info("sync_twitter_dms: no new DM events for user %s (cursor: %s)", user.id, user.twitter_dm_cursor)
        return 0

    logger.info("sync_twitter_dms: processing %d DM events for user %s (cursor: %s)", len(dm_events), user.id, user.twitter_dm_cursor)

    id_to_contact = _id_map if _id_map is not None else await _build_twitter_id_to_contact_map(user, db, headers)
    logger.info("sync_twitter_dms: contact map has %d entries", len(id_to_contact))
    new_count = 0
    created_contacts = 0
    skipped_duplicate = 0
    _pending_create: dict[str, list[dict]] = {}

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

        direction = "outbound" if sender_id == user.twitter_user_id else "inbound"

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
        if not participant_id or participant_id == user.twitter_user_id:
            continue

        ref_id = f"twitter_dm:{event_id}"
        if ref_id in existing_refs:
            skipped_duplicate += 1
            contact = id_to_contact.get(participant_id)
            if contact:
                occurred_at = _parse_twitter_ts_local(event.get("created_at"))
                if contact.last_interaction_at is None or contact.last_interaction_at < occurred_at:
                    contact.last_interaction_at = occurred_at
            continue

        contact = id_to_contact.get(participant_id)
        if not contact:
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
            occurred_at=_parse_twitter_ts_local(event.get("created_at")),
        )
        db.add(interaction)
        if contact.last_interaction_at is None or contact.last_interaction_at < interaction.occurred_at:
            contact.last_interaction_at = interaction.occurred_at
        new_count += 1

    if _pending_create:
        profiles = await _lookup_twitter_users_by_ids(list(_pending_create.keys()), headers)
        for twitter_id, events in _pending_create.items():
            profile = profiles.get(twitter_id, {})
            username = profile.get("username", "")
            name = profile.get("name", "")

            parts = name.split(None, 1) if name else []
            contact, created = await find_or_create_contact_by_twitter_user_id(
                db, user.id, twitter_id,
                defaults=dict(
                    given_name=parts[0] if parts else username or twitter_id,
                    family_name=parts[1] if len(parts) > 1 else None,
                    full_name=name or username or None,
                    twitter_handle=username or None,
                    source="twitter",
                ),
            )
            if created:
                created_contacts += 1
            id_to_contact[twitter_id] = contact

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
                    occurred_at=_parse_twitter_ts_local(ev.get("created_at")),
                )
                db.add(interaction)
                if contact.last_interaction_at is None or contact.last_interaction_at < interaction.occurred_at:
                    contact.last_interaction_at = interaction.occurred_at
                new_count += 1

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
    """Fetch DM events with a specific user using Twitter API v2."""
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
    """Sync Twitter DMs for a single contact."""
    from app.models.interaction import Interaction

    headers = await _user_bearer_headers(user, db)
    if not headers:
        return {"new_interactions": 0, "skipped": True, "reason": "twitter_not_connected"}

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

    if not re.fullmatch(r"\d+", contact_twitter_id):
        return {"new_interactions": 0, "skipped": True, "reason": "invalid_twitter_id"}

    try:
        dm_events = await fetch_dm_conversation_with(contact_twitter_id, headers)
    except httpx.HTTPStatusError:
        headers = await _refresh_and_retry(user, db)
        if not headers:
            return {"new_interactions": 0, "skipped": True, "reason": "auth_failed"}
        dm_events = await fetch_dm_conversation_with(contact_twitter_id, headers)

    if not dm_events:
        return {"new_interactions": 0}

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

        if participant_id != contact_twitter_id:
            continue

        if f"twitter_dm:{event_id}" in existing_refs:
            continue

        interaction = Interaction(
            contact_id=contact.id,
            user_id=user.id,
            platform="twitter",
            direction=direction,
            content_preview=text[:500] if text else "",
            raw_reference_id=f"twitter_dm:{event_id}",
            occurred_at=_parse_twitter_ts_local(event.get("created_at")),
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
