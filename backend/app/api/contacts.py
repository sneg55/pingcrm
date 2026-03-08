from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import (
    ContactCreate,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
)
from app.schemas.responses import (
    ApplyTagsResult,
    AutoTagResult,
    AvatarRefreshData,
    BioRefreshData,
    ContactStatsData,
    CsvImportResult,
    DeletedData,
    DuplicateContactData,
    EnrichData,
    Envelope,
    LinkedInImportResult,
    LinkedInMessagesImportResult,
    MergedContactData,
    ScoresRecalculatedData,
    SendMessageData,
    SyncStartedData,
    TaxonomyResult,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


def envelope(data: Any, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


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
    has_interactions: bool | None = Query(None, description="Filter to contacts with (true) or without (false) interactions"),
    interaction_days: int | None = Query(None, ge=1, le=365, description="Filter to contacts with last interaction within N days"),
    has_birthday: bool | None = Query(None, description="Filter to contacts with (true) or without (false) a birthday set"),
    sort: str = Query("score", pattern="^(score|created|interaction|birthday)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactListResponse:
    from app.services.contact_search import list_contacts_paginated

    return await list_contacts_paginated(
        db,
        current_user.id,
        page=page,
        page_size=page_size,
        search=search,
        tag=tag,
        source=source,
        score=score,
        date_from=date_from,
        date_to=date_to,
        has_interactions=has_interactions,
        interaction_days=interaction_days,
        has_birthday=has_birthday,
        sort_by=sort,
    )


@router.get("/tags", response_model=Envelope[list[str]])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[str]]:
    """Return all unique tags used across the user's contacts."""
    result = await db.execute(
        select(func.unnest(Contact.tags)).where(
            Contact.user_id == current_user.id,
            Contact.tags.isnot(None),
        ).distinct()
    )
    tags = sorted(row[0] for row in result.all())
    return {"data": tags, "error": None}


# ---------------------------------------------------------------------------
# Tag Taxonomy & Auto-tagging endpoints
# NOTE: These MUST be declared before /{contact_id} routes so FastAPI
# matches the literal "/tags/..." path before the UUID parameter.
# ---------------------------------------------------------------------------


@router.post("/tags/discover", response_model=Envelope[TaxonomyResult])
async def discover_tag_taxonomy(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[TaxonomyResult]:
    """Phase 1: AI scans all contacts and proposes a categorized tag taxonomy."""
    from app.models.interaction import Interaction
    from app.models.tag_taxonomy import TagTaxonomy
    from app.services.auto_tagger import deduplicate_taxonomy, discover_taxonomy

    import random as _random

    from sqlalchemy import or_

    # Fetch all non-archived, non-"2nd tier" contacts
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == current_user.id,
            Contact.priority_level != "archived",
            or_(Contact.tags.is_(None), ~Contact.tags.contains(["2nd tier"])),
        )
    )
    all_contacts = list(result.scalars().all())
    if not all_contacts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No contacts to analyze")

    # Sample up to 300 contacts for taxonomy discovery.
    # Prioritize contacts with richer data (bios, titles, interactions).
    # This keeps the LLM calls to ~6 batches (~30-60s) instead of 100+.
    _MAX_DISCOVER_SAMPLE = 300

    if len(all_contacts) > _MAX_DISCOVER_SAMPLE:
        # Score contacts by data richness so we sample the most informative ones
        def _richness(c: Contact) -> int:
            score = 0
            if c.full_name:
                score += 1
            if c.title:
                score += 2
            if c.company:
                score += 2
            if c.twitter_bio:
                score += 3
            if c.telegram_bio:
                score += 3
            if c.notes:
                score += 1
            if c.tags:
                score += 1
            if c.location:
                score += 1
            return score

        # Take top 200 by richness + random 100 for diversity
        sorted_contacts = sorted(all_contacts, key=_richness, reverse=True)
        top_rich = sorted_contacts[:200]
        remaining = sorted_contacts[200:]
        random_sample = _random.sample(remaining, min(100, len(remaining)))
        contacts = top_rich + random_sample
        logger.info(
            "discover_tag_taxonomy: sampled %d of %d contacts for discovery",
            len(contacts), len(all_contacts),
        )
    else:
        contacts = all_contacts

    # Batch-fetch interaction topics for sampled contacts (avoids N+1)
    cids = [c.id for c in contacts]
    int_result = await db.execute(
        select(Interaction.contact_id, Interaction.content_preview).where(
            Interaction.contact_id.in_(cids),
            Interaction.content_preview.isnot(None),
        ).order_by(Interaction.occurred_at.desc())
    )
    topics_by_contact: dict[uuid.UUID, list[str]] = {}
    for row in int_result.all():
        lst = topics_by_contact.setdefault(row[0], [])
        if len(lst) < 10:
            lst.append(row[1][:100])

    summaries = []
    for c in contacts:
        summaries.append({
            "full_name": c.full_name,
            "title": c.title,
            "company": c.company,
            "twitter_bio": c.twitter_bio,
            "telegram_bio": c.telegram_bio,
            "notes": c.notes,
            "tags": c.tags,
            "location": c.location,
            "interaction_topics": topics_by_contact.get(c.id, []),
        })

    try:
        raw_categories = await discover_taxonomy(summaries)
        categories = await deduplicate_taxonomy(raw_categories)
    except Exception as exc:
        logger.exception("discover_tag_taxonomy: AI discovery failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI tag discovery failed: {type(exc).__name__}: {str(exc)[:200]}",
        ) from exc

    total_tags = sum(len(tags) for tags in categories.values())

    # Upsert taxonomy record
    tax_result = await db.execute(
        select(TagTaxonomy).where(TagTaxonomy.user_id == current_user.id)
    )
    taxonomy = tax_result.scalar_one_or_none()
    if taxonomy:
        taxonomy.categories = categories
        taxonomy.status = "draft"
    else:
        taxonomy = TagTaxonomy(
            user_id=current_user.id,
            categories=categories,
            status="draft",
        )
        db.add(taxonomy)

    await db.flush()

    return envelope({
        "categories": categories,
        "total_tags": total_tags,
        "status": "draft",
    })


@router.get("/tags/taxonomy", response_model=Envelope[TaxonomyResult])
async def get_taxonomy(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[TaxonomyResult]:
    """Get the current user's tag taxonomy."""
    from app.models.tag_taxonomy import TagTaxonomy

    result = await db.execute(
        select(TagTaxonomy).where(TagTaxonomy.user_id == current_user.id)
    )
    taxonomy = result.scalar_one_or_none()
    if not taxonomy:
        return envelope(None)

    categories = taxonomy.categories or {}
    return envelope({
        "categories": categories,
        "total_tags": sum(len(t) for t in categories.values()),
        "status": taxonomy.status,
    })


class TaxonomyUpdateBody(BaseModel):
    categories: dict[str, list[str]]
    status: str | None = None  # "draft" | "approved"


@router.put("/tags/taxonomy", response_model=Envelope[TaxonomyResult])
async def update_taxonomy(
    body: TaxonomyUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[TaxonomyResult]:
    """Update the user's tag taxonomy (add/remove/rename categories and tags)."""
    from app.models.tag_taxonomy import TagTaxonomy

    # Validate status field
    if body.status and body.status not in ("draft", "approved"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be 'draft' or 'approved'",
        )

    result = await db.execute(
        select(TagTaxonomy).where(TagTaxonomy.user_id == current_user.id)
    )
    taxonomy = result.scalar_one_or_none()
    if not taxonomy:
        taxonomy = TagTaxonomy(
            user_id=current_user.id,
            categories=body.categories,
            status=body.status or "draft",
        )
        db.add(taxonomy)
    else:
        taxonomy.categories = body.categories
        if body.status:
            taxonomy.status = body.status

    await db.flush()

    categories = taxonomy.categories or {}
    return envelope({
        "categories": categories,
        "total_tags": sum(len(t) for t in categories.values()),
        "status": taxonomy.status,
    })


class ApplyTagsBody(BaseModel):
    contact_ids: list[uuid.UUID] | None = None


@router.post("/tags/apply", response_model=Envelope[ApplyTagsResult])
async def apply_tags(
    body: ApplyTagsBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ApplyTagsResult]:
    """Phase 2: Apply approved taxonomy tags to contacts (inline for <20, Celery for more)."""
    from app.models.tag_taxonomy import TagTaxonomy

    tax_result = await db.execute(
        select(TagTaxonomy).where(TagTaxonomy.user_id == current_user.id)
    )
    taxonomy = tax_result.scalar_one_or_none()
    if not taxonomy or taxonomy.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Taxonomy must be approved before applying tags.",
        )

    # Determine contact IDs
    if body.contact_ids:
        contact_ids = body.contact_ids
    else:
        from sqlalchemy import or_
        result = await db.execute(
            select(Contact.id).where(
                Contact.user_id == current_user.id,
                Contact.priority_level != "archived",
                or_(Contact.tags.is_(None), ~Contact.tags.contains(["2nd tier"])),
            )
        )
        contact_ids = [row[0] for row in result.all()]

    if len(contact_ids) <= 20:
        # Inline processing
        from app.models.interaction import Interaction
        from app.services.auto_tagger import _get_anthropic_client, assign_tags, merge_tags

        # Batch-load contacts and interactions (avoids N+1)
        c_result = await db.execute(
            select(Contact).where(
                Contact.id.in_(contact_ids),
                Contact.user_id == current_user.id,
            )
        )
        contacts_map = {c.id: c for c in c_result.scalars().all()}

        int_result = await db.execute(
            select(Interaction.contact_id, Interaction.content_preview).where(
                Interaction.contact_id.in_(contact_ids),
                Interaction.content_preview.isnot(None),
            ).order_by(Interaction.occurred_at.desc())
        )
        topics_by_contact: dict[uuid.UUID, list[str]] = {}
        for row in int_result.all():
            lst = topics_by_contact.setdefault(row[0], [])
            if len(lst) < 10:
                lst.append(row[1][:100])

        # Reuse one client for all contacts
        anthropic_client = _get_anthropic_client()
        tagged = 0
        for cid in contact_ids:
            contact = contacts_map.get(cid)
            if not contact:
                continue

            contact_data = {
                "full_name": contact.full_name,
                "title": contact.title,
                "company": contact.company,
                "twitter_bio": contact.twitter_bio,
                "telegram_bio": contact.telegram_bio,
                "notes": contact.notes,
                "tags": contact.tags,
                "location": contact.location,
                "interaction_topics": topics_by_contact.get(cid, []),
            }
            new_tags = await assign_tags(contact_data, taxonomy.categories, client=anthropic_client)
            if new_tags:
                contact.tags = merge_tags(contact.tags, new_tags)
                tagged += 1

        await db.flush()
        return envelope({"tagged_count": tagged, "task_id": None})
    else:
        # Enqueue Celery task for large sets
        from app.services.tasks import apply_tags_to_contacts
        task = apply_tags_to_contacts.delay(
            str(current_user.id),
            [str(cid) for cid in contact_ids] if body.contact_ids else None,
        )
        return envelope({"tagged_count": 0, "task_id": task.id})


@router.get("/stats", response_model=Envelope[ContactStatsData])
async def contact_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactStatsData]:
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
        ).where(
            Contact.user_id == current_user.id,
            Contact.priority_level != "archived",
        )
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


