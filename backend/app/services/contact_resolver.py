"""Race-safe find-or-create for Contact rows, keyed by identity axis.

Two contacts (same user) sharing exactly any email (ci), telegram_user_id,
telegram_username (ci), twitter_user_id, twitter_handle (ci), or
linkedin_profile_id are duplicates. This module is the single chokepoint
that prevents new ones — every sync/import path should funnel through it.

Concurrent transactions are serialized via Postgres advisory transaction
locks keyed on (axis, user_id, normalized_value). The lock is held for
the lifetime of the transaction, so the lookup-then-insert pair is atomic
across workers.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_email(raw: str | None) -> str | None:
    """Lowercase + trim. Plus-aliases preserved (foo+work@x.com is intentional).
    Returns None for empty/whitespace/None."""
    if raw is None:
        return None
    s = raw.strip().lower()
    return s or None


def normalize_handle(raw: str | None) -> str | None:
    """Lowercase + trim + strip leading '@'. Returns None for empty."""
    if raw is None:
        return None
    s = raw.strip().lstrip("@").strip().lower()
    return s or None


# ---------------------------------------------------------------------------
# Internal: advisory lock + apply defaults
# ---------------------------------------------------------------------------

async def _xact_lock(db: AsyncSession, key: str) -> None:
    """Acquire a Postgres advisory lock for the lifetime of the current
    transaction. Two transactions with the same key serialize."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key}
    )


def _apply_defaults_for_create(
    user_id: uuid.UUID,
    defaults: dict[str, Any] | None,
    *,
    locked_field: str,
    locked_value: Any,
    extra_emails: list[str] | None = None,
) -> Contact:
    """Build a fresh Contact from defaults, with the locked identity field
    forced to its normalized value (defaults can't override it).

    `extra_emails` (used by the email resolver) is merged with any emails
    already in *defaults*, dedup'd case-insensitively, and stored as the
    final `emails` array."""
    payload: dict[str, Any] = dict(defaults or {})

    # Normalize handle-shaped fields if present in defaults (and not the
    # locked field — the locked one already gets the canonical value below).
    for field in ("telegram_username", "twitter_handle"):
        if field in payload and field != locked_field:
            payload[field] = normalize_handle(payload[field])

    # Merge emails: combine `extra_emails` with any defaults emails. This
    # runs before the `locked_field` overwrite so that for `locked_field='emails'`
    # the merged list becomes the locked value, not just `extra_emails`.
    if extra_emails is not None:
        existing = payload.pop("emails", None) or []
        merged = []
        seen: set[str] = set()
        for e in [*extra_emails, *existing]:
            n = normalize_email(e)
            if n and n not in seen:
                seen.add(n)
                merged.append(n)
        payload["emails"] = merged
        # If we just computed the emails array and emails is the locked field,
        # the merged list IS the locked value — skip the overwrite below.
        if locked_field == "emails":
            payload["user_id"] = user_id
            return Contact(**payload)

    payload[locked_field] = locked_value
    payload["user_id"] = user_id
    return Contact(**payload)


# ---------------------------------------------------------------------------
# Public API — find_or_create per identity axis
# ---------------------------------------------------------------------------

async def find_or_create_contact_by_email(
    db: AsyncSession,
    user_id: uuid.UUID,
    email: str,
    *,
    defaults: dict[str, Any] | None = None,
) -> tuple[Contact, bool]:
    """Returns (contact, created). Match is case-insensitive against any
    element of `Contact.emails`. On create, the email is stored normalized."""
    norm = normalize_email(email)
    if norm is None:
        raise ValueError("email is empty")

    await _xact_lock(db, f"cr:email:{user_id}:{norm}")

    result = await db.execute(
        text(
            """
            SELECT id FROM contacts
            WHERE user_id = :uid
              AND EXISTS (
                SELECT 1 FROM unnest(emails) e
                WHERE lower(trim(e)) = :norm
              )
            ORDER BY created_at ASC
            LIMIT 1
            """
        ),
        {"uid": user_id, "norm": norm},
    )
    row = result.first()
    if row:
        existing = await db.get(Contact, row[0])
        if existing is not None:
            return existing, False

    contact = _apply_defaults_for_create(
        user_id, defaults, locked_field="emails", locked_value=[norm],
        extra_emails=[norm],
    )
    db.add(contact)
    await db.flush()
    return contact, True


