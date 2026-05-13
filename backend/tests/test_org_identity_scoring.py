"""Tests for app.services.org_identity_scoring."""
import pytest

from app.services.org_identity_scoring import (
    _normalize_linkedin_url,
    _normalize_website,
    _same_non_generic_domain,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.linkedin.com/company/anthropic/", "linkedin.com/company/anthropic"),
        ("http://linkedin.com/company/anthropic", "linkedin.com/company/anthropic"),
        ("linkedin.com/company/anthropic/", "linkedin.com/company/anthropic"),
        ("https://linkedin.com/company/anthropic-ai/about/", "linkedin.com/company/anthropic-ai"),
        ("", None),
        (None, None),
        ("not a url", None),
    ],
)
def test_normalize_linkedin_url(url, expected):
    assert _normalize_linkedin_url(url) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.anthropic.com/", "anthropic.com"),
        ("http://anthropic.com", "anthropic.com"),
        ("anthropic.com/", "anthropic.com"),
        ("https://anthropic.com/careers", "anthropic.com"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_website(url, expected):
    assert _normalize_website(url) == expected


@pytest.mark.parametrize(
    "domain_a,domain_b,expected",
    [
        ("anthropic.com", "anthropic.com", True),
        ("Anthropic.COM", "anthropic.com", True),
        ("gmail.com", "gmail.com", False),
        ("yahoo.com", "yahoo.com", False),
        ("anthropic.com", "openai.com", False),
        ("anthropic.com", None, False),
        (None, "anthropic.com", False),
        ("", "", False),
    ],
)
def test_same_non_generic_domain(domain_a, domain_b, expected):
    assert _same_non_generic_domain(domain_a, domain_b) is expected


from app.services.org_identity_scoring import _same_linkedin


@pytest.mark.parametrize(
    "url_a,url_b,expected",
    [
        (
            "https://www.linkedin.com/company/anthropic/",
            "linkedin.com/company/anthropic",
            True,
        ),
        (
            "https://linkedin.com/company/anthropic-ai/about/",
            "https://www.linkedin.com/company/anthropic-ai",
            True,
        ),
        (
            "https://linkedin.com/company/anthropic",
            "https://linkedin.com/company/openai",
            False,
        ),
        ("https://linkedin.com/company/anthropic", None, False),
        (None, None, False),
        ("garbage", "garbage", False),
    ],
)
def test_same_linkedin(url_a, url_b, expected):
    assert _same_linkedin(url_a, url_b) is expected


from dataclasses import dataclass
from typing import Optional

from app.services.org_identity_scoring import compute_org_adaptive_score


@dataclass
class FakeOrg:
    """Stand-in for Organization for pure-scoring tests."""
    name: str
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    website: Optional[str] = None
    twitter_handle: Optional[str] = None


def test_score_identical_orgs_high():
    a = FakeOrg(
        name="Anthropic", domain="anthropic.com",
        linkedin_url="https://linkedin.com/company/anthropic",
        website="https://anthropic.com", twitter_handle="AnthropicAI",
    )
    b = FakeOrg(
        name="Anthropic", domain="anthropic.com",
        linkedin_url="https://www.linkedin.com/company/anthropic/",
        website="https://www.anthropic.com/", twitter_handle="AnthropicAI",
    )
    assert compute_org_adaptive_score(a, b) >= 0.95


def test_score_name_variation_with_shared_domain():
    a = FakeOrg(name="Anthropic", domain="anthropic.com")
    b = FakeOrg(name="Anthropic, Inc.", domain="anthropic.com")
    score = compute_org_adaptive_score(a, b)
    assert 0.60 <= score <= 1.0


def test_score_different_names_shared_domain_capped():
    """Different orgs at same domain (e.g. parent + subsidiary) — cap to force review."""
    a = FakeOrg(name="Google", domain="google.com")
    b = FakeOrg(name="DeepMind", domain="google.com")
    score = compute_org_adaptive_score(a, b)
    assert score <= 0.50


def test_score_single_token_name_no_other_signal_capped():
    a = FakeOrg(name="Acme")
    b = FakeOrg(name="Acme")
    score = compute_org_adaptive_score(a, b)
    assert score <= 0.70


def test_score_all_signals_none_zero():
    a = FakeOrg(name="")
    b = FakeOrg(name="")
    assert compute_org_adaptive_score(a, b) == 0.0


def test_score_completely_different_low():
    a = FakeOrg(name="Anthropic", domain="anthropic.com")
    b = FakeOrg(name="Stripe", domain="stripe.com")
    assert compute_org_adaptive_score(a, b) < 0.30