@router.get("/birthdays")
async def get_upcoming_birthdays(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return contacts with birthdays in the next 7 days."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    today = now.date()
    upcoming_mmdd = [(today + timedelta(days=d)).strftime("%m-%d") for d in range(7)]
    upcoming_set = set(upcoming_mmdd)

    result = await db.execute(
        select(Contact).where(
            Contact.user_id == current_user.id,
            Contact.priority_level != "archived",
            Contact.birthday.isnot(None),
        )
    )
    contacts = result.scalars().all()

    matches = []
    for contact in contacts:
        bday = contact.birthday.strip()
        mmdd = bday[-5:]  # supports "MM-DD" and "YYYY-MM-DD"
        if mmdd not in upcoming_set:
            continue
        days_away = upcoming_mmdd.index(mmdd)
        matches.append((days_away, contact))

    matches.sort(key=lambda x: x[0])
    matches = matches[:10]

    return envelope(
        [
            {
                **ContactResponse.model_validate(c).model_dump(),
                "days_until_birthday": days,
            }
            for days, c in matches
        ]
    )


@router.post("", response_model=Envelope[ContactResponse], status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_in: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactResponse]:
    contact = Contact(**contact_in.model_dump(), user_id=current_user.id)
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.get("/{contact_id}", response_model=Envelope[ContactResponse])
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactResponse]:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.put("/{contact_id}", response_model=Envelope[ContactResponse])
async def update_contact(
    contact_id: uuid.UUID,
    contact_in: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ContactResponse]:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    for field, value in contact_in.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)

    # When archiving, dismiss any pending follow-up suggestions
    if contact.priority_level == "archived":
        from app.models.follow_up import FollowUpSuggestion
        pending_result = await db.execute(
            select(FollowUpSuggestion).where(
                FollowUpSuggestion.contact_id == contact_id,
                FollowUpSuggestion.status == "pending",
            )
        )
        for suggestion in pending_result.scalars().all():
            suggestion.status = "dismissed"

    await db.flush()
    await db.refresh(contact)
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.delete("/{contact_id}", response_model=Envelope[DeletedData])
async def delete_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[DeletedData]:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    await db.delete(contact)
    return envelope({"id": str(contact_id), "deleted": True})


