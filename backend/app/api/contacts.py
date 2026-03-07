import csv
import io
import logging
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import String, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.contact import (
    ContactCreate,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
    PaginationMeta,
)

from app.models.notification import Notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


def _add_sync_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str,
    body: str | None = None,
    link: str | None = "/settings",
) -> None:
    """Queue a sync/connect notification for the user."""
    db.add(Notification(
        user_id=user_id,
        notification_type="sync",
        title=title,
        body=body,
        link=link,
    ))


def envelope(data: Any, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


import re as _re

# Patterns like "Jan | Safe Foundation", "Mickey @ Arcadia", "Alice / ACME Corp"
_NAME_ORG_RE = _re.compile(
    r"^(.+?)\s*(?:\||@|/|—|–|-\s)\s*(.+)$"
)


def _parse_name_org(raw_name: str | None) -> tuple[str | None, str | None]:
    """Extract (clean_name, company) from a raw name that may contain an org separator.

    Recognises separators: |  @  /  —  –  and " - " (dash with spaces).
    Returns (name, None) if no separator found.
    """
    if not raw_name:
        return (None, None)
    raw = raw_name.strip()
    if not raw:
        return (None, None)
    m = _NAME_ORG_RE.match(raw)
    if m:
        name = m.group(1).strip()
        org = m.group(2).strip()
        if name and org:
            return (name, org)
    return (raw, None)


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    tag: str | None = Query(None),
    source: str | None = Query(None),
    score: str | None = Query(None, description="Filter by score tier: strong (8-10), active (4-7), dormant (0-3)"),
    date_from: str | None = Query(None, description="Filter contacts created on or after this date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Filter contacts created on or before this date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactListResponse:
    base_query = select(Contact).where(Contact.user_id == current_user.id)

    if search:
        # Escape SQL LIKE wildcards to prevent wildcard injection
        safe_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe_search}%"
        interaction_match = exists(
            select(Interaction.id).where(
                Interaction.contact_id == Contact.id,
                Interaction.content_preview.ilike(pattern),
            )
        )
        base_query = base_query.where(
            or_(
                Contact.full_name.ilike(pattern),
                Contact.given_name.ilike(pattern),
                Contact.family_name.ilike(pattern),
                Contact.company.ilike(pattern),
                Contact.title.ilike(pattern),
                Contact.twitter_handle.ilike(pattern),
                Contact.telegram_username.ilike(pattern),
                Contact.twitter_bio.ilike(pattern),
                Contact.telegram_bio.ilike(pattern),
                Contact.notes.ilike(pattern),
                Contact.source.ilike(pattern),
                cast(Contact.emails, String).ilike(pattern),
                cast(Contact.phones, String).ilike(pattern),
                interaction_match,
            )
        )

    if tag:
        base_query = base_query.where(Contact.tags.any(tag))

    if source:
        base_query = base_query.where(Contact.source == source)

    if date_from:
        from datetime import datetime, UTC
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=UTC)
            base_query = base_query.where(Contact.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        from datetime import datetime, timedelta, UTC
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
            base_query = base_query.where(Contact.created_at < dt_to)
        except ValueError:
            pass

    if score == "strong":
        base_query = base_query.where(Contact.relationship_score >= 8)
    elif score == "active":
        base_query = base_query.where(
            Contact.relationship_score >= 4, Contact.relationship_score <= 7
        )
    elif score == "dormant":
        base_query = base_query.where(Contact.relationship_score <= 3)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        base_query.order_by(Contact.relationship_score.desc(), Contact.created_at.desc()).offset(offset).limit(page_size)
    )
    contacts = result.scalars().all()

    return ContactListResponse(
        data=[ContactResponse.model_validate(c) for c in contacts],
        error=None,
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total > 0 else 1,
        ),
    )


@router.get("/tags", response_model=dict)
async def list_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return all unique tags used across the user's contacts."""
    result = await db.execute(
        select(func.unnest(Contact.tags)).where(
            Contact.user_id == current_user.id,
            Contact.tags.isnot(None),
        ).distinct()
    )
    tags = sorted(row[0] for row in result.all())
    return {"data": tags, "error": None}


