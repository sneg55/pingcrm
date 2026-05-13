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
