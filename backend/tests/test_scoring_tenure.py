"""Tests for tenure bonus and extended decay in the scoring service."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.services.scoring import calculate_score_breakdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contact(db: AsyncSession, user: User, name: str) -> Contact:
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name=name,
        emails=[f"{name.lower().replace(' ', '')}@test.com"],
        source="manual",
    )
    db.add(contact)
    return contact


def _add_interaction(
    db: AsyncSession,
    contact: Contact,
    user: User,
    direction: str,
    occurred_at: datetime,
    platform: str = "email",
) -> None:
    db.add(Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user.id,
        platform=platform,
        direction=direction,
        content_preview=f"{direction} msg",
        occurred_at=occurred_at,
    ))


# ---------------------------------------------------------------------------
# Tenure bonus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenure_bonus_zero_for_new_contacts(db: AsyncSession, test_user: User):
    """Contacts with fewer than 20 interactions or less than 1 year history get tenure=0."""
    contact = _make_contact(db, test_user, "New Person")
    await db.flush()

    # 10 interactions over only 6 months (< 1 year, < 20 interactions)
    now = datetime.now(UTC)
    for i in range(10):
        _add_interaction(
            db, contact, test_user, "inbound",
            occurred_at=now - timedelta(days=180 - i * 10),
        )
    await db.commit()

    breakdown = await calculate_score_breakdown(contact.id, db)
    assert breakdown.tenure == 0, (
        f"Expected tenure=0 for <20 interactions and <1 year, got {breakdown.tenure}"
    )


@pytest.mark.asyncio
async def test_tenure_bonus_one_for_established(db: AsyncSession, test_user: User):
    """20+ interactions spanning 1+ year → tenure=1."""
    contact = _make_contact(db, test_user, "Established Person")
    await db.flush()

    now = datetime.now(UTC)
    for i in range(22):
        _add_interaction(
            db, contact, test_user,
            direction="outbound" if i % 2 else "inbound",
            occurred_at=now - timedelta(days=400 + i * 5),
        )
    await db.commit()

    breakdown = await calculate_score_breakdown(contact.id, db)
    assert breakdown.tenure == 1, (
        f"Expected tenure=1 for 22 interactions spanning 1+ year, got {breakdown.tenure}"
    )
    assert breakdown.interaction_count >= 20


@pytest.mark.asyncio
async def test_tenure_bonus_two_for_deep(db: AsyncSession, test_user: User):
    """50+ interactions spanning 2+ years → tenure=2."""
    contact = _make_contact(db, test_user, "Deep Contact")
    await db.flush()

    now = datetime.now(UTC)
    for i in range(55):
        _add_interaction(
            db, contact, test_user,
            direction="outbound" if i % 2 else "inbound",
            occurred_at=now - timedelta(days=800 + i * 7),
        )
    await db.commit()

    breakdown = await calculate_score_breakdown(contact.id, db)
    assert breakdown.tenure == 2, (
        f"Expected tenure=2 for 55 interactions spanning 2+ years, got {breakdown.tenure}"
    )
    assert breakdown.interaction_count >= 50


# ---------------------------------------------------------------------------
# Extended decay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extended_decay_contributes_to_frequency(db: AsyncSession, test_user: User):
    """Old interactions (1-2y and 2-5y windows) contribute to the frequency score
    via 0.05x and 0.02x weights."""
    contact_with_history = _make_contact(db, test_user, "Long History")
    contact_no_history = _make_contact(db, test_user, "Short History")
    await db.flush()

    now = datetime.now(UTC)

    # Both contacts get 2 interactions in the last year (same baseline)
    for c in [contact_with_history, contact_no_history]:
        _add_interaction(db, c, test_user, "inbound", now - timedelta(days=200))
        _add_interaction(db, c, test_user, "outbound", now - timedelta(days=300))

    # contact_with_history also gets many old interactions (1-2y and 2-5y windows)
    for i in range(30):
        # 1-2 year window
        _add_interaction(
            db, contact_with_history, test_user, "inbound",
            now - timedelta(days=400 + i * 5),
        )
    for i in range(20):
        # 2-5 year window
        _add_interaction(
            db, contact_with_history, test_user, "outbound",
            now - timedelta(days=800 + i * 10),
        )
    await db.commit()

    bd_history = await calculate_score_breakdown(contact_with_history.id, db)
    bd_no_history = await calculate_score_breakdown(contact_no_history.id, db)

    # The contact with old interactions should have equal or higher frequency
    assert bd_history.frequency >= bd_no_history.frequency, (
        "Extended decay should contribute non-negatively to frequency"
    )
    # The contact with 50+ old interactions should show higher total interaction count
    assert bd_history.interaction_count > bd_no_history.interaction_count


@pytest.mark.asyncio
async def test_extended_decay_contributes_to_reciprocity(db: AsyncSession, test_user: User):
    """Old inbound/outbound at reduced weight affect effective reciprocity.

    A contact with balanced old interactions should have higher reciprocity than one
    with only recent one-sided outbound.
    """
    contact_balanced_old = _make_contact(db, test_user, "Balanced Old")
    contact_one_sided = _make_contact(db, test_user, "One Sided")
    await db.flush()

    now = datetime.now(UTC)

    # contact_balanced_old: many old balanced interactions (no recent ones to avoid
    # recency contribution masking the comparison)
    for i in range(15):
        _add_interaction(
            db, contact_balanced_old, test_user, "inbound",
            now - timedelta(days=400 + i * 10),
        )
        _add_interaction(
            db, contact_balanced_old, test_user, "outbound",
            now - timedelta(days=400 + i * 10 + 2),
        )

    # contact_one_sided: only outbound in last 365d, no inbound at all
    for i in range(5):
        _add_interaction(
            db, contact_one_sided, test_user, "outbound",
            now - timedelta(days=50 + i * 30),
        )
    await db.commit()

    bd_balanced = await calculate_score_breakdown(contact_balanced_old.id, db)
    bd_one_sided = await calculate_score_breakdown(contact_one_sided.id, db)

    # One-sided contact must have reciprocity=0 (no inbound at all)
    assert bd_one_sided.reciprocity == 0, (
        f"Expected reciprocity=0 for outbound-only contact, got {bd_one_sided.reciprocity}"
    )
    # Balanced-old contact should benefit from extended decay — reciprocity > 0
    assert bd_balanced.reciprocity > 0, (
        f"Expected reciprocity>0 for balanced old interactions, got {bd_balanced.reciprocity}"
    )
