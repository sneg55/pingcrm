"""Tests for relationship scoring service."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.services.scoring import calculate_score


@pytest.mark.asyncio
async def test_score_no_interactions(db: AsyncSession, test_user: User):
    contact = Contact(
        user_id=test_user.id,
        full_name="No Interactions",
        emails=["none@test.com"],
    )
    db.add(contact)
    await db.flush()

    score = await calculate_score(contact.id, db)
    assert score == 0  # No interactions, silence penalty


@pytest.mark.asyncio
async def test_score_recent_activity(db: AsyncSession, test_user: User):
    contact = Contact(
        user_id=test_user.id,
        full_name="Active Person",
        emails=["active@test.com"],
    )
    db.add(contact)
    await db.flush()

    # Add recent interaction
    interaction = Interaction(
        contact_id=contact.id,
        user_id=test_user.id,
        platform="email",
        direction="inbound",
        content_preview="Hey!",
        occurred_at=datetime.now(UTC) - timedelta(days=2),
    )
    db.add(interaction)
    await db.flush()

    score = await calculate_score(contact.id, db)
    assert score >= 5  # +5 for recent messages


@pytest.mark.asyncio
async def test_score_quick_reply_bonus(db: AsyncSession, test_user: User):
    contact = Contact(
        user_id=test_user.id,
        full_name="Quick Reply",
        emails=["quick@test.com"],
    )
    db.add(contact)
    await db.flush()

    now = datetime.now(UTC)
    # Inbound then outbound within 48h
    db.add(Interaction(
        contact_id=contact.id, user_id=test_user.id,
        platform="email", direction="inbound",
        content_preview="Question?",
        occurred_at=now - timedelta(hours=5),
    ))
    db.add(Interaction(
        contact_id=contact.id, user_id=test_user.id,
        platform="email", direction="outbound",
        content_preview="Answer!",
        occurred_at=now - timedelta(hours=3),
    ))
    await db.flush()

    score = await calculate_score(contact.id, db)
    assert score >= 8  # +5 recent + +3 quick reply


@pytest.mark.asyncio
async def test_score_capped_at_10(db: AsyncSession, test_user: User):
    contact = Contact(
        user_id=test_user.id,
        full_name="Super Active",
        emails=["super@test.com"],
    )
    db.add(contact)
    await db.flush()

    now = datetime.now(UTC)
    # Lots of interactions including intro and quick reply
    db.add(Interaction(
        contact_id=contact.id, user_id=test_user.id,
        platform="email", direction="inbound",
        content_preview="Let me introduce you to Bob",
        occurred_at=now - timedelta(hours=10),
    ))
    db.add(Interaction(
        contact_id=contact.id, user_id=test_user.id,
        platform="email", direction="outbound",
        content_preview="Thanks for the introduction!",
        occurred_at=now - timedelta(hours=8),
    ))
    await db.flush()

    score = await calculate_score(contact.id, db)
    assert 0 <= score <= 10


@pytest.mark.asyncio
async def test_score_silence_penalty(db: AsyncSession, test_user: User):
    contact = Contact(
        user_id=test_user.id,
        full_name="Old Contact",
        emails=["old@test.com"],
    )
    db.add(contact)
    await db.flush()

    # Only an old interaction
    db.add(Interaction(
        contact_id=contact.id, user_id=test_user.id,
        platform="email", direction="inbound",
        content_preview="Hello",
        occurred_at=datetime.now(UTC) - timedelta(days=120),
    ))
    await db.flush()

    score = await calculate_score(contact.id, db)
    assert score == 0  # No recent activity, 4 months silence penalty


@pytest.mark.asyncio
async def test_interaction_count_persisted(db: AsyncSession, test_user: User):
    """calculate_score should persist interaction_count on the contact."""
    contact = Contact(
        user_id=test_user.id,
        full_name="Count Test",
        emails=["count@test.com"],
    )
    db.add(contact)
    await db.flush()

    now = datetime.now(UTC)
    for i in range(3):
        db.add(Interaction(
            contact_id=contact.id, user_id=test_user.id,
            platform="email", direction="inbound",
            content_preview=f"Message {i}",
            occurred_at=now - timedelta(days=i + 1),
        ))
    await db.flush()

    await calculate_score(contact.id, db)
    await db.refresh(contact)
    assert contact.interaction_count == 3
