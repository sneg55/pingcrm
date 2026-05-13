"""Identity-resolution scoring primitives.

Pure helpers (no DB I/O) used by app.services.identity_resolution to compute
adaptive match scores and blocking keys.
"""
from __future__ import annotations

import re

from app.models.contact import Contact


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


def _name_similarity(a: str, b: str) -> float:
    """Return 0.0-1.0 name similarity score."""
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0.0
    max_len = max(len(na), len(nb))
    if max_len == 0:
        return 1.0

    base_score = 1.0 - _levenshtein(na, nb) / max_len

    tokens_a = na.split()
    tokens_b = nb.split()
    if len(tokens_a) >= 2 and len(tokens_b) >= 2:
        first_a, last_a = tokens_a[0], tokens_a[-1]
        first_b, last_b = tokens_b[0], tokens_b[-1]
        first_sim = 1.0 - _levenshtein(first_a, first_b) / max(len(first_a), len(first_b))
        last_sim = 1.0 - _levenshtein(last_a, last_b) / max(len(last_a), len(last_b))
        if first_sim < 0.6 or last_sim < 0.6:
            return min(base_score, 0.30)

    return base_score


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


def _extract_name_tokens_from_email(email: str) -> list[str]:
    """Extract potential name tokens from an email local part."""
    local = email.strip().lower().split("@")[0]
    tokens = re.split(r"[._\-+]", local)
    return [t for t in tokens if len(t) >= 3 and not t.isdigit()]


def _compute_adaptive_score(ca: Contact, cb: Contact) -> float:
    """Compute a match score using adaptive weights.

    Base weights: email_domain=0.40, name=0.20, company=0.20, username=0.10, mutual=0.10
    When a signal is *unavailable* on either contact, its weight is redistributed
    proportionally to the remaining signals.
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

    email_score = _email_domain_match(ca.emails, cb.emails)

    name_score = _name_similarity(name_a, name_b)
    if name_score < 0.8:
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

    has_email = bool(ca.emails) and bool(cb.emails)
    has_company = bool(ca.company) and bool(cb.company)
    has_username = (bool(ca.twitter_handle) and bool(cb.twitter_handle)) or (
        bool(ca.telegram_username) and bool(cb.telegram_username)
    )
    has_mutual = bool(tags_a) and bool(tags_b)
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

    total = 0.0
    for key in BASE_WEIGHTS:
        if available[key]:
            weight = BASE_WEIGHTS[key] / active_weight_sum
            total += weight * scores[key]

    # Guards: company + email-domain colleagues; same domain different names; etc.
    if has_name and name_score < 0.5 and company_score == 1.0 and email_score == 1.0:
        total = min(total, 0.35)
    if has_name and name_score < 0.5 and company_score == 1.0 and email_score == 0.0:
        total = min(total, 0.35)
    if has_email and email_score == 1.0 and has_name and name_score < 0.7:
        total = min(total, 0.35)

    name_a_tokens = len(name_a.split()) if name_a else 0
    name_b_tokens = len(name_b.split()) if name_b else 0
    is_single_token = name_a_tokens <= 1 or name_b_tokens <= 1

    if has_name and is_single_token:
        if not has_email and not has_company and not has_username:
            total = min(total * 0.4, 0.50)
        elif has_company and company_score == 0.0:
            total = min(total, 0.35)
        elif has_username and username_score < 0.3:
            total = min(total, 0.45)

    active_count = sum(1 for v in available.values() if v)
    if active_count == 1 and has_name:
        total = min(total, 0.70)

    return total


def _build_blocking_keys(contact: Contact) -> list[str]:
    """Generate blocking keys for a contact.

    Contacts are only compared if they share at least one blocking key.
    """
    keys: list[str] = []
    name = _normalize_name(
        contact.full_name
        or f"{contact.given_name or ''} {contact.family_name or ''}".strip()
    )
    if name:
        keys.append(f"name:{name[:3]}")
        for token in name.split():
            if len(token) >= 3:
                keys.append(f"token:{token}")
    if contact.company:
        keys.append(f"company:{contact.company.strip().lower()}")
    for email in (contact.emails or []):
        parts = email.strip().lower().split("@")
        if len(parts) == 2:
            keys.append(f"domain:{parts[1]}")
        for token in _extract_name_tokens_from_email(email):
            keys.append(f"token:{token}")
    if contact.twitter_handle:
        keys.append(f"twitter:{contact.twitter_handle.strip().lower().lstrip('@')}")
    if contact.telegram_username:
        keys.append(f"telegram:{contact.telegram_username.strip().lower().lstrip('@')}")
    if contact.linkedin_profile_id:
        keys.append(f"linkedin:{contact.linkedin_profile_id.strip().lower()}")
    return keys
