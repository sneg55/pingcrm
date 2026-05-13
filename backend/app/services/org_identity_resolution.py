"""Organization deduplication: deterministic + probabilistic matching and merging."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization
from app.services.org_identity_scoring import (
    _normalize_website,
    _same_linkedin,
    _same_non_generic_domain,
)

logger = logging.getLogger(__name__)

# Fields that get copied source -> target when target has no value
_MERGE_FILL_FIELDS = (
    "domain", "industry", "location", "website",
    "linkedin_url", "twitter_handle", "notes", "logo_url",
)


async def merge_org_pair(
    target: Organization, source: Organization, db: AsyncSession
) -> int:
    """Move source's contacts to target, fill target's null fields from source, delete source.

    Returns the number of contacts moved.

    Conservative on field merge: never overwrites a non-null target field.
    Caller is responsible for choosing which org is the target (typically the
    one with more contacts).
    """
    if target.user_id != source.user_id:
        raise ValueError("Cannot merge orgs across different users")
    if target.id == source.id:
        return 0

    # Fill any null target fields from source
    for field in _MERGE_FILL_FIELDS:
        if getattr(target, field, None) is None:
            src_val = getattr(source, field, None)
            if src_val is not None:
                setattr(target, field, src_val)

    # Move contacts from source to target
    move_result = await db.execute(
        update(Contact)
        .where(
            Contact.organization_id == source.id,
            Contact.user_id == target.user_id,
        )
        .values(organization_id=target.id, company=target.name)
    )
    moved = move_result.rowcount or 0

    # Delete source
    await db.execute(
        delete(Organization).where(
            Organization.id == source.id,
            Organization.user_id == target.user_id,
        )
    )

    logger.info(
        "merge_org_pair: moved %d contacts from %s -> %s",
        moved, source.id, target.id,
        extra={"target_id": str(target.id), "source_id": str(source.id)},
    )
    return moved


async def find_deterministic_org_matches(
    user_id: uuid.UUID, db: AsyncSession,
) -> list[tuple[Organization, Organization, str]]:
    """Find org pairs that should auto-merge with no review.

    Returns a list of (org_a, org_b, match_method) tuples. match_method is one of:
      - "deterministic_domain"
      - "deterministic_linkedin"
      - "deterministic_name_website"

    Each pair is returned at most once. Convention: org_a.id < org_b.id.
    """
    result = await db.execute(
        select(Organization).where(Organization.user_id == user_id)
    )
    orgs: list[Organization] = list(result.scalars().all())

    pairs: list[tuple[Organization, Organization, str]] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for i, a in enumerate(orgs):
        for b in orgs[i + 1:]:
            if a.id < b.id:
                first, second = a, b
            else:
                first, second = b, a
            key = (first.id, second.id)
            if key in seen:
                continue

            method: str | None = None
            if _same_non_generic_domain(a.domain, b.domain):
                method = "deterministic_domain"
            elif _same_linkedin(a.linkedin_url, b.linkedin_url):
                method = "deterministic_linkedin"
            else:
                na = (a.name or "").strip().lower()
                nb = (b.name or "").strip().lower()
                if na and na == nb:
                    nwa = _normalize_website(a.website)
                    nwb = _normalize_website(b.website)
                    if nwa and nwa == nwb:
                        method = "deterministic_name_website"

            if method is not None:
                seen.add(key)
                pairs.append((first, second, method))

    return pairs
