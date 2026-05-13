"""Identity-resolution scoring primitives for organizations.

Pure helpers (no DB I/O). Mirrors the structure of app.services.identity_scoring
but operates on Organization fields. Reuses _name_similarity, _username_similarity,
_levenshtein, _normalize_name from the contact scoring module.
"""
from __future__ import annotations

import re

from app.models.organization import Organization
from app.services.identity_scoring import (
    _name_similarity,
    _normalize_name,
    _username_similarity,
)

GENERIC_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "mail.com", "aol.com", "protonmail.com",
}

_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/(company|school)/([^/?#]+)",
    re.IGNORECASE,
)


def _normalize_linkedin_url(url: str | None) -> str | None:
    """Return canonical linkedin.com/company/<slug> form, or None for unparseable."""
    if not url:
        return None
    m = _LINKEDIN_RE.search(url.strip())
    if not m:
        return None
    kind, slug = m.group(1).lower(), m.group(2).lower().rstrip("/")
    if not slug:
        return None
    return f"linkedin.com/{kind}/{slug}"


def _normalize_website(url: str | None) -> str | None:
    """Strip protocol, www, trailing slash, path. Return bare host or None."""
    if not url:
        return None
    text = url.strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    text = text.split("/", 1)[0]
    text = text.rstrip("/")
    if not text or "." not in text:
        return None
    return text


def _same_non_generic_domain(a: str | None, b: str | None) -> bool:
    """True iff both are the same domain AND not a generic provider."""
    if not a or not b:
        return False
    da, db = a.strip().lower(), b.strip().lower()
    if not da or not db:
        return False
    if da != db:
        return False
    return da not in GENERIC_DOMAINS


def _same_linkedin(a: str | None, b: str | None) -> bool:
    """True iff both URLs normalize to the same linkedin.com/company/<slug>."""
    na = _normalize_linkedin_url(a)
    nb = _normalize_linkedin_url(b)
    return na is not None and na == nb