async def find_or_create_contact_by_telegram_user_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    telegram_user_id: str,
    *,
    defaults: dict[str, Any] | None = None,
) -> tuple[Contact, bool]:
    """Match by exact telegram_user_id (the stable Telegram numeric ID, stored as str)."""
    tg_id = (telegram_user_id or "").strip()
    if not tg_id:
        raise ValueError("telegram_user_id is empty")

    await _xact_lock(db, f"cr:tgid:{user_id}:{tg_id}")

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.telegram_user_id == tg_id,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    contact = _apply_defaults_for_create(
        user_id, defaults, locked_field="telegram_user_id", locked_value=tg_id,
    )
    db.add(contact)
    await db.flush()
    return contact, True


async def find_or_create_contact_by_telegram_username(
    db: AsyncSession,
    user_id: uuid.UUID,
    username: str,
    *,
    defaults: dict[str, Any] | None = None,
) -> tuple[Contact, bool]:
    """Match by case-insensitive telegram_username. The stored column is
    expected to already be lowercase but we compare via lower() to be safe."""
    norm = normalize_handle(username)
    if norm is None:
        raise ValueError("telegram_username is empty")

    await _xact_lock(db, f"cr:tguser:{user_id}:{norm}")

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.telegram_username == norm,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    contact = _apply_defaults_for_create(
        user_id, defaults, locked_field="telegram_username", locked_value=norm,
    )
    db.add(contact)
    await db.flush()
    return contact, True


async def find_or_create_contact_by_twitter_user_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    twitter_user_id: str,
    *,
    defaults: dict[str, Any] | None = None,
) -> tuple[Contact, bool]:
    """Match by exact twitter_user_id (the stable Twitter numeric ID)."""
    tw_id = (twitter_user_id or "").strip()
    if not tw_id:
        raise ValueError("twitter_user_id is empty")

    await _xact_lock(db, f"cr:twid:{user_id}:{tw_id}")

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.twitter_user_id == tw_id,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    contact = _apply_defaults_for_create(
        user_id, defaults, locked_field="twitter_user_id", locked_value=tw_id,
    )
    db.add(contact)
    await db.flush()
    return contact, True


async def find_or_create_contact_by_twitter_handle(
    db: AsyncSession,
    user_id: uuid.UUID,
    handle: str,
    *,
    defaults: dict[str, Any] | None = None,
) -> tuple[Contact, bool]:
    """Match by case-insensitive twitter_handle (the @-username). Less stable
    than twitter_user_id (handles can change) — prefer the ID variant when known."""
    norm = normalize_handle(handle)
    if norm is None:
        raise ValueError("twitter_handle is empty")

    await _xact_lock(db, f"cr:twhandle:{user_id}:{norm}")

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.twitter_handle == norm,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    contact = _apply_defaults_for_create(
        user_id, defaults, locked_field="twitter_handle", locked_value=norm,
    )
    db.add(contact)
    await db.flush()
    return contact, True


async def find_or_create_contact_by_linkedin_profile_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    profile_id: str,
    *,
    defaults: dict[str, Any] | None = None,
) -> tuple[Contact, bool]:
    """Match by exact linkedin_profile_id (the slug from /in/<slug>)."""
    slug = (profile_id or "").strip()
    if not slug:
        raise ValueError("linkedin_profile_id is empty")

    await _xact_lock(db, f"cr:liid:{user_id}:{slug}")

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.linkedin_profile_id == slug,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    contact = _apply_defaults_for_create(
        user_id, defaults, locked_field="linkedin_profile_id", locked_value=slug,
    )
    db.add(contact)
    await db.flush()
    return contact, True
