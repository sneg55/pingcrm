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


def compute_org_adaptive_score(a: Organization, b: Organization) -> float:
    """Adaptive-weight match score for two organizations.

    Base weights: name=0.40, domain=0.20, linkedin=0.20, website=0.10, twitter=0.10.
    Weights for unavailable signals are redistributed across active signals.
    """
    BASE_WEIGHTS = {
        "name":     0.40,
        "domain":   0.20,
        "linkedin": 0.20,
        "website":  0.10,
        "twitter":  0.10,
    }

    name_a = (a.name or "").strip()
    name_b = (b.name or "").strip()

    name_score = _name_similarity(name_a, name_b)
    domain_score = 1.0 if _same_non_generic_domain(a.domain, b.domain) else 0.0
    linkedin_score = 1.0 if _same_linkedin(a.linkedin_url, b.linkedin_url) else 0.0

    nwa = _normalize_website(a.website)
    nwb = _normalize_website(b.website)
    website_score = 1.0 if nwa and nwa == nwb else 0.0

    twitter_score = _username_similarity(a.twitter_handle, b.twitter_handle)

    scores = {
        "name": name_score,
        "domain": domain_score,
        "linkedin": linkedin_score,
        "website": website_score,
        "twitter": twitter_score,
    }

    has_name = bool(name_a) and bool(name_b)
    has_domain = bool(a.domain) and bool(b.domain) and a.domain.lower() not in GENERIC_DOMAINS
    has_linkedin = bool(a.linkedin_url) and bool(b.linkedin_url)
    has_website = bool(nwa) and bool(nwb)
    has_twitter = bool(a.twitter_handle) and bool(b.twitter_handle)

    available = {
        "name": has_name,
        "domain": has_domain,
        "linkedin": has_linkedin,
        "website": has_website,
        "twitter": has_twitter,
    }

    active_weight_sum = sum(BASE_WEIGHTS[k] for k, v in available.items() if v)
    if active_weight_sum == 0:
        return 0.0

    total = 0.0
    for key in BASE_WEIGHTS:
        if available[key]:
            weight = BASE_WEIGHTS[key] / active_weight_sum
            total += weight * scores[key]

    # Guard: name_score very low even when domain+linkedin both fire — likely
    # shared infrastructure (parent/subsidiary), not the same org.
    if has_name and name_score < 0.5 and (domain_score == 1.0 or linkedin_score == 1.0):
        total = min(total, 0.50)

    # Guard: single-token name on either side AND no corroborating signal.
    name_a_tokens = len(_normalize_name(name_a).split())
    name_b_tokens = len(_normalize_name(name_b).split())
    is_single_token = name_a_tokens <= 1 or name_b_tokens <= 1
    if has_name and is_single_token:
        if not has_domain and not has_linkedin and not has_website and not has_twitter:
            total = min(total, 0.50)

    # Cap: when name is the *only* signal, cap at 0.70 to force review.
    active_count = sum(1 for v in available.values() if v)
    if active_count == 1 and has_name:
        total = min(total, 0.70)

    return total


def _shares_anchor(a: Organization, b: Organization) -> bool:
    """Cheap pre-filter: True if the pair shares *any* fragment worth scoring.

    Cuts O(n^2) pair comparisons down by >95% before the more expensive
    compute_org_adaptive_score runs.
    """
    na = _normalize_name(a.name or "")
    nb = _normalize_name(b.name or "")
    if na and nb and na[:3] == nb[:3]:
        return True

    if _same_non_generic_domain(a.domain, b.domain):
        return True

    if _same_linkedin(a.linkedin_url, b.linkedin_url):
        return True

    nwa = _normalize_website(a.website)
    nwb = _normalize_website(b.website)
    if nwa and nwa == nwb:
        return True

    return False
