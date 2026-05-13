"""Organization deduplication: deterministic + probabilistic matching and merging."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.org_identity_match import OrgIdentityMatch
from app.models.organization import Organization
from app.services.org_identity_scoring import (
    _normalize_website,
    _same_linkedin,
    _same_non_generic_domain,
    _shares_anchor,
    compute_org_adaptive_score,
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


# Below this, surface to review queue. Above 0.95, auto-merge (treated as Tier 1).
PROBABILISTIC_REVIEW_THRESHOLD = 0.40
PROBABILISTIC_AUTOMERGE_THRESHOLD = 0.95


async def find_probabilistic_org_matches(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    exclude_ids: set[uuid.UUID],
) -> list[tuple[Organization, Organization, float]]:
    """Score org pairs and return those above the review threshold.

    Skips pairs where either org is in *exclude_ids* (used to skip orgs that
    were already auto-merged in the deterministic pass).

    Returns (org_a, org_b, score) with org_a.id < org_b.id.
    Score >= PROBABILISTIC_AUTOMERGE_THRESHOLD → caller should auto-merge.
    Score in [PROBABILISTIC_REVIEW_THRESHOLD, PROBABILISTIC_AUTOMERGE_THRESHOLD) → queue.
    """
    result = await db.execute(
        select(Organization).where(Organization.user_id == user_id)
    )
    orgs: list[Organization] = [
        o for o in result.scalars().all() if o.id not in exclude_ids
    ]

    pairs: list[tuple[Organization, Organization, float]] = []
    for i, a in enumerate(orgs):
        for b in orgs[i + 1:]:
            if not _shares_anchor(a, b):
                continue
            score = compute_org_adaptive_score(a, b)
            if score < PROBABILISTIC_REVIEW_THRESHOLD:
                continue
            if a.id < b.id:
                pairs.append((a, b, score))
            else:
                pairs.append((b, a, score))

    return pairs


async def _prune_stale_pending_matches(
    user_id: uuid.UUID, db: AsyncSession,
) -> int:
    """Delete pending_review matches whose pair would no longer score above
    the review threshold under the current scorer. Returns count deleted.

    Resolved matches (merged/dismissed) are preserved as audit trail.
    """
    pending_result = await db.execute(
        select(OrgIdentityMatch).where(
            OrgIdentityMatch.user_id == user_id,
            OrgIdentityMatch.status == "pending_review",
            OrgIdentityMatch.match_method == "probabilistic",
        )
    )
    pending = list(pending_result.scalars().all())
    if not pending:
        return 0

    org_ids = {m.org_a_id for m in pending} | {m.org_b_id for m in pending}
    org_result = await db.execute(
        select(Organization).where(Organization.id.in_(org_ids))
    )
    orgs_by_id = {o.id: o for o in org_result.scalars().all()}

    deleted = 0
    for m in pending:
        org_a = orgs_by_id.get(m.org_a_id)
        org_b = orgs_by_id.get(m.org_b_id)
        if org_a is None or org_b is None:
            await db.delete(m)
            deleted += 1
            continue
        if compute_org_adaptive_score(org_a, org_b) < PROBABILISTIC_REVIEW_THRESHOLD:
            await db.delete(m)
            deleted += 1
    return deleted


async def _count_contacts(org_id: uuid.UUID, db: AsyncSession) -> int:
    """Return the number of contacts assigned to an org."""
    result = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.organization_id == org_id)
    )
    return result.scalar() or 0


async def _pick_target(
    a: Organization, b: Organization, db: AsyncSession
) -> tuple[Organization, Organization]:
    """Return (target, source) — target is the org with more contacts.

    Ties broken by older created_at (the older org is more "canonical").
    """
    count_a = await _count_contacts(a.id, db)
    count_b = await _count_contacts(b.id, db)
    if count_a > count_b:
        return a, b
    if count_b > count_a:
        return b, a
    if (a.created_at or b.created_at) and a.created_at <= b.created_at:
        return a, b
    return b, a


async def scan_org_duplicates(
    user_id: uuid.UUID, db: AsyncSession,
) -> dict:
    """Full scan: auto-merge deterministic pairs, queue probabilistic ones.

    Returns {"matches_found", "auto_merged", "pending_review"}.
    """
    auto_merged = 0
    merged_org_ids: set[uuid.UUID] = set()

    # Tier 1: deterministic auto-merge
    deterministic = await find_deterministic_org_matches(user_id, db)
    for a, b, _method in deterministic:
        if a.id in merged_org_ids or b.id in merged_org_ids:
            continue
        target, source = await _pick_target(a, b, db)
        await merge_org_pair(target, source, db)
        merged_org_ids.add(source.id)
        auto_merged += 1
    if deterministic:
        await db.flush()

    # Prune stale pending_review matches that no longer score above threshold
    # (e.g., scoring algorithm tightened, or one of the orgs was edited so the
    # pair no longer looks similar). Keeps the review queue self-healing.
    pruned = await _prune_stale_pending_matches(user_id, db)
    if pruned:
        await db.flush()

    # Tier 2: probabilistic
    probabilistic = await find_probabilistic_org_matches(
        user_id, db, exclude_ids=merged_org_ids,
    )

    # Pre-load existing matches for this user so we can dedup before inserting
    # (the DB unique index is a backstop, but async session state is tricky
    # after IntegrityError, so we pre-check in Python).
    existing_result = await db.execute(
        select(OrgIdentityMatch.org_a_id, OrgIdentityMatch.org_b_id).where(
            OrgIdentityMatch.user_id == user_id
        )
    )
    existing_pairs: set[frozenset[uuid.UUID]] = {
        frozenset((row[0], row[1])) for row in existing_result.all()
    }

    pending_review = 0
    for a, b, score in probabilistic:
        if score >= PROBABILISTIC_AUTOMERGE_THRESHOLD:
            target, source = await _pick_target(a, b, db)
            await merge_org_pair(target, source, db)
            merged_org_ids.add(source.id)
            auto_merged += 1
            continue

        pair_key = frozenset((a.id, b.id))
        if pair_key in existing_pairs:
            continue

        match = OrgIdentityMatch(
            user_id=user_id,
            org_a_id=a.id,
            org_b_id=b.id,
            match_score=score,
            match_method="probabilistic",
            status="pending_review",
        )
        db.add(match)
        existing_pairs.add(pair_key)
        pending_review += 1

    if pending_review:
        await db.flush()

    return {
        "matches_found": auto_merged + pending_review,
        "auto_merged": auto_merged,
        "pending_review": pending_review,
    }
