"""Identity Resolution Service — Tier 1 (deterministic) + Tier 4 (probabilistic)."""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.identity_match import IdentityMatch
from app.models.interaction import Interaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_phone(phone: str) -> str:
    """Strip all non-digit characters for phone comparison."""
    return re.sub(r"\D", "", phone)


def _normalize_name(name: str | None) -> str:
    """Lowercase and strip whitespace for fuzzy name comparison."""
    if not name:
        return ""
    return name.strip().lower()


def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    previous_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


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
                 "twitter_handle", "telegram_username", "notes"):
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
    result = await db.execute(select(Contact).where(Contact.user_id == user_id))
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
                    deleted_ids.add(contact.id)
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
                    deleted_ids.add(contact.id)
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
                    deleted_ids.add(contact.id)
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

    # Fill missing scalar fields from contact_b.
    for field in ("full_name", "given_name", "family_name", "company", "title",
                  "twitter_handle", "telegram_username", "notes"):
        if not getattr(contact_a, field) and getattr(contact_b, field):
            setattr(contact_a, field, getattr(contact_b, field))

    # Reassign interactions.
    interactions_result = await db.execute(
        select(Interaction).where(Interaction.contact_id == contact_b_id)
    )
    for interaction in interactions_result.scalars().all():
        interaction.contact_id = contact_a_id

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

    # Delete secondary contact.
    await db.delete(contact_b)
    await db.flush()
    await db.refresh(match)

    return match


# ---------------------------------------------------------------------------
# Tier 4 — Probabilistic matching (pending user confirmation)
# ---------------------------------------------------------------------------


async def find_probable_matches(user_id: uuid.UUID, db: AsyncSession) -> list[IdentityMatch]:
    """Find contacts that are probably duplicates and create pending review records.

    Matching signals:
    - Similar names (Levenshtein similarity >= 0.8).
    - Same company (case-insensitive).

    Skips pairs that already have an existing IdentityMatch record.

    Returns newly created IdentityMatch records with status="pending_review".
    """
    result = await db.execute(select(Contact).where(Contact.user_id == user_id))
    contacts: list[Contact] = list(result.scalars().all())

    # Load existing match pairs to avoid duplicates.
    existing_result = await db.execute(
        select(IdentityMatch.contact_a_id, IdentityMatch.contact_b_id)
    )
    existing_pairs: set[frozenset] = {
        frozenset([row[0], row[1]]) for row in existing_result.all()
    }

    new_matches: list[IdentityMatch] = []

    for i in range(len(contacts)):
        for j in range(i + 1, len(contacts)):
            ca, cb = contacts[i], contacts[j]
            pair = frozenset([ca.id, cb.id])
            if pair in existing_pairs:
                continue

            name_a = ca.full_name or f"{ca.given_name or ''} {ca.family_name or ''}".strip()
            name_b = cb.full_name or f"{cb.given_name or ''} {cb.family_name or ''}".strip()

            name_match = _names_similar(name_a, name_b)
            company_match = (
                bool(ca.company)
                and bool(cb.company)
                and ca.company.strip().lower() == cb.company.strip().lower()
            )

            if name_match or company_match:
                # Compute a blended score.
                score = 0.0
                if name_match:
                    score += 0.6
                if company_match:
                    score += 0.4
                score = min(score, 0.99)

                match = IdentityMatch(
                    contact_a_id=ca.id,
                    contact_b_id=cb.id,
                    match_score=score,
                    match_method="probabilistic",
                    status="pending_review",
                )
                db.add(match)
                await db.flush()
                await db.refresh(match)
                new_matches.append(match)
                existing_pairs.add(pair)

    return new_matches


# ---------------------------------------------------------------------------
# Tier 2 — Probabilistic matching (mvp.md weighted formula)
# ---------------------------------------------------------------------------


def _name_similarity(a: str, b: str) -> float:
    """Return 0.0-1.0 name similarity score."""
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0.0
    max_len = max(len(na), len(nb))
    if max_len == 0:
        return 1.0
    return 1.0 - _levenshtein(na, nb) / max_len


