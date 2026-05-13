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