@router.get("/{contact_id}/duplicates", response_model=Envelope[list[DuplicateContactData]])
async def find_contact_duplicates(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[DuplicateContactData]]:
    """Find possible duplicates for a specific contact."""
    from app.services.identity_resolution import compute_adaptive_score, build_blocking_keys

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
    target_keys = set(build_blocking_keys(target))

    duplicates = []
    for other in others:
        other_keys = set(build_blocking_keys(other))
        if not target_keys & other_keys:
            continue
        score = compute_adaptive_score(target, other)
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


@router.post("/{contact_id}/merge/{other_id}", response_model=Envelope[MergedContactData])
async def merge_contact_pair(
    contact_id: uuid.UUID,
    other_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[MergedContactData]:
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
    await db.flush()

    # Re-fetch the surviving contact
    result = await db.execute(select(Contact).where(Contact.id == match_record.contact_a_id))
    surviving = result.scalar_one()

    return envelope({
        "id": str(surviving.id),
        "full_name": surviving.full_name,
        "merged_contact_id": str(other_id),
    })


@router.post("/import/csv", response_model=Envelope[CsvImportResult])
async def import_contacts_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[CsvImportResult]:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    from app.services.contact_import import import_csv

    content = await file.read()
    result = await import_csv(content, current_user.id, db)
    return envelope(result)


@router.post("/import/linkedin", response_model=Envelope[LinkedInImportResult])
async def import_linkedin_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[LinkedInImportResult]:
    """Import contacts from LinkedIn Connections.csv export."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    from app.services.contact_import import import_linkedin_connections

    content = await file.read()
    result = await import_linkedin_connections(content, current_user.id, db)
    return envelope(result)


@router.post("/import/linkedin-messages", response_model=Envelope[LinkedInMessagesImportResult])
async def import_linkedin_messages(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[LinkedInMessagesImportResult]:
    """Import LinkedIn messages.csv and create interactions matched to existing contacts."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    from app.services.contact_import import import_linkedin_messages as _import_messages

    content = await file.read()
    user_name = (current_user.full_name or current_user.email or "").lower()
    result = await _import_messages(content, current_user.id, user_name, db)
    return envelope(result)


@router.post("/sync/google", response_model=Envelope[SyncStartedData])
async def sync_google_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
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


@router.post("/sync/google-calendar", response_model=Envelope[SyncStartedData])
async def sync_google_calendar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
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


@router.post("/sync/gmail", response_model=Envelope[SyncStartedData])
async def sync_gmail(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
    """Dispatch a background Gmail thread sync.

    Returns immediately. A notification is created when sync completes.
    """
    if not current_user.google_refresh_token:
        from app.models.google_account import GoogleAccount
        ga_result = await db.execute(
            select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
        )
        if not ga_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No Google account connected. Complete Google OAuth first.",
            )

    from app.services.tasks import sync_gmail_for_user
    sync_gmail_for_user.delay(str(current_user.id))

    return envelope({"status": "started"})


@router.post("/sync/twitter", response_model=Envelope[SyncStartedData])
async def sync_twitter(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
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


@router.post("/scores/recalculate", response_model=Envelope[ScoresRecalculatedData])
async def recalculate_scores(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ScoresRecalculatedData]:
    """Recalculate relationship scores for all contacts of the authenticated user."""
    from app.services.scoring import calculate_score

    contacts_result = await db.execute(
        select(Contact.id).where(Contact.user_id == current_user.id)
    )
    updated = 0
    for (contact_id,) in contacts_result.all():
        await calculate_score(contact_id, db)
        updated += 1

    await db.flush()
    return envelope({"updated": updated})


class BulkUpdateBody(BaseModel):
    contact_ids: list[uuid.UUID]
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None
    priority_level: str | None = None


@router.post("/bulk-update", response_model=Envelope[dict])
async def bulk_update_contacts(
    body: BulkUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Bulk update tags and/or priority level for a set of contacts."""
    result = await db.execute(
        select(Contact).where(
            Contact.id.in_(body.contact_ids),
            Contact.user_id == current_user.id,
        )
    )
    contacts = result.scalars().all()

    archive_contact_ids: list[uuid.UUID] = []
    for contact in contacts:
        if body.add_tags:
            existing = set(contact.tags or [])
            contact.tags = list(existing | set(body.add_tags))
        if body.remove_tags:
            existing = set(contact.tags or [])
            contact.tags = list(existing - set(body.remove_tags))
        if body.priority_level is not None:
            contact.priority_level = body.priority_level
            if body.priority_level == "archived":
                archive_contact_ids.append(contact.id)

    if archive_contact_ids:
        from app.models.follow_up import FollowUpSuggestion
        pending_result = await db.execute(
            select(FollowUpSuggestion).where(
                FollowUpSuggestion.contact_id.in_(archive_contact_ids),
                FollowUpSuggestion.status == "pending",
            )
        )
        for suggestion in pending_result.scalars().all():
            suggestion.status = "dismissed"

    await db.flush()
    return envelope({"updated": len(contacts)})


@router.post("/{contact_id}/enrich", response_model=Envelope[EnrichData])
async def enrich_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[EnrichData]:
    """Enrich a contact using the Apollo People Enrichment API.

    Only fills in fields that are currently empty/null on the contact.
    """
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.emails and not contact.linkedin_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact has no email or LinkedIn URL. At least one is required for enrichment.",
        )

    from app.integrations.apollo import enrich_person

    # Prefer email over LinkedIn URL for higher match quality
    enriched = await enrich_person(
        email=contact.emails[0] if contact.emails else None,
        linkedin_url=contact.linkedin_url if not contact.emails else None,
    )
    if not enriched:
        return envelope({"fields_updated": [], "source": "apollo"})

    # Simple string/scalar fields — only update if contact field is empty
    fields_updated: list[str] = []
    scalar_fields = [
        "given_name", "family_name", "full_name", "title", "company",
        "location", "linkedin_url", "twitter_handle", "avatar_url",
    ]
    for field in scalar_fields:
        if field in enriched and not getattr(contact, field, None):
            setattr(contact, field, enriched[field])
            fields_updated.append(field)

    # List fields — append new values
    if "phones" in enriched:
        existing_phones = set(contact.phones or [])
        new_phones = [p for p in enriched["phones"] if p not in existing_phones]
        if new_phones:
            contact.phones = list(existing_phones | set(new_phones))
            fields_updated.append("phones")

    if "emails" in enriched:
        existing_emails = set(contact.emails or [])
        new_emails = [e for e in enriched["emails"] if e not in existing_emails]
        if new_emails:
            contact.emails = list(existing_emails | set(new_emails))
            fields_updated.append("emails")

    if fields_updated:
        await db.flush()
        await db.refresh(contact)

    return envelope({"fields_updated": fields_updated, "source": "apollo"})


from app.core.redis import get_redis

@router.post("/{contact_id}/refresh-bios", response_model=Envelope[BioRefreshData])
async def refresh_contact_bios(
    contact_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 24h rate limit (for manual refresh)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[BioRefreshData]:
    """Check for bio updates on Twitter and Telegram for a single contact.

    Rate-limited to once per 24 hours per contact (unless force=true).
    """
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    r = get_redis()
    cache_key = f"bio_check:{contact_id}"
    if not force and await r.exists(cache_key):
        return envelope({"skipped": True, "reason": "checked_recently"})

    from app.services.bio_refresh import refresh_contact_bios as _refresh_bios, _BIO_CHECK_TTL

    changes = await _refresh_bios(contact, current_user, db)

    await r.setex(cache_key, _BIO_CHECK_TTL, "1")
    return envelope(changes)


_AVATAR_CHECK_TTL = 86400  # 24 hours


@router.post("/{contact_id}/refresh-avatar", response_model=Envelope[AvatarRefreshData])
async def refresh_contact_avatar(
    contact_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 24h rate limit (for manual refresh)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[AvatarRefreshData]:
    """Refresh a contact's avatar from Telegram or Twitter. Rate-limited to once per 24h."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    r = get_redis()
    cache_key = f"avatar_check:{contact_id}"
    if not force and await r.exists(cache_key):
        return envelope({"avatar_url": contact.avatar_url, "skipped": True, "reason": "checked_recently"})

    old_avatar = contact.avatar_url
    new_avatar = None

    # Try Telegram first
    if contact.telegram_username and current_user.telegram_session:
        try:
            from app.integrations.telegram import _make_client, _ensure_connected, _download_avatar
            client = _make_client(current_user.telegram_session)
            await _ensure_connected(client)
            try:
                username = (contact.telegram_username or "").lstrip("@").strip()
                if username:
                    entity = await client.get_input_entity(username)
                    avatar_path = await _download_avatar(client, entity, contact.id)
                    if avatar_path:
                        new_avatar = avatar_path
            finally:
                await client.disconnect()
        except Exception:
            logger.debug("Avatar refresh: Telegram failed for contact %s", contact_id)

    # Try Twitter if still no avatar
    if not new_avatar and contact.twitter_handle:
        try:
            from app.integrations.bird import fetch_user_profile_bird
            from app.integrations.twitter import download_twitter_avatar
            handle = (contact.twitter_handle or "").lstrip("@").strip()
            if handle:
                profile = await fetch_user_profile_bird(handle)
                image_url = profile.get("profileImageUrl") or profile.get("profile_image_url")
                if image_url:
                    avatar_path = await download_twitter_avatar(image_url, contact.id)
                    if avatar_path:
                        new_avatar = avatar_path
        except Exception:
            logger.debug("Avatar refresh: Twitter failed for contact %s", contact_id)

    changed = False
    if new_avatar and new_avatar != old_avatar:
        contact.avatar_url = new_avatar
        changed = True
        await db.flush()

    await r.setex(cache_key, _AVATAR_CHECK_TTL, "1")
    return envelope({"avatar_url": contact.avatar_url, "changed": changed})


# ---------------------------------------------------------------------------
# POST /api/v1/contacts/{contact_id}/sync-emails
# ---------------------------------------------------------------------------

_EMAIL_SYNC_TTL = 3600  # 1 hour


@router.post("/{contact_id}/sync-emails", response_model=Envelope[dict])
async def sync_contact_emails(
    contact_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 1h rate limit (for manual refresh)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Search Gmail for threads involving this contact's emails and save as interactions.

    Rate-limited to once per hour per contact (unless force=true).
    """
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.emails:
        return envelope({"new_interactions": 0, "skipped": True, "reason": "no_emails"})

    if not current_user.google_refresh_token:
        return envelope({"new_interactions": 0, "skipped": True, "reason": "google_not_connected"})

    r = get_redis()
    cache_key = f"email_sync:{contact_id}"
    if not force and await r.exists(cache_key):
        return envelope({"new_interactions": 0, "skipped": True, "reason": "synced_recently"})

    from app.integrations.gmail import sync_contact_emails as _sync_emails

    new_count = await _sync_emails(current_user, contact, db)

    await r.setex(cache_key, _EMAIL_SYNC_TTL, "1")
    return envelope({"new_interactions": new_count})


# ---------------------------------------------------------------------------
# POST /api/v1/contacts/{contact_id}/send-message
# ---------------------------------------------------------------------------


class SendMessageBody(BaseModel):
    message: str
    channel: str  # "telegram" | "twitter" | "email"


@router.post(
    "/{contact_id}/send-message",
    response_model=Envelope[SendMessageData],
    status_code=status.HTTP_200_OK,
)
async def send_message(
    contact_id: uuid.UUID,
    body: SendMessageBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SendMessageData]:
    """Send a message to a contact via the specified channel.

    Currently supports Telegram. Creates an Interaction record on success.
    """
    from datetime import UTC, datetime

    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.user_id == current_user.id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not body.message.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message cannot be empty")

    if body.channel == "telegram":
        username = contact.telegram_username
        if not username:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Contact has no Telegram username",
            )
        from app.integrations.telegram import send_telegram_message

        try:
            send_result = await send_telegram_message(current_user, username, body.message.strip())
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to send Telegram message to %s", username)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to send Telegram message. Please try again.",
            ) from exc
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sending via '{body.channel}' is not yet supported. Only 'telegram' is available.",
        )

    # Record the interaction
    from app.models.interaction import Interaction

    interaction = Interaction(
        contact_id=contact.id,
        user_id=current_user.id,
        platform=body.channel,
        direction="outbound",
        content_preview=body.message.strip()[:500],
        occurred_at=datetime.now(UTC),
        raw_reference_id=f"sent:{send_result.get('message_id', '')}",
    )
    db.add(interaction)

    # Update last_interaction_at and last_followup_at
    contact.last_interaction_at = datetime.now(UTC)
    contact.last_followup_at = datetime.now(UTC)
    await db.flush()

    return envelope({
        "sent": True,
        "channel": body.channel,
        "interaction_id": str(interaction.id),
    })


# ---------------------------------------------------------------------------
# Single-contact auto-tag (uses /{contact_id} prefix, safe after path params)
# ---------------------------------------------------------------------------


@router.post("/{contact_id}/auto-tag", response_model=Envelope[AutoTagResult])
async def auto_tag_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[AutoTagResult]:
    """Quick single-contact auto-tagging using the approved taxonomy."""
    from app.models.interaction import Interaction
    from app.models.tag_taxonomy import TagTaxonomy
    from app.services.auto_tagger import assign_tags, merge_tags

    # Check taxonomy
    tax_result = await db.execute(
        select(TagTaxonomy).where(
            TagTaxonomy.user_id == current_user.id,
            TagTaxonomy.status == "approved",
        )
    )
    taxonomy = tax_result.scalar_one_or_none()
    if not taxonomy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No approved taxonomy. Discover and approve tags first.",
        )

    # Fetch contact
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Get recent interactions
    int_result = await db.execute(
        select(Interaction.content_preview).where(
            Interaction.contact_id == contact_id,
            Interaction.content_preview.isnot(None),
        ).order_by(Interaction.occurred_at.desc()).limit(20)
    )
    topics = [row[0][:100] for row in int_result.all() if row[0]]

    contact_data = {
        "full_name": contact.full_name,
        "title": contact.title,
        "company": contact.company,
        "twitter_bio": contact.twitter_bio,
        "telegram_bio": contact.telegram_bio,
        "notes": contact.notes,
        "tags": contact.tags,
        "location": contact.location,
        "interaction_topics": topics,
    }

    new_tags = await assign_tags(contact_data, taxonomy.categories)
    old_tags = list(contact.tags or [])
    contact.tags = merge_tags(contact.tags, new_tags)
    tags_added = [t for t in contact.tags if t not in old_tags]

    await db.flush()
    await db.refresh(contact)

    return envelope({
        "tags_added": tags_added,
        "all_tags": contact.tags or [],
    })


# ---------------------------------------------------------------------------
# POST /api/v1/contacts/{contact_id}/compose
# ---------------------------------------------------------------------------


class ComposeBody(BaseModel):
    channel: str = "email"


@router.post("/{contact_id}/compose")
async def compose_message(
    contact_id: uuid.UUID,
    body: ComposeBody | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an AI-drafted reach-out message for a contact (no suggestion required)."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    from app.services.message_composer import compose_followup_message

    channel = body.channel if body else "email"
    message = await compose_followup_message(
        contact_id=contact_id,
        trigger_type="manual",
        event_summary=None,
        db=db,
    )

    return envelope({"suggested_message": message, "suggested_channel": channel})