@router.get("/stats", response_model=dict)
async def contact_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return aggregate contact stats for the dashboard."""
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Contact.relationship_score >= 8).label("strong"),
            func.count().filter(
                Contact.relationship_score >= 4,
                Contact.relationship_score < 8,
            ).label("active"),
            func.count().filter(Contact.relationship_score < 4).label("dormant"),
        ).where(Contact.user_id == current_user.id)
    )
    row = result.one()
    return {
        "data": {
            "total": row.total,
            "strong": row.strong,
            "active": row.active,
            "dormant": row.dormant,
        },
        "error": None,
    }


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_in: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    contact = Contact(**contact_in.model_dump(), user_id=current_user.id)
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.get("/{contact_id}", response_model=dict)
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.put("/{contact_id}", response_model=dict)
async def update_contact(
    contact_id: uuid.UUID,
    contact_in: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    for field, value in contact_in.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)

    await db.flush()
    await db.refresh(contact)
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.delete("/{contact_id}", response_model=dict)
async def delete_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    await db.delete(contact)
    return envelope({"id": str(contact_id), "deleted": True})


@router.get("/{contact_id}/duplicates", response_model=dict)
async def find_contact_duplicates(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Find possible duplicates for a specific contact."""
    from app.services.identity_resolution import _compute_adaptive_score, _build_blocking_keys

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Get all other contacts for this user
    all_result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id, Contact.id != contact_id)
    )
    others: list[Contact] = list(all_result.scalars().all())

    # Use blocking keys for efficiency
    target_keys = set(_build_blocking_keys(target))

    duplicates = []
    for other in others:
        other_keys = set(_build_blocking_keys(other))
        if not target_keys & other_keys:
            continue
        score = _compute_adaptive_score(target, other)
        if score < 0.40:
            continue
        duplicates.append({
            "id": str(other.id),
            "full_name": other.full_name,
            "given_name": other.given_name,
            "family_name": other.family_name,
            "emails": other.emails or [],
            "phones": other.phones or [],
            "company": other.company,
            "title": other.title,
            "twitter_handle": other.twitter_handle,
            "telegram_username": other.telegram_username,
            "score": round(score, 2),
        })

    duplicates.sort(key=lambda d: d["score"], reverse=True)
    return envelope(duplicates[:20])


