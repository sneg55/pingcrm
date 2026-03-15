from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.contacts_routes.shared import (
    Contact,
    Depends,
    Envelope,
    HTTPException,
    AsyncSession,
    User,
    envelope,
    get_current_user,
    get_db,
    select,
    status,
)
from app.schemas.responses import ApplyTagsResult, AutoTagResult, TaxonomyResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


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
