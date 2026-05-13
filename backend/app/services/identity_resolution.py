"""Identity Resolution Service — Tier 1 (deterministic) + Tier 4 (probabilistic)."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.models.contact import Contact
from app.models.identity_match import IdentityMatch
from app.models.interaction import Interaction
from app.services.identity_scoring import (
    _build_blocking_keys,
    _compute_adaptive_score,
    _email_domain_match,
    _extract_name_tokens_from_email,
    _levenshtein,
    _name_similarity,
    _normalize_name,
    _username_similarity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_phone(phone: str) -> str:
    """Strip all non-digit characters for phone comparison."""
    return re.sub(r"\D", "", phone)


def _names_similar(a: str, b: str, threshold: float = 0.8) -> bool:
    """Return True when the two names are similar enough (similarity >= threshold)."""
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return False
    max_len = max(len(na), len(nb))
    if max_len == 0:
        return True
    distance = _levenshtein(na, nb)
    similarity = 1.0 - distance / max_len
    return similarity >= threshold


def _contact_data_weight(contact: Contact) -> int:
    """Count non-null fields as a rough measure of how 'complete' a contact is."""
    score = 0
    for attr in ("full_name", "given_name", "family_name", "company", "title",
                 "twitter_handle", "twitter_bio", "telegram_username", "telegram_bio",
                 "linkedin_url", "linkedin_profile_id", "linkedin_headline", "linkedin_bio",
                 "notes", "source"):
        if getattr(contact, attr):
            score += 1
    score += len(contact.emails or [])
    score += len(contact.phones or [])
    score += len(contact.tags or [])
    return score


# ---------------------------------------------------------------------------
# Tier 1 — Deterministic matching
# ---------------------------------------------------------------------------


async def find_deterministic_matches(user_id: uuid.UUID, db: AsyncSession) -> list[IdentityMatch]:
    """Scan all contacts for a user and auto-merge deterministic duplicates.

    Matching rules:
    - Same email appears in two different contacts.
    - Same normalised phone number appears in two different contacts.
    - Twitter bio contains an email that matches another contact.

    Returns a list of IdentityMatch records that were created (already merged).
    """
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.priority_level != "archived",
        )
    )
    contacts: list[Contact] = list(result.scalars().all())

    merged_records: list[IdentityMatch] = []
    # Track contacts that have been deleted mid-loop so we skip stale references.
    deleted_ids: set[uuid.UUID] = set()

    # Build lookup structures for O(n) detection.
    email_map: dict[str, uuid.UUID] = {}   # email -> first contact id seen
    phone_map: dict[str, uuid.UUID] = {}   # normalised phone -> first contact id seen

    for contact in contacts:
        for email in (contact.emails or []):
            email_lower = email.strip().lower()
            if not email_lower:
                continue
            if email_lower in email_map:
                other_id = email_map[email_lower]
                if other_id != contact.id and other_id not in deleted_ids and contact.id not in deleted_ids:
                    record = await merge_contacts(other_id, contact.id, db)
                    merged_records.append(record)
                    # merge_contacts may swap primary/secondary; track the deleted one
                    survivor = record.contact_a_id
                    for cid in (other_id, contact.id):
                        if cid != survivor:
                            deleted_ids.add(cid)
                    # Update email_map to point to survivor
                    email_map[email_lower] = survivor
                    break  # contact is gone; stop processing its emails
            else:
                email_map[email_lower] = contact.id

        if contact.id in deleted_ids:
            continue

        for phone in (contact.phones or []):
            norm = _normalize_phone(phone)
            if not norm:
                continue
            if norm in phone_map:
                other_id = phone_map[norm]
                if other_id != contact.id and other_id not in deleted_ids and contact.id not in deleted_ids:
                    record = await merge_contacts(other_id, contact.id, db)
                    merged_records.append(record)
                    survivor = record.contact_a_id
                    for cid in (other_id, contact.id):
                        if cid != survivor:
                            deleted_ids.add(cid)
                    phone_map[norm] = survivor
                    break
            else:
                phone_map[norm] = contact.id

    # Twitter bio email check — requires an extra pass over contacts that have
    # a twitter_handle.  We rely on caller to have stored the bio in notes or a
    # dedicated field.  Here we scan the notes field for email-like strings.
    email_pattern = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    all_contact_emails: dict[str, uuid.UUID] = {
        e.strip().lower(): c.id
        for c in contacts
        if c.id not in deleted_ids
        for e in (c.emails or [])
        if e.strip()
    }

    for contact in contacts:
        if contact.id in deleted_ids:
            continue
        if not contact.notes:
            continue
        found_emails = email_pattern.findall(contact.notes)
        for found_email in found_emails:
            fe = found_email.strip().lower()
            if fe in all_contact_emails:
                other_id = all_contact_emails[fe]
                if (
                    other_id != contact.id
                    and other_id not in deleted_ids
                    and contact.id not in deleted_ids
                ):
                    record = await merge_contacts(other_id, contact.id, db)
                    merged_records.append(record)
                    survivor = record.contact_a_id
                    for cid in (other_id, contact.id):
                        if cid != survivor:
                            deleted_ids.add(cid)
                    break

    return merged_records


async def merge_contacts(
    contact_a_id: uuid.UUID,
    contact_b_id: uuid.UUID,
    db: AsyncSession,
) -> IdentityMatch:
    """Merge contact_b into contact_a (or swap to keep the richer one as primary).

    - Keeps the contact with more data as primary.
    - Merges emails[], phones[], tags[] (union, preserving order).
    - Reassigns Interaction rows from contact_b to contact_a.
    - Creates an IdentityMatch record with status="merged".
    - Deletes contact_b.
    """
    res_a = await db.execute(select(Contact).where(Contact.id == contact_a_id))
    contact_a = res_a.scalar_one_or_none()

    res_b = await db.execute(select(Contact).where(Contact.id == contact_b_id))
    contact_b = res_b.scalar_one_or_none()

    if contact_a is None or contact_b is None:
        raise ValueError(
            f"merge_contacts: one or both contacts not found "
            f"({contact_a_id}, {contact_b_id})"
        )

    # Decide which is primary (keep the richer contact as contact_a).
    if _contact_data_weight(contact_b) > _contact_data_weight(contact_a):
        contact_a, contact_b = contact_b, contact_a
        contact_a_id, contact_b_id = contact_b_id, contact_a_id

    # Merge list fields (union, order-preserving, case-insensitive dedup for emails).
    def _merge_list(primary: list[str] | None, secondary: list[str] | None) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in list(primary or []) + list(secondary or []):
            key = item.strip().lower()
            if key not in seen:
                seen.add(key)
                result.append(item.strip())
        return result

    contact_a.emails = _merge_list(contact_a.emails, contact_b.emails)
    contact_a.phones = _merge_list(contact_a.phones, contact_b.phones)
    contact_a.tags = _merge_list(contact_a.tags, contact_b.tags)

    # Clear unique-constrained fields on contact_b FIRST and flush, so that
    # copying values to contact_a doesn't violate uniqueness constraints
    # (both contacts exist in the same transaction until contact_b is deleted).
    # Capture values before clearing so we can copy them to contact_a.
    b_unique_fields = {
        "telegram_username": contact_b.telegram_username,
        "telegram_user_id": contact_b.telegram_user_id,
        "twitter_handle": contact_b.twitter_handle,
        "twitter_user_id": contact_b.twitter_user_id,
        "linkedin_profile_id": contact_b.linkedin_profile_id,
    }
    contact_b.telegram_username = None
    contact_b.telegram_user_id = None
    contact_b.twitter_handle = None
    contact_b.twitter_user_id = None
    contact_b.linkedin_profile_id = None
    await db.flush()

    # Fill missing scalar fields from contact_b (using captured values for unique fields).
    for field in ("full_name", "given_name", "family_name", "company", "title",
                  "twitter_bio", "telegram_bio",
                  "linkedin_url", "linkedin_headline", "linkedin_bio",
                  "notes", "source"):
        if not getattr(contact_a, field) and getattr(contact_b, field):
            setattr(contact_a, field, getattr(contact_b, field))

    # Copy unique-constrained fields from captured values (now safe since contact_b is cleared).
    for field, value in b_unique_fields.items():
        if not getattr(contact_a, field) and value:
            setattr(contact_a, field, value)

    # Keep the better relationship score
    if (contact_b.relationship_score or 0) > (contact_a.relationship_score or 0):
        contact_a.relationship_score = contact_b.relationship_score

    # Keep the most recent interaction timestamp
    if contact_b.last_interaction_at and (
        not contact_a.last_interaction_at or contact_b.last_interaction_at > contact_a.last_interaction_at
    ):
        contact_a.last_interaction_at = contact_b.last_interaction_at

    # Reassign interactions.
    interactions_result = await db.execute(
        select(Interaction).where(Interaction.contact_id == contact_b_id)
    )
    for interaction in interactions_result.scalars().all():
        interaction.contact_id = contact_a_id

    await db.flush()

    # Record in audit trail (survives contact deletion).
    from app.models.contact_merge import ContactMerge
    db.add(ContactMerge(
        primary_contact_id=contact_a_id,
        merged_contact_id=contact_b_id,
        match_score=1.0,
        match_method="deterministic",
    ))
    await db.flush()

    # Create IdentityMatch record.
    match = IdentityMatch(
        contact_a_id=contact_a_id,
        contact_b_id=contact_b_id,
        match_score=1.0,
        match_method="deterministic",
        status="merged",
        resolved_at=datetime.now(UTC),
    )
    db.add(match)
    await db.flush()

    # Delete secondary contact. contact_b_id FK is SET NULL so the
    # IdentityMatch record survives with contact_b_id=NULL.
    await db.delete(contact_b)
    await db.flush()

    # The CASCADE SET NULL makes contact_b_id NULL in DB; update in-memory.
    match.contact_b_id = None

    return match


# ---------------------------------------------------------------------------
# Tier 2 — Probabilistic matching (mvp.md weighted formula)
# ---------------------------------------------------------------------------


def _same_source(ca: Contact, cb: Contact) -> bool:
    """Return True if both contacts originate from the same platform.

    Two contacts from the same source (e.g. both Telegram, both LinkedIn)
    have unique identifiers on that platform and are definitively different
    people. Duplicates only occur across different sources.
    """
    # Check platform-specific identifiers: if both have an ID on the same
    # platform, they were independently created from that platform.
    if ca.telegram_user_id and cb.telegram_user_id:
        return True
    if ca.telegram_username and cb.telegram_username:
        return True
    if ca.linkedin_profile_id and cb.linkedin_profile_id:
        return True
    if ca.twitter_user_id and cb.twitter_user_id:
        return True
    if ca.twitter_handle and cb.twitter_handle:
        return True
    return False


# ---------------------------------------------------------------------------
# Public wrappers — use these instead of the private _-prefixed functions
# ---------------------------------------------------------------------------


def compute_adaptive_score(ca: Contact, cb: Contact) -> float:
    """Public alias for :func:`_compute_adaptive_score`."""
    return _compute_adaptive_score(ca, cb)


def build_blocking_keys(contact: Contact) -> list[str]:
    """Public alias for :func:`_build_blocking_keys`."""
    return _build_blocking_keys(contact)


async def find_probabilistic_matches(user_id: uuid.UUID, db: AsyncSession) -> list[IdentityMatch]:
    """Tier 2: Weighted probabilistic matching with adaptive weights.

    Base weights: email_domain=0.40, name=0.20, company=0.20, username=0.10, mutual=0.10
    Weights are redistributed when signals are unavailable on either contact.

    Uses blocking keys to avoid O(n²) full comparison — only contacts that share
    a blocking key (name prefix, company, email domain, username) are compared.

    - Auto-merge if score > 0.85
    - Create pending_review if 0.70 < score <= 0.85
    - Ignore if score < 0.70
    """
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.priority_level != "archived",
        )
    )
    contacts: list[Contact] = list(result.scalars().all())

    # Scope existing pairs query to this user's contacts.
    user_contact_ids = select(Contact.id).where(Contact.user_id == user_id)
    existing_result = await db.execute(
        select(IdentityMatch.contact_a_id, IdentityMatch.contact_b_id).where(
            IdentityMatch.contact_a_id.in_(user_contact_ids)
        )
    )
    existing_pairs: set[frozenset] = {
        frozenset([row[0], row[1]]) for row in existing_result.all()
    }

    # Build blocking index: key -> list of contact indices
    from collections import defaultdict
    block_index: dict[str, list[int]] = defaultdict(list)
    contact_by_idx: dict[int, Contact] = {}
    for idx, contact in enumerate(contacts):
        contact_by_idx[idx] = contact
        for bk in _build_blocking_keys(contact):
            block_index[bk].append(idx)

    # Collect candidate pairs from blocking (deduplicated)
    candidate_pairs: set[tuple[int, int]] = set()
    for indices in block_index.values():
        if len(indices) > 500:
            # Skip overly broad blocks (e.g. "domain:gmail.com")
            continue
        for ii in range(len(indices)):
            for jj in range(ii + 1, len(indices)):
                a, b = indices[ii], indices[jj]
                candidate_pairs.add((min(a, b), max(a, b)))

    new_matches: list[IdentityMatch] = []
    deleted_ids: set[uuid.UUID] = set()

    for i, j in candidate_pairs:
        ca, cb = contact_by_idx[i], contact_by_idx[j]
        if ca.id == cb.id:
            continue
        if ca.id in deleted_ids or cb.id in deleted_ids:
            continue

        # Skip same-source pairs: two contacts from the same platform have
        # unique identifiers on that platform — they're different people.
        if _same_source(ca, cb):
            continue

        pair = frozenset([ca.id, cb.id])
        if pair in existing_pairs:
            continue

        total = _compute_adaptive_score(ca, cb)

        if total < 0.70:
            continue

        if total > 0.85:
            # Auto-merge (merge_contacts picks the richer contact as primary
            # and deletes the other — track both IDs as potentially deleted)
            try:
                record = await merge_contacts(ca.id, cb.id, db)
                record.match_score = total
                record.match_method = "probabilistic"
                new_matches.append(record)
                # One of the two was deleted; add both to be safe
                # (merge_contacts may swap primary/secondary)
                deleted_ids.add(ca.id)
                deleted_ids.add(cb.id)
                # Re-add the surviving contact (contact_a_id is always the primary)
                deleted_ids.discard(record.contact_a_id)
                existing_pairs.add(pair)
            except Exception:
                logger.warning("Auto-merge failed for contacts %s + %s", ca.id, cb.id, exc_info=True)
        else:
            # Pending review
            try:
                match = IdentityMatch(
                    contact_a_id=ca.id,
                    contact_b_id=cb.id,
                    match_score=total,
                    match_method="probabilistic",
                    status="pending_review",
                )
                db.add(match)
                await db.flush()
                new_matches.append(match)
                existing_pairs.add(pair)
            except Exception:
                logger.warning("Failed to create pending match for %s + %s", ca.id, cb.id, exc_info=True)

    return new_matches
