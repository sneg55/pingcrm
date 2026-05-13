"""Tests for app.services.org_identity_resolution."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization
from app.models.user import User
from app.services.org_identity_resolution import merge_org_pair


@pytest.mark.asyncio
async def test_merge_org_pair_moves_contacts(db: AsyncSession, test_user: User):
    target = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    source = Organization(user_id=test_user.id, name="Anthropic, Inc.")
    db.add_all([target, source])
    await db.flush()

    c1 = Contact(user_id=test_user.id, full_name="Alice", emails=["a@anthropic.com"],
                 company="Anthropic, Inc.", organization_id=source.id)
    c2 = Contact(user_id=test_user.id, full_name="Bob", emails=["b@anthropic.com"],
                 company="Anthropic, Inc.", organization_id=source.id)
    db.add_all([c1, c2])
    await db.flush()

    moved = await merge_org_pair(target, source, db)
    await db.flush()

    assert moved == 2
    result = await db.execute(select(Organization).where(Organization.id == source.id))
    assert result.scalar_one_or_none() is None
    result = await db.execute(
        select(Contact).where(Contact.organization_id == target.id)
    )
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_merge_org_pair_fills_null_target_fields(db: AsyncSession, test_user: User):
    target = Organization(user_id=test_user.id, name="Anthropic")
    source = Organization(
        user_id=test_user.id, name="Anthropic, Inc.",
        domain="anthropic.com",
        linkedin_url="https://linkedin.com/company/anthropic",
        website="https://anthropic.com",
        industry="AI",
    )
    db.add_all([target, source])
    await db.flush()

    await merge_org_pair(target, source, db)
    await db.flush()

    assert target.domain == "anthropic.com"
    assert target.linkedin_url == "https://linkedin.com/company/anthropic"
    assert target.website == "https://anthropic.com"
    assert target.industry == "AI"


@pytest.mark.asyncio
async def test_merge_org_pair_does_not_overwrite_target_fields(
    db: AsyncSession, test_user: User
):
    target = Organization(
        user_id=test_user.id, name="Anthropic",
        domain="anthropic.com", industry="Research",
    )
    source = Organization(
        user_id=test_user.id, name="Anthropic, Inc.",
        domain="other.com", industry="AI",
    )
    db.add_all([target, source])
    await db.flush()

    await merge_org_pair(target, source, db)
    await db.flush()

    assert target.domain == "anthropic.com"
    assert target.industry == "Research"


from app.services.org_identity_resolution import find_deterministic_org_matches


@pytest.mark.asyncio
async def test_deterministic_same_domain(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic, Inc.", domain="anthropic.com")
    c = Organization(user_id=test_user.id, name="Stripe", domain="stripe.com")
    db.add_all([a, b, c])
    await db.flush()

    pairs = await find_deterministic_org_matches(test_user.id, db)
    pair_ids = {tuple(sorted([str(p[0].id), str(p[1].id)])) for p in pairs}
    assert tuple(sorted([str(a.id), str(b.id)])) in pair_ids
    assert all(c.id not in (p[0].id, p[1].id) for p in pairs)


@pytest.mark.asyncio
async def test_deterministic_same_linkedin(db: AsyncSession, test_user: User):
    a = Organization(
        user_id=test_user.id, name="Foo",
        linkedin_url="https://linkedin.com/company/anthropic",
    )
    b = Organization(
        user_id=test_user.id, name="Bar",
        linkedin_url="https://www.linkedin.com/company/anthropic/",
    )
    db.add_all([a, b])
    await db.flush()

    pairs = await find_deterministic_org_matches(test_user.id, db)
    assert len(pairs) == 1
    assert pairs[0][2] == "deterministic_linkedin"


@pytest.mark.asyncio
async def test_deterministic_generic_domain_ignored(db: AsyncSession, test_user: User):
    """Two orgs with gmail.com as their 'domain' should NOT auto-merge."""
    a = Organization(user_id=test_user.id, name="Acme", domain="gmail.com")
    b = Organization(user_id=test_user.id, name="Widget", domain="gmail.com")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_deterministic_org_matches(test_user.id, db)
    assert len(pairs) == 0


@pytest.mark.asyncio
async def test_deterministic_cross_user_isolation(
    db: AsyncSession, test_user: User, user_factory
):
    other = await user_factory()
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=other.id, name="Anthropic", domain="anthropic.com")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_deterministic_org_matches(test_user.id, db)
    assert len(pairs) == 0  # cross-user pairs never match


from app.services.org_identity_resolution import find_probabilistic_org_matches


@pytest.mark.asyncio
async def test_probabilistic_finds_name_variation(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic, Inc.", domain="anthropic.com")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_probabilistic_org_matches(test_user.id, db, exclude_ids=set())
    assert len(pairs) == 1
    assert pairs[0][2] >= 0.40


@pytest.mark.asyncio
async def test_probabilistic_skips_excluded(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic, Inc.", domain="anthropic.com")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_probabilistic_org_matches(
        test_user.id, db, exclude_ids={a.id}
    )
    assert pairs == []


@pytest.mark.asyncio
async def test_probabilistic_filters_below_threshold(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic")
    b = Organization(user_id=test_user.id, name="Stripe")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_probabilistic_org_matches(test_user.id, db, exclude_ids=set())
    assert pairs == []  # below 0.40 threshold


from app.models.org_identity_match import OrgIdentityMatch
from app.services.org_identity_resolution import scan_org_duplicates


@pytest.mark.asyncio
async def test_scan_auto_merges_deterministic(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic Inc", domain="anthropic.com")
    db.add_all([a, b])
    await db.flush()

    summary = await scan_org_duplicates(test_user.id, db)
    await db.flush()

    assert summary["auto_merged"] == 1
    result = await db.execute(
        select(Organization).where(Organization.user_id == test_user.id)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_scan_queues_probabilistic_for_review(db: AsyncSession, test_user: User):
    """Same first-3 chars but no domain/linkedin/website match — probabilistic territory."""
    a = Organization(user_id=test_user.id, name="Stripe")
    b = Organization(user_id=test_user.id, name="Stripe Payments")
    db.add_all([a, b])
    await db.flush()

    summary = await scan_org_duplicates(test_user.id, db)
    await db.flush()

    assert summary["pending_review"] >= 1
    result = await db.execute(
        select(OrgIdentityMatch).where(
            OrgIdentityMatch.user_id == test_user.id,
            OrgIdentityMatch.status == "pending_review",
        )
    )
    matches = result.scalars().all()
    assert len(matches) == 1
    assert matches[0].match_method == "probabilistic"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name_a,name_b",
    [
        ("BitTalent", "Bitscale"),
        ("BitBasel", "Bitbond"),
        ("Bitpanda", "Bitbond"),
        ("Microsoft", "MicroStrategy"),
        ("Apple", "Appian"),
    ],
)
async def test_probabilistic_drops_single_token_shared_prefix(
    db: AsyncSession, test_user: User, name_a: str, name_b: str
):
    """Two single-token names sharing only a short prefix, with no other signals,
    should NOT surface for review — they're noise (the only signal is the prefix)."""
    a = Organization(user_id=test_user.id, name=name_a)
    b = Organization(user_id=test_user.id, name=name_b)
    db.add_all([a, b])
    await db.flush()

    pairs = await find_probabilistic_org_matches(test_user.id, db, exclude_ids=set())
    assert pairs == [], f"expected {name_a} vs {name_b} to be filtered, got {pairs}"


