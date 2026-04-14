"""Merge duplicate LinkedIn contacts that share a linkedin_profile_id.

Usage:
    PYTHONPATH=. python scripts/dedupe_linkedin_contacts.py [--user-id UUID] [--apply]

Defaults to dry-run. Pass --apply to actually merge.

Picks the "primary" as the contact with the most interactions (ties broken by
oldest created_at), reparents all FKs pointing at the loser, back-fills blank
fields on the primary from the loser, records a ContactMerge audit row, then
deletes the loser.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from collections import defaultdict

from sqlalchemy import select, update as sa_update, delete as sa_delete, func

from app.core.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.contact_merge import ContactMerge
from app.models.detected_event import DetectedEvent
from app.models.follow_up import FollowUpSuggestion
from app.models.identity_match import IdentityMatch
from app.models.interaction import Interaction

logger = logging.getLogger(__name__)


MERGE_FIELDS = [
    "emails",
    "phones",
    "linkedin_url",
    "linkedin_profile_id",
    "linkedin_headline",
    "linkedin_bio",
    "avatar_url",
    "company",
    "title",
    "location",
    "birthday",
    "twitter_handle",
    "twitter_user_id",
    "telegram_username",
    "telegram_user_id",
    "whatsapp_phone",
    "notes",
]


def _merge_list(primary: list | None, loser: list | None) -> list | None:
    """Union-merge while preserving primary order."""
    if not loser:
        return primary
    seen = set(primary or [])
    out = list(primary or [])
    for v in loser:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


def _pick_primary(contacts: list[Contact]) -> tuple[Contact, list[Contact]]:
    """Return (primary, losers). Primary = most interactions, ties → oldest."""
    ranked = sorted(
        contacts,
        key=lambda c: (-(c.interaction_count or 0), c.created_at),
    )
    return ranked[0], ranked[1:]


async def _reparent(db, loser_id: uuid.UUID, primary_id: uuid.UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model, col in (
        (Interaction, Interaction.contact_id),
        (DetectedEvent, DetectedEvent.contact_id),
        (FollowUpSuggestion, FollowUpSuggestion.contact_id),
    ):
        res = await db.execute(
            sa_update(model).where(col == loser_id).values(contact_id=primary_id)
        )
        counts[model.__tablename__] = res.rowcount or 0

    # identity_matches has two FK columns; also collapse self-matches created by the merge
    res = await db.execute(
        sa_update(IdentityMatch)
        .where(IdentityMatch.contact_a_id == loser_id)
        .values(contact_a_id=primary_id)
    )
    counts["identity_matches.a"] = res.rowcount or 0
    res = await db.execute(
        sa_update(IdentityMatch)
        .where(IdentityMatch.contact_b_id == loser_id)
        .values(contact_b_id=primary_id)
    )
    counts["identity_matches.b"] = res.rowcount or 0
    res = await db.execute(
        sa_delete(IdentityMatch).where(IdentityMatch.contact_a_id == IdentityMatch.contact_b_id)
    )
    counts["identity_matches.self_del"] = res.rowcount or 0
    return counts


async def _merge_fields(primary: Contact, loser: Contact) -> None:
    for field in MERGE_FIELDS:
        primary_val = getattr(primary, field)
        loser_val = getattr(loser, field)
        if isinstance(primary_val, list) or isinstance(loser_val, list):
            merged = _merge_list(primary_val, loser_val)
            if merged != primary_val:
                setattr(primary, field, merged)
        elif not primary_val and loser_val:
            setattr(primary, field, loser_val)

    # Restore accurate interaction_count / last_interaction_at after reparenting
    # happens outside this helper.


async def run(user_id: uuid.UUID | None, apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Contact)
            .where(Contact.linkedin_profile_id.isnot(None))
            .order_by(Contact.user_id, Contact.linkedin_profile_id, Contact.created_at)
        )
        if user_id:
            stmt = stmt.where(Contact.user_id == user_id)
        res = await db.execute(stmt)
        all_contacts = list(res.scalars().all())

        groups: dict[tuple[uuid.UUID, str], list[Contact]] = defaultdict(list)
        for c in all_contacts:
            groups[(c.user_id, c.linkedin_profile_id)].append(c)

        dup_groups = [g for g in groups.values() if len(g) > 1]
        logger.info("Found %d duplicate groups (%d loser contacts)", len(dup_groups), sum(len(g) - 1 for g in dup_groups))

        pairs_merged = 0
        for group in dup_groups:
            primary, losers = _pick_primary(group)
            for loser in losers:
                logger.info(
                    "merge slug=%s primary=%s (%d interactions) <- loser=%s (%d interactions)",
                    primary.linkedin_profile_id,
                    primary.id,
                    primary.interaction_count or 0,
                    loser.id,
                    loser.interaction_count or 0,
                )
                if not apply:
                    continue

                counts = await _reparent(db, loser.id, primary.id)
                await _merge_fields(primary, loser)

                # Recompute interaction_count / last_interaction_at on primary
                ic_res = await db.execute(
                    select(func.count(), func.max(Interaction.occurred_at))
                    .where(Interaction.contact_id == primary.id)
                )
                ic, last_at = ic_res.one()
                primary.interaction_count = ic or 0
                if last_at:
                    primary.last_interaction_at = last_at

                db.add(
                    ContactMerge(
                        primary_contact_id=primary.id,
                        merged_contact_id=loser.id,
                        match_score=1.0,
                        match_method="linkedin_profile_id_dedupe",
                    )
                )
                await db.delete(loser)
                await db.flush()
                pairs_merged += 1
                logger.info("  reparented: %s", counts)

        if apply:
            await db.commit()
            logger.info("Committed %d merges", pairs_merged)
        else:
            logger.info("DRY RUN — no changes written. Re-run with --apply.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=uuid.UUID, default=None, help="Restrict to a single user")
    parser.add_argument("--apply", action="store_true", help="Actually perform the merges (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(run(args.user_id, args.apply))


if __name__ == "__main__":
    main()
