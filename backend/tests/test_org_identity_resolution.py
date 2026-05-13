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
