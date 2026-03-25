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


def _compute_adaptive_score(ca: Contact, cb: Contact) -> float:
    """Compute a match score using adaptive weights.

    Base weights: email_domain=0.40, name=0.20, company=0.20, username=0.10, mutual=0.10
    When a signal is *unavailable* on either contact (e.g. neither has email),
    its weight is redistributed proportionally to the remaining signals.
    This ensures that two contacts matching only on name can still score high
    enough to surface as candidates.

    Names shorter than 6 characters are penalized (common first-name collisions).
    """
    BASE_WEIGHTS = {
        "email": 0.40,
        "name": 0.20,
        "company": 0.20,
        "username": 0.10,
        "mutual": 0.10,
    }

    name_a = ca.full_name or f"{ca.given_name or ''} {ca.family_name or ''}".strip()
    name_b = cb.full_name or f"{cb.given_name or ''} {cb.family_name or ''}".strip()

    # Raw scores
    email_score = _email_domain_match(ca.emails, cb.emails)

    # Name score: also check email local parts as a name proxy.
    # E.g. "pengcheng.chen@gmail.com" vs contact named "Pengcheng Chen"
    name_score = _name_similarity(name_a, name_b)
    if name_score < 0.8:
        # Try matching name against email-derived names
        for emails, name in [(ca.emails, name_b), (cb.emails, name_a)]:
            if not name:
                continue
            for email in (emails or []):
                tokens = _extract_name_tokens_from_email(email)
                if tokens:
                    email_name = " ".join(tokens)
                    sim = _name_similarity(email_name, name)
                    if sim > name_score:
                        name_score = sim
    company_score = (
        1.0 if ca.company and cb.company
        and ca.company.strip().lower() == cb.company.strip().lower()
        else 0.0
    )
    username_score = max(
        _username_similarity(ca.twitter_handle, cb.twitter_handle),
        _username_similarity(ca.telegram_username, cb.telegram_username),
    )
    tags_a = set(t.lower() for t in (ca.tags or []))
    tags_b = set(t.lower() for t in (cb.tags or []))
    mutual_score = (
        len(tags_a & tags_b) / max(len(tags_a | tags_b), 1)
        if tags_a or tags_b
        else 0.0
    )

    scores = {
        "email": email_score,
        "name": name_score,
        "company": company_score,
        "username": username_score,
        "mutual": mutual_score,
    }

    # Determine which signals are *available* (both contacts have the data).
    has_email = bool(ca.emails) and bool(cb.emails)
    has_company = bool(ca.company) and bool(cb.company)
    has_username = (bool(ca.twitter_handle) and bool(cb.twitter_handle)) or (
        bool(ca.telegram_username) and bool(cb.telegram_username)
    )
    has_mutual = bool(tags_a) and bool(tags_b)
    # Name is available if both have names, OR if email-to-name matching produced a score.
    has_name = (bool(name_a) and bool(name_b)) or name_score > 0

    available = {
        "email": has_email,
        "name": has_name,
        "company": has_company,
        "username": has_username,
        "mutual": has_mutual,
    }

    active_weight_sum = sum(BASE_WEIGHTS[k] for k, v in available.items() if v)
    if active_weight_sum == 0:
        return 0.0

    # Redistribute: each active signal gets its base weight scaled up so active
    # weights sum to 1.0.
    total = 0.0
    for key in BASE_WEIGHTS:
        if available[key]:
            weight = BASE_WEIGHTS[key] / active_weight_sum
            total += weight * scores[key]

    # Guard: company + email_domain are correlated (colleagues share both).
    # If names clearly differ, cap the score to prevent false positives.
    if has_name and name_score < 0.5 and company_score == 1.0 and email_score == 1.0:
        total = min(total, 0.35)  # Below the 0.40 display threshold

    # Guard: company match alone (without name similarity) should not surface
    # as a duplicate — two different people at the same company are not dupes.
    if has_name and name_score < 0.5 and company_score == 1.0 and email_score == 0.0:
        total = min(total, 0.35)

    # Penalty: short names (< 6 chars) are likely first-name-only collisions
    # ("Alex", "David") — reduce confidence when name is the dominant signal.
    # Use the longest available name (including email-derived) for the length check.
    effective_name_len = max(len(name_a), len(name_b))
    if has_name and effective_name_len < 6 and not has_email and not has_company:
        total *= 0.5

    # Cap: when name is the *only* signal, cap at 0.85 to force human review
    # instead of auto-merging (two different people can share a name).
    active_count = sum(1 for v in available.values() if v)
    if active_count == 1 and has_name:
        total = min(total, 0.85)

    return total


def _extract_name_tokens_from_email(email: str) -> list[str]:
    """Extract potential name tokens from an email local part.

    E.g. 'pengcheng.chen@gmail.com' -> ['pengcheng', 'chen']
         'john_smith@company.com' -> ['john', 'smith']
    """
    local = email.strip().lower().split("@")[0]
    # Split on dots, underscores, dashes, plus signs
    tokens = re.split(r"[._\-+]", local)
    # Filter out short/numeric-only tokens
    return [t for t in tokens if len(t) >= 3 and not t.isdigit()]


def _build_blocking_keys(contact: Contact) -> list[str]:
    """Generate blocking keys for a contact.

    Contacts are only compared if they share at least one blocking key.
    This reduces O(n²) to O(n * block_size) in practice.
    """
    keys: list[str] = []
    name = _normalize_name(
        contact.full_name
        or f"{contact.given_name or ''} {contact.family_name or ''}".strip()
    )
    if name:
        # First 3 chars of name — catches similar names
        keys.append(f"name:{name[:3]}")
        # Each name token (for matching "John Smith" with "John S.")
        for token in name.split():
            if len(token) >= 3:
                keys.append(f"token:{token}")
    if contact.company:
        keys.append(f"company:{contact.company.strip().lower()}")
    for email in (contact.emails or []):
        parts = email.strip().lower().split("@")
        if len(parts) == 2:
            keys.append(f"domain:{parts[1]}")
        # Extract name tokens from email local part for cross-signal blocking
        for token in _extract_name_tokens_from_email(email):
            keys.append(f"token:{token}")
    if contact.twitter_handle:
        keys.append(f"twitter:{contact.twitter_handle.strip().lower().lstrip('@')}")
    if contact.telegram_username:
        keys.append(f"telegram:{contact.telegram_username.strip().lower().lstrip('@')}")
    if contact.linkedin_profile_id:
        keys.append(f"linkedin:{contact.linkedin_profile_id.strip().lower()}")
    return keys


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
    result = await db.execute(select(Contact).where(Contact.user_id == user_id))
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
