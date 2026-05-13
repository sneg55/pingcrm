"""Organization deduplication: deterministic + probabilistic matching and merging."""
from __future__ import annotations

import logging

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization

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