@router.post("/{contact_id}/merge/{other_id}", response_model=dict)
async def merge_contact_pair(
    contact_id: uuid.UUID,
    other_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Merge other_id into contact_id. Returns the surviving contact."""
    from app.services.identity_resolution import merge_contacts

    # Verify both contacts belong to current user
    for cid in (contact_id, other_id):
        result = await db.execute(
            select(Contact).where(Contact.id == cid, Contact.user_id == current_user.id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {cid} not found")

    match_record = await merge_contacts(contact_id, other_id, db)
    await db.commit()

    # Re-fetch the surviving contact
    result = await db.execute(select(Contact).where(Contact.id == match_record.contact_a_id))
    surviving = result.scalar_one()

    return envelope({
        "id": str(surviving.id),
        "full_name": surviving.full_name,
        "merged_contact_id": str(other_id),
    })


@router.post("/import/csv", response_model=dict)
async def import_contacts_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    created: list[dict] = []
    errors: list[str] = []

    for i, row in enumerate(reader):
        try:
            raw_name = row.get("full_name") or row.get("name")
            csv_company = row.get("company") or row.get("organization")
            parsed_name, parsed_org = _parse_name_org(raw_name)
            # Use parsed org only if no explicit company column value
            effective_company = csv_company or parsed_org

            contact = Contact(
                user_id=current_user.id,
                full_name=parsed_name,
                given_name=row.get("given_name") or row.get("first_name"),
                family_name=row.get("family_name") or row.get("last_name"),
                emails=[e.strip() for e in row.get("emails", "").split(";") if e.strip()],
                phones=[p.strip() for p in row.get("phones", "").split(";") if p.strip()],
                company=effective_company,
                title=row.get("title") or row.get("job_title"),
                twitter_handle=row.get("twitter_handle") or row.get("twitter") or row.get("x_handle"),
                telegram_username=row.get("telegram_username") or row.get("telegram"),
                notes=row.get("notes") or row.get("note"),
                tags=[t.strip() for t in row.get("tags", "").split(";") if t.strip()] or None,
                source="csv",
            )
            db.add(contact)
            await db.flush()
            created.append({"id": str(contact.id), "full_name": contact.full_name})
        except Exception as exc:
            errors.append(f"Row {i + 1}: {exc!s}")

    return envelope({"created": created, "errors": errors})


@router.post("/import/linkedin", response_model=dict)
async def import_linkedin_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Import contacts from LinkedIn Connections.csv export."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    content = await file.read()
    text = content.decode("utf-8-sig")

    # LinkedIn CSV has header notes before the actual CSV header row.
    # Find the line that starts with "First Name," to locate the real header.
    lines = text.split("\n")
    header_idx = 0
    for idx, line in enumerate(lines):
        if line.strip().startswith("First Name,"):
            header_idx = idx
            break

    csv_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(csv_text))

    created = 0
    skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader):
        try:
            first = (row.get("First Name") or "").strip()
            last = (row.get("Last Name") or "").strip()
            email = (row.get("Email Address") or "").strip()
            company = (row.get("Company") or "").strip()
            position = (row.get("Position") or "").strip()
            url = (row.get("URL") or "").strip()

            if not first and not last:
                continue

            full_name = f"{first} {last}".strip()

            # Skip if contact with same name and company already exists
            existing = await db.execute(
                select(Contact).where(
                    Contact.user_id == current_user.id,
                    Contact.full_name == full_name,
                    Contact.company == (company or None),
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            contact = Contact(
                user_id=current_user.id,
                full_name=full_name,
                given_name=first or None,
                family_name=last or None,
                emails=[email] if email else [],
                company=company or None,
                title=position or None,
                linkedin_url=url or None,
                source="linkedin",
            )
            db.add(contact)
            await db.flush()
            created += 1
        except Exception as exc:
            errors.append(f"Row {i + 1}: {exc!s}")

    return envelope({"created": created, "skipped": skipped, "errors": errors})


@router.post("/import/linkedin-messages", response_model=dict)
async def import_linkedin_messages(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Import LinkedIn messages.csv and create interactions matched to existing contacts."""
    from datetime import datetime, UTC

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # Load all contacts for this user keyed by full_name (lowercased)
    all_contacts_result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id)
    )
    contacts_by_name: dict[str, Contact] = {}
    for c in all_contacts_result.scalars().all():
        if c.full_name:
            contacts_by_name[c.full_name.lower()] = c

    user_name = (current_user.full_name or current_user.email or "").lower()

    new_interactions = 0
    skipped = 0
    unmatched_names: set[str] = set()

    for row in reader:
        from_name = (row.get("FROM") or "").strip()
        to_name = (row.get("TO") or "").strip()
        content_preview = (row.get("CONTENT") or "").strip()
        date_str = (row.get("DATE") or "").strip()
        conv_id = (row.get("CONVERSATION ID") or "").strip()

        if not content_preview or not date_str:
            continue

        # Determine the other party and direction
        if from_name.lower() == user_name:
            other_name = to_name
            direction = "outbound"
        elif to_name.lower() == user_name:
            other_name = from_name
            direction = "inbound"
        else:
            # Neither side matches the user — skip
            continue

        contact = contacts_by_name.get(other_name.lower())
        if not contact:
            unmatched_names.add(other_name)
            continue

        # Parse date
        try:
            occurred_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %Z").replace(tzinfo=UTC)
        except ValueError:
            try:
                occurred_at = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except ValueError:
                continue

        # Idempotent: check by reference id
        ref_id = f"linkedin:{conv_id}:{date_str}"
        existing = await db.execute(
            select(Interaction).where(
                Interaction.raw_reference_id == ref_id,
                Interaction.user_id == current_user.id,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        interaction = Interaction(
            contact_id=contact.id,
            user_id=current_user.id,
            platform="linkedin",
            direction=direction,
            content_preview=content_preview[:500],
            raw_reference_id=ref_id,
            occurred_at=occurred_at,
        )
        db.add(interaction)
        new_interactions += 1

        # Update last_interaction_at
        if contact.last_interaction_at is None or contact.last_interaction_at < occurred_at:
            contact.last_interaction_at = occurred_at

    await db.flush()
    return envelope({
        "new_interactions": new_interactions,
        "skipped": skipped,
        "unmatched": len(unmatched_names),
        "unmatched_names": sorted(unmatched_names)[:20],
    })


@router.post("/sync/google", response_model=dict)
async def sync_google_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Dispatch a background Google Contacts sync.

    Returns immediately. A notification is created when sync completes.
    """
    from app.models.google_account import GoogleAccount

    ga_result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    has_accounts = ga_result.scalars().first() is not None
    if not has_accounts and not current_user.google_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Google account connected. Complete Google OAuth first.",
        )

    from app.services.tasks import sync_google_contacts_for_user
    sync_google_contacts_for_user.delay(str(current_user.id))

    return envelope({"status": "started"})


@router.post("/sync/google-calendar", response_model=dict)
async def sync_google_calendar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Dispatch a background Google Calendar sync.

    Returns immediately. A notification is created when sync completes.
    """
    from app.models.google_account import GoogleAccount

    ga_result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    has_accounts = ga_result.scalars().first() is not None
    if not has_accounts and not current_user.google_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Google account connected. Complete Google OAuth first.",
        )

    from app.services.tasks import sync_google_calendar_for_user
    sync_google_calendar_for_user.delay(str(current_user.id))

    return envelope({"status": "started"})


@router.post("/sync/twitter", response_model=dict)
async def sync_twitter(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Dispatch a background Twitter sync (DMs + mentions + bios).

    Returns immediately. A notification is created when sync completes.
    """
    if not current_user.twitter_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Twitter account not connected. Complete Twitter OAuth first.",
        )

    from app.services.tasks import sync_twitter_dms_for_user
    sync_twitter_dms_for_user.delay(str(current_user.id))

    return envelope({"status": "started"})


@router.post("/scores/recalculate", response_model=dict)
async def recalculate_scores(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Recalculate relationship scores for all contacts of the authenticated user."""
    from app.services.scoring import calculate_score

    contacts_result = await db.execute(
        select(Contact.id).where(Contact.user_id == current_user.id)
    )
    updated = 0
    for (contact_id,) in contacts_result.all():
        await calculate_score(contact_id, db)
        updated += 1

    await db.commit()
    return envelope({"updated": updated})


# In-memory cache: contact_id -> last_bio_check timestamp
_bio_check_cache: dict[str, float] = {}
_BIO_CHECK_TTL = 86400  # 24 hours


@router.post("/{contact_id}/refresh-bios", response_model=dict)
async def refresh_contact_bios(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Check for bio updates on Twitter and Telegram for a single contact.

    Rate-limited to once per 24 hours per contact.
    """
    import time as _time

    cache_key = str(contact_id)
    now = _time.time()
    last_check = _bio_check_cache.get(cache_key, 0)
    if now - last_check < _BIO_CHECK_TTL:
        return envelope({"skipped": True, "reason": "checked_recently"})

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    changes: dict[str, Any] = {"twitter_bio_changed": False, "telegram_bio_changed": False}

    # Twitter bio check
    if contact.twitter_handle:
        try:
            from app.integrations.twitter import fetch_user_profile
            handle = (contact.twitter_handle or "").lstrip("@").strip()
            if handle:
                profile = await fetch_user_profile(handle)
                new_bio = profile.get("description", "")
                if new_bio and new_bio != (contact.twitter_bio or ""):
                    old_bio = contact.twitter_bio
                    contact.twitter_bio = new_bio
                    changes["twitter_bio_changed"] = True
                    if old_bio:
                        from app.models.notification import Notification
                        notif = Notification(
                            user_id=current_user.id,
                            notification_type="bio_change",
                            title=f"@{handle} updated their Twitter bio",
                            body=f"{contact.full_name or handle} changed their bio to: {new_bio[:200]}",
                            link=f"/contacts/{contact.id}",
                        )
                        db.add(notif)
        except Exception:
            logger.warning("refresh_contact_bios: Twitter bio fetch failed for contact %s", contact_id)

    # Telegram bio check
    if contact.telegram_username and current_user.telegram_session:
        try:
            from app.integrations.telegram import _make_client, _ensure_connected
            from telethon.tl.functions.users import GetFullUserRequest

            username = (contact.telegram_username or "").lstrip("@").strip()
            if username:
                client = _make_client(current_user.telegram_session)
                await _ensure_connected(client)
                try:
                    input_user = await client.get_input_entity(username)
                    full = await client(GetFullUserRequest(input_user))
                    new_bio = getattr(full.full_user, "about", None) or ""
                    if new_bio and new_bio != (contact.telegram_bio or ""):
                        old_bio = contact.telegram_bio
                        contact.telegram_bio = new_bio
                        changes["telegram_bio_changed"] = True
                        if old_bio:
                            from app.models.notification import Notification
                            notif = Notification(
                                user_id=current_user.id,
                                notification_type="bio_change",
                                title=f"@{username} updated their Telegram bio",
                                body=f"{contact.full_name or username} changed their bio to: {new_bio[:200]}",
                                link=f"/contacts/{contact.id}",
                            )
                            db.add(notif)
                finally:
                    await client.disconnect()
        except Exception:
            logger.warning("refresh_contact_bios: Telegram bio fetch failed for contact %s", contact_id)

    _bio_check_cache[cache_key] = now
    await db.commit()
    return envelope(changes)
