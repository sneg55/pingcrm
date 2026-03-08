"""Tests for reciprocity-first relationship scoring service."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.services.scoring import calculate_score


def _make_contact(db: AsyncSession, user: User, name: str) -> Contact:
    contact = Contact(
        user_id=user.id,
        full_name=name,
        emails=[f"{name.lower().replace(' ', '')}@test.com"],
    )
    db.add(contact)
    return contact


def _add_interaction(
    db: AsyncSession,
    contact: Contact,
    user: User,
    direction: str,
    days_ago: int,
    platform: str = "email",
):
    db.add(Interaction(
        contact_id=contact.id,
        user_id=user.id,
        platform=platform,
        direction=direction,
        content_preview=f"{direction} msg",
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
    ))


@pytest.mark.asyncio
async def test_score_no_interactions(db: AsyncSession, test_user: User):
    """No interactions → score 0."""
    contact = _make_contact(db, test_user, "Ghost")
    await db.flush()

    score = await calculate_score(contact.id, db)
    assert score == 0


@pytest.mark.asyncio
async def test_score_outbound_only_zero_reciprocity(db: AsyncSession, test_user: User):
    """Outbound-only messages with 0 inbound → score <= 2 (Dormant)."""
    contact = _make_contact(db, test_user, "One Sided")
    await db.flush()

    # 4 outbound messages over the past year, 0 inbound
    for days in [10, 60, 180, 350]:
        _add_interaction(db, contact, test_user, "outbound", days)
    await db.flush()

    score = await calculate_score(contact.id, db)
    # reciprocity=0, recency=round(2*0.5)=1, frequency=1, breadth=0 → max 2
    assert score <= 2


@pytest.mark.asyncio
async def test_score_balanced_recent_conversation(db: AsyncSession, test_user: User):
    """Bidirectional recent conversation on 2 platforms → score >= 7."""
    contact = _make_contact(db, test_user, "Best Friend")
    await db.flush()

    # 8 outbound + 6 inbound in last 14 days across email and telegram
    for i in range(8):
        _add_interaction(db, contact, test_user, "outbound", i + 1)
    for i in range(3):
        _add_interaction(db, contact, test_user, "inbound", i + 1, platform="email")
    for i in range(3):
        _add_interaction(db, contact, test_user, "inbound", i + 4, platform="telegram")
    await db.flush()

    score = await calculate_score(contact.id, db)
    # reciprocity=3, recency=3, frequency=2, breadth=1 → 9
    assert score >= 7


@pytest.mark.asyncio
async def test_score_old_balanced_conversation(db: AsyncSession, test_user: User):
    """Bidirectional but >90 days ago → score 4-6 (Active tier)."""
    contact = _make_contact(db, test_user, "Old Friend")
    await db.flush()

    # 3 outbound + 3 inbound, all around 60 days ago
    for i in range(3):
        _add_interaction(db, contact, test_user, "outbound", 55 + i)
    for i in range(3):
        _add_interaction(db, contact, test_user, "inbound", 58 + i)
    await db.flush()

    score = await calculate_score(contact.id, db)
    # reciprocity=4, recency=1, frequency=1, breadth=0 → 6
    assert 4 <= score <= 6


@pytest.mark.asyncio
async def test_score_multi_platform_breadth_bonus(db: AsyncSession, test_user: User):
    """2 platforms adds 1 point vs single platform."""
    contact_single = _make_contact(db, test_user, "Single Platform")
    contact_multi = _make_contact(db, test_user, "Multi Platform")
    await db.flush()

    # Same interaction pattern, different platform count
    for c, platforms in [
        (contact_single, ["email", "email"]),
        (contact_multi, ["email", "telegram"]),
    ]:
        _add_interaction(db, c, test_user, "outbound", 5, platform=platforms[0])
        _add_interaction(db, c, test_user, "inbound", 5, platform=platforms[1])
    await db.flush()

    score_single = await calculate_score(contact_single.id, db)
    score_multi = await calculate_score(contact_multi.id, db)
    assert score_multi == score_single + 1


@pytest.mark.asyncio
async def test_score_capped_at_10(db: AsyncSession, test_user: User):
    """Score never exceeds 10."""
    contact = _make_contact(db, test_user, "Super Active")
    await db.flush()

    # Lots of balanced interactions across 3 platforms
    for i in range(20):
        platforms = ["email", "telegram", "twitter"]
        _add_interaction(db, contact, test_user, "outbound", i + 1, platform=platforms[i % 3])
        _add_interaction(db, contact, test_user, "inbound", i + 1, platform=platforms[i % 3])
    await db.flush()

    score = await calculate_score(contact.id, db)
    assert 0 <= score <= 10


@pytest.mark.asyncio
async def test_interaction_count_persisted(db: AsyncSession, test_user: User):
    """calculate_score should persist interaction_count on the contact."""
    contact = _make_contact(db, test_user, "Count Test")
    await db.flush()

    for i in range(3):
        _add_interaction(db, contact, test_user, "inbound", i + 1)
    await db.flush()

    await calculate_score(contact.id, db)
    await db.refresh(contact)
    assert contact.interaction_count == 3