@pytest.mark.asyncio
async def test_probabilistic_keeps_single_token_exact_match(
    db: AsyncSession, test_user: User
):
    """Two orgs with the same single-token name should still surface — the user
    presumably wants to confirm whether these are the same Google."""
    a = Organization(user_id=test_user.id, name="Google")
    b = Organization(user_id=test_user.id, name="Google")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_probabilistic_org_matches(test_user.id, db, exclude_ids=set())
    assert len(pairs) == 1


@pytest.mark.asyncio
async def test_scan_prunes_stale_pending_matches(
    db: AsyncSession, test_user: User
):
    """A pending_review row whose pair no longer scores above threshold (e.g.,
    inserted by an older, looser scorer) is dropped on next scan."""
    a = Organization(user_id=test_user.id, name="BitTalent")
    b = Organization(user_id=test_user.id, name="Bitscale")
    db.add_all([a, b])
    await db.flush()

    stale = OrgIdentityMatch(
        user_id=test_user.id,
        org_a_id=a.id,
        org_b_id=b.id,
        match_score=0.50,
        match_method="probabilistic",
        status="pending_review",
    )
    db.add(stale)
    await db.flush()

    await scan_org_duplicates(test_user.id, db)
    await db.flush()

    result = await db.execute(
        select(OrgIdentityMatch).where(OrgIdentityMatch.user_id == test_user.id)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_scan_keeps_resolved_matches(
    db: AsyncSession, test_user: User
):
    """Dismissed/merged matches are preserved as audit trail, even if the pair
    would no longer score above threshold."""
    a = Organization(user_id=test_user.id, name="BitTalent")
    b = Organization(user_id=test_user.id, name="Bitscale")
    db.add_all([a, b])
    await db.flush()

    dismissed = OrgIdentityMatch(
        user_id=test_user.id,
        org_a_id=a.id,
        org_b_id=b.id,
        match_score=0.50,
        match_method="probabilistic",
        status="dismissed",
    )
    db.add(dismissed)
    await db.flush()

    await scan_org_duplicates(test_user.id, db)
    await db.flush()

    result = await db.execute(
        select(OrgIdentityMatch).where(OrgIdentityMatch.user_id == test_user.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "dismissed"


@pytest.mark.asyncio
async def test_scan_idempotent(db: AsyncSession, test_user: User):
    """Running scan twice doesn't create duplicate match rows."""
    a = Organization(user_id=test_user.id, name="Stripe")
    b = Organization(user_id=test_user.id, name="Stripe Payments")
    db.add_all([a, b])
    await db.flush()

    await scan_org_duplicates(test_user.id, db)
    await db.flush()
    await scan_org_duplicates(test_user.id, db)
    await db.flush()

    result = await db.execute(
        select(OrgIdentityMatch).where(OrgIdentityMatch.user_id == test_user.id)
    )
    assert len(result.scalars().all()) == 1