def _email_domain_match(emails_a: list[str] | None, emails_b: list[str] | None) -> float:
    """Return 1.0 if any email domains match (excluding common providers), else 0.0."""
    common_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "mail.com"}
    domains_a: set[str] = set()
    for e in (emails_a or []):
        parts = e.strip().lower().split("@")
        if len(parts) == 2 and parts[1] not in common_domains:
            domains_a.add(parts[1])
    for e in (emails_b or []):
        parts = e.strip().lower().split("@")
        if len(parts) == 2 and parts[1] in domains_a:
            return 1.0
    return 0.0


def _username_similarity(handle_a: str | None, handle_b: str | None) -> float:
    """Return similarity between Twitter/Telegram usernames."""
    a = (handle_a or "").strip().lower().lstrip("@")
    b = (handle_b or "").strip().lower().lstrip("@")
    if not a or not b:
        return 0.0
    max_len = max(len(a), len(b))
    return 1.0 - _levenshtein(a, b) / max_len


async def find_probabilistic_matches(user_id: uuid.UUID, db: AsyncSession) -> list[IdentityMatch]:
    """Tier 2: Weighted probabilistic matching using the formula from mvp.md.

    match_score = 0.40 * email_domain_match + 0.20 * name_similarity
                + 0.20 * company_match + 0.10 * username_similarity
                + 0.10 * mutual_signals

    - Auto-merge if score > 0.85
    - Create pending_review if 0.70 < score <= 0.85
    - Ignore if score < 0.70
    """
    result = await db.execute(select(Contact).where(Contact.user_id == user_id))
    contacts: list[Contact] = list(result.scalars().all())

    existing_result = await db.execute(
        select(IdentityMatch.contact_a_id, IdentityMatch.contact_b_id)
    )
    existing_pairs: set[frozenset] = {
        frozenset([row[0], row[1]]) for row in existing_result.all()
    }

    new_matches: list[IdentityMatch] = []
    deleted_ids: set[uuid.UUID] = set()

    for i in range(len(contacts)):
        if contacts[i].id in deleted_ids:
            continue
        for j in range(i + 1, len(contacts)):
            if contacts[j].id in deleted_ids:
                continue

            ca, cb = contacts[i], contacts[j]
            pair = frozenset([ca.id, cb.id])
            if pair in existing_pairs:
                continue

            name_a = ca.full_name or f"{ca.given_name or ''} {ca.family_name or ''}".strip()
            name_b = cb.full_name or f"{cb.given_name or ''} {cb.family_name or ''}".strip()

            # Compute weighted score
            email_score = _email_domain_match(ca.emails, cb.emails)
            name_score = _name_similarity(name_a, name_b)
            company_score = (
                1.0 if ca.company and cb.company
                and ca.company.strip().lower() == cb.company.strip().lower()
                else 0.0
            )
            username_score = max(
                _username_similarity(ca.twitter_handle, cb.twitter_handle),
                _username_similarity(ca.telegram_username, cb.telegram_username),
            )
            # Mutual signals: shared tags as a proxy
            tags_a = set(t.lower() for t in (ca.tags or []))
            tags_b = set(t.lower() for t in (cb.tags or []))
            mutual_score = (
                len(tags_a & tags_b) / max(len(tags_a | tags_b), 1)
                if tags_a or tags_b
                else 0.0
            )

            total = (
                0.40 * email_score
                + 0.20 * name_score
                + 0.20 * company_score
                + 0.10 * username_score
                + 0.10 * mutual_score
            )

            if total < 0.70:
                continue

            if total > 0.85:
                # Auto-merge
                try:
                    record = await merge_contacts(ca.id, cb.id, db)
                    record.match_score = total
                    record.match_method = "probabilistic"
                    new_matches.append(record)
                    deleted_ids.add(cb.id)
                    existing_pairs.add(pair)
                except Exception:
                    pass  # Skip if merge fails
            else:
                # Pending review
                match = IdentityMatch(
                    contact_a_id=ca.id,
                    contact_b_id=cb.id,
                    match_score=total,
                    match_method="probabilistic",
                    status="pending_review",
                )
                db.add(match)
                await db.flush()
                await db.refresh(match)
                new_matches.append(match)
                existing_pairs.add(pair)

    return new_matches
