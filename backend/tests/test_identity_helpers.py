"""Tests for identity resolution helper functions and probabilistic matching."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.user import User
from dataclasses import dataclass, field
from typing import Optional

from app.services.identity_resolution import (
    _compute_adaptive_score,
    _email_domain_match,
    _name_similarity,
    _username_similarity,
    find_probabilistic_matches,
    merge_contacts,
)


@dataclass
class FakeContact:
    """Lightweight stand-in for Contact to test scoring without DB."""
    full_name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    emails: Optional[list] = None
    phones: Optional[list] = None
    company: Optional[str] = None
    title: Optional[str] = None
    twitter_handle: Optional[str] = None
    telegram_username: Optional[str] = None
    tags: Optional[list] = None
    source: Optional[str] = None


def test_name_similarity_identical():
    assert _name_similarity("John Doe", "John Doe") == 1.0


def test_name_similarity_close():
    score = _name_similarity("Jon Doe", "John Doe")
    assert 0.7 < score < 1.0


def test_name_similarity_different():
    score = _name_similarity("Alice", "Bob")
    assert score < 0.5


def test_name_similarity_empty():
    assert _name_similarity("", "Bob") == 0.0
    assert _name_similarity("Alice", "") == 0.0


def test_email_domain_match_same_corp_domain():
    assert _email_domain_match(["alice@acme.com"], ["bob@acme.com"]) == 1.0


def test_email_domain_match_common_provider_ignored():
    assert _email_domain_match(["alice@gmail.com"], ["bob@gmail.com"]) == 0.0


def test_email_domain_match_different_domains():
    assert _email_domain_match(["alice@acme.com"], ["bob@other.com"]) == 0.0


def test_email_domain_match_empty():
    assert _email_domain_match(None, ["bob@acme.com"]) == 0.0
    assert _email_domain_match([], []) == 0.0


def test_username_similarity_identical():
    assert _username_similarity("@johndoe", "@johndoe") == 1.0


def test_username_similarity_close():
    score = _username_similarity("johndoe", "john_doe")
    assert score > 0.5


def test_username_similarity_empty():
    assert _username_similarity(None, "@bob") == 0.0
    assert _username_similarity("", "@bob") == 0.0


@pytest.mark.asyncio
async def test_merge_contacts_not_found(db: AsyncSession):
    with pytest.raises(ValueError, match="not found"):
        await merge_contacts(uuid.uuid4(), uuid.uuid4(), db)


@pytest.mark.asyncio
async def test_merge_contacts_swaps_richer_primary(
    db: AsyncSession, test_user: User
):
    """Contact with more data becomes the primary."""
    sparse = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Sparse",
        emails=["sparse@test.com"],
    )
    rich = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Rich Person",
        emails=["rich@test.com"],
        company="RichCo",
        title="CEO",
        twitter_handle="@rich",
        tags=["vip", "investor"],
    )
    db.add_all([sparse, rich])
    await db.commit()

    match = await merge_contacts(sparse.id, rich.id, db)
    assert match.status == "merged"
    # Rich should be the primary (contact_a_id) since it has more data
    assert match.contact_a_id == rich.id


def _make_contact(**kwargs) -> FakeContact:
    """Create a FakeContact for unit-testing scoring."""
    return FakeContact(**kwargs)


class TestAdaptiveScore:
    """Tests for _compute_adaptive_score with adaptive weight redistribution."""

    def test_full_overlap_same_as_before(self):
        """When all signals are available, behaves like original formula."""
        ca = _make_contact(
            full_name="John Smith", emails=["john@acme.com"],
            company="Acme Corp", twitter_handle="@john", tags=["vip"],
        )
        cb = _make_contact(
            full_name="John Smith", emails=["jsmith@acme.com"],
            company="Acme Corp", twitter_handle="@john", tags=["vip"],
        )
        score = _compute_adaptive_score(ca, cb)
        # All signals match: email_domain=1, name=1, company=1, username=1, mutual=1
        assert score > 0.85

    def test_name_only_cross_source_long_name(self):
        """Exact name match across sources (no other data) → pending_review range."""
        ca = _make_contact(full_name="Alex Wearn", source="linkedin")
        cb = _make_contact(full_name="Alex Wearn", source="telegram")
        score = _compute_adaptive_score(ca, cb)
        # Name is the only signal → gets weight 1.0, name_score=1.0, capped at 0.85
        assert 0.70 <= score <= 0.85, f"Expected 0.70-0.85, got {score}"

    def test_name_only_short_name_penalized(self):
        """Short first-name-only matches are penalized to avoid false positives."""
        ca = _make_contact(full_name="Alex", source="linkedin")
        cb = _make_contact(full_name="Alex", source="telegram")
        score = _compute_adaptive_score(ca, cb)
        # Short name penalty: 1.0 * 0.5 = 0.5
        assert score < 0.70, f"Short name should be penalized, got {score}"

    def test_name_plus_company_match(self):
        """Name + company match should score very high."""
        ca = _make_contact(full_name="John Smith", company="Acme Corp")
        cb = _make_contact(full_name="John Smith", company="Acme Corp")
        score = _compute_adaptive_score(ca, cb)
        # name=1.0 (weight 0.5) + company=1.0 (weight 0.5) = 1.0
        assert score > 0.85

    def test_different_names_no_match(self):
        """Different names should not match even with adaptive weights."""
        ca = _make_contact(full_name="Alice Johnson", source="linkedin")
        cb = _make_contact(full_name="Bob Williams", source="telegram")
        score = _compute_adaptive_score(ca, cb)
        assert score < 0.70

    def test_no_data_returns_zero(self):
        """Both contacts empty → 0."""
        ca = _make_contact()
        cb = _make_contact()
        score = _compute_adaptive_score(ca, cb)
        assert score == 0.0

    def test_similar_name_different_company(self):
        """Same name but different companies → below auto-merge threshold."""
        ca = _make_contact(full_name="John Smith", company="Acme Corp")
        cb = _make_contact(full_name="John Smith", company="Other Inc")
        score = _compute_adaptive_score(ca, cb)
        # name matches (weight ~0.5) but company doesn't → ~0.5
        assert 0.40 < score < 0.85


@pytest.mark.asyncio
async def test_probabilistic_matches_high_score_auto_merge(
    db: AsyncSession, test_user: User
):
    """Contacts with same company domain + similar names get auto-merged."""
    c1 = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="John Smith",
        emails=["john@acmecorp.com"],
        company="Acme Corp",
    )
    c2 = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="John Smith",
        emails=["jsmith@acmecorp.com"],
        company="Acme Corp",
    )
    db.add_all([c1, c2])
    await db.commit()

    matches = await find_probabilistic_matches(test_user.id, db)
    assert len(matches) >= 1


@pytest.mark.asyncio
async def test_probabilistic_matches_low_score_ignored(
    db: AsyncSession, test_user: User
):
    """Completely different contacts should not match."""
    c1 = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Alice",
        emails=["alice@gmail.com"],
    )
    c2 = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Bob",
        emails=["bob@yahoo.com"],
    )
    db.add_all([c1, c2])
    await db.commit()

    matches = await find_probabilistic_matches(test_user.id, db)
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_probabilistic_matches_cross_source_name_only(
    db: AsyncSession, test_user: User
):
    """Exact name match across sources with no other data → pending_review."""
    c1 = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Cooper Turley",
        source="linkedin",
        company="Audius",
    )
    c2 = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Cooper Turley",
        source="telegram",
        telegram_username="cooperturley",
    )
    db.add_all([c1, c2])
    await db.commit()

    matches = await find_probabilistic_matches(test_user.id, db)
    assert len(matches) >= 1
    # Name-only match is capped at 0.85 → pending_review (not auto-merged)
    assert matches[0].status == "pending_review"
