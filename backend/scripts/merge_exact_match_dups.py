"""Merge exact-match contact duplicates across email / twitter / telegram /
linkedin axes.

A "duplicate" here is a pair of contacts (same user) sharing exactly:
  - any email (case-insensitive after lower+trim)
  - twitter_user_id (exact)
  - twitter_handle  (case-insensitive)
  - telegram_user_id (exact)
  - telegram_username (case-insensitive)
  - linkedin_profile_id (exact)

For each pair, calls services.identity_resolution.merge_contacts(), which
keeps the richer contact, unions emails/phones/tags, reassigns Interactions,
and writes ContactMerge + IdentityMatch audit rows.

Idempotent — re-running finds nothing once the dups have been merged.

Usage:
    python -m scripts.merge_exact_match_dups --dry-run
    python -m scripts.merge_exact_match_dups
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from collections import defaultdict
from typing import Iterable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("merge_exact_match_dups")


def _split_pairs(rows: list[tuple[uuid.UUID, ...]]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Group contact IDs by their dedup key, then emit (any, other) pairs."""
    by_key: dict[tuple, list[uuid.UUID]] = defaultdict(list)
    for row in rows:
        cid = row[0]
        key = row[1:]
        by_key[key].append(cid)
    pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
    for ids in by_key.values():
        if len(ids) < 2:
            continue
        # Emit (first, each other). merge_contacts handles primary selection.
        first, *rest = ids
        for other in rest:
            pairs.append((first, other))
    return pairs


async def _email_ci_pairs(db: AsyncSession) -> list[tuple[uuid.UUID, uuid.UUID]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT c.id, c.user_id, lower(trim(email)) AS norm
                FROM contacts c, unnest(c.emails) email
                WHERE email IS NOT NULL AND length(trim(email)) > 0
                """
            )
        )
    ).all()
    return _split_pairs([tuple(r) for r in rows])


async def _scalar_field_pairs(
    db: AsyncSession, field: str, *, lower: bool
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    expr = f"lower({field})" if lower else field
    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, user_id, {expr} AS norm
                FROM contacts
                WHERE {field} IS NOT NULL AND length(trim({field}::text)) > 0
                """
            )
        )
    ).all()
    return _split_pairs([tuple(r) for r in rows])


async def find_all_exact_match_pairs(db: AsyncSession) -> dict[str, list[tuple[uuid.UUID, uuid.UUID]]]:
    return {
        "email_ci": await _email_ci_pairs(db),
        "twitter_user_id": await _scalar_field_pairs(db, "twitter_user_id", lower=False),
        "twitter_handle_ci": await _scalar_field_pairs(db, "twitter_handle", lower=True),
        "telegram_user_id": await _scalar_field_pairs(db, "telegram_user_id", lower=False),
        "telegram_username_ci": await _scalar_field_pairs(db, "telegram_username", lower=True),
        "linkedin_profile_id": await _scalar_field_pairs(db, "linkedin_profile_id", lower=False),
    }


async def _merge_pair(
    db: AsyncSession, primary_id: uuid.UUID, other_id: uuid.UUID
) -> bool:
    """Attempt to merge other_id into primary_id. Returns True on success.

    Skips if either side has been deleted (already merged via another axis
    earlier in this run). Catches ValueError from merge_contacts on missing
    rows and treats it as already-merged."""
    from app.services.identity_resolution import merge_contacts

    # Verify both rows still exist (a previous merge in this run may have
    # deleted one of them).
    from app.models.contact import Contact
    a = await db.get(Contact, primary_id)
    b = await db.get(Contact, other_id)
    if a is None or b is None:
        return False
    if a.user_id != b.user_id:
        # Defensive: never merge across users.
        logger.warning(
            "skipping cross-user pair primary=%s other=%s", primary_id, other_id
        )
        return False

    await merge_contacts(primary_id, other_id, db)
    return True


async def main(*, dry_run: bool) -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        pairs_by_axis = await find_all_exact_match_pairs(db)

    total = sum(len(p) for p in pairs_by_axis.values())
    for axis, pairs in pairs_by_axis.items():
        logger.info("%s: %d pair(s)", axis, len(pairs))
        for primary_id, other_id in pairs:
            logger.info("  pair: primary=%s other=%s", primary_id, other_id)

    if dry_run:
        logger.info("[dry-run] %d total pair(s); not merging.", total)
        await engine.dispose()
        return 0

    if total == 0:
        logger.info("nothing to merge.")
        await engine.dispose()
        return 0

    # Merge in a single transaction per pair so a failure on one doesn't
    # rollback others. merge_contacts has internal flushes; we commit between.
    merged = 0
    failed = 0
    seen_axis_pairs: set[frozenset[uuid.UUID]] = set()

    for axis, pairs in pairs_by_axis.items():
        for primary_id, other_id in pairs:
            key = frozenset({primary_id, other_id})
            if key in seen_axis_pairs:
                # The same pair can show up under multiple axes (e.g. Sid Ramesh
                # has both telegram_user_id and linkedin_profile_id matches once
                # they share). Merge once.
                continue
            seen_axis_pairs.add(key)

            async with factory() as db:
                try:
                    ok = await _merge_pair(db, primary_id, other_id)
                    if ok:
                        await db.commit()
                        merged += 1
                        logger.info(
                            "merged via %s: primary=%s <- other=%s",
                            axis, primary_id, other_id,
                        )
                except Exception:
                    await db.rollback()
                    failed += 1
                    logger.exception(
                        "merge failed via %s: primary=%s other=%s",
                        axis, primary_id, other_id,
                    )

    logger.info("done. merged=%d failed=%d", merged, failed)
    await engine.dispose()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report dup pairs without merging.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run)))
