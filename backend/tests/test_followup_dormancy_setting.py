"""Tests for the user-configurable dormancy threshold.

Default is 365 (Pool A excludes contacts dormant > 1 year). Setting it
higher (e.g. 1825 = 5 years) makes more contacts engine-eligible. The
value lives in priority_settings.suggestion_prefs.dormancy_threshold_days.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.services.followup_engine import generate_suggestions


def _contact_with_interaction(
    user_id: uuid.UUID,
    *,
    last_interaction_days_ago: int,
    name: str = "C",
    interaction_count: int = 5,
) -> tuple[Contact, Interaction]:
    last_at = datetime.now(UTC) - timedelta(days=last_interaction_days_ago)
    c = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=name,
        emails=[f"{name.lower()}@example.com"],
        relationship_score=2,
        priority_level="medium",
        source="manual",
        last_interaction_at=last_at,
        interaction_count=interaction_count,
    )
    i = Interaction(
        id=uuid.uuid4(),
        contact_id=c.id,
        user_id=user_id,
        platform="telegram",
        direction="inbound",
        occurred_at=last_at,
    )
    return c, i


@pytest.mark.asyncio
async def test_default_dormancy_excludes_contact_over_365_days_from_pool_a(
    db: AsyncSession, test_user: User
):
    """No setting → default 365d. Contact dormant 400d cannot be in Pool A
    (the time-based pool). Pool B may still pick it — that's expected."""
    c, i = _contact_with_interaction(
        test_user.id, last_interaction_days_ago=400, name="OverDefault",
    )
    db.add_all([c, i])
    await db.commit()

    suggestions = await generate_suggestions(test_user.id, db)
    await db.commit()

    pool_a_for_contact = [s for s in suggestions if s.contact_id == c.id and s.pool == "A"]
    assert pool_a_for_contact == []


@pytest.mark.asyncio
async def test_extended_dormancy_setting_includes_older_contact(
    db: AsyncSession, test_user: User
):
    """User sets dormancy_threshold_days=730. Now a 400d-dormant contact
    is Pool A eligible (it falls within the user's broader window)."""
    test_user.priority_settings = {
        "suggestion_prefs": {"dormancy_threshold_days": 730},
    }
    c, i = _contact_with_interaction(
        test_user.id, last_interaction_days_ago=400, name="Within730",
    )
    db.add_all([c, i])
    await db.commit()

    from app.services.user_settings import get_priority_settings
    suggestions = await generate_suggestions(
        test_user.id, db,
        priority_settings=get_priority_settings(test_user),
    )
    await db.commit()

    pool_a_for_contact = [s for s in suggestions if s.contact_id == c.id and s.pool == "A"]
    assert len(pool_a_for_contact) == 1, (
        f"contact should be Pool A with dormancy=730d; got {[(s.pool, s.trigger_type) for s in suggestions]}"
    )


@pytest.mark.asyncio
async def test_setting_does_not_let_recent_contact_become_pool_b(
    db: AsyncSession, test_user: User
):
    """Boundary: a contact dormant only 30 days is still Pool A (not B),
    regardless of the dormancy setting. The setting widens the upper
    bound, not the lower."""
    test_user.priority_settings = {
        "suggestion_prefs": {"dormancy_threshold_days": 730},
    }
    c, i = _contact_with_interaction(
        test_user.id, last_interaction_days_ago=70, name="StillPoolA",
    )
    db.add_all([c, i])
    await db.commit()

    from app.services.user_settings import get_priority_settings
    suggestions = await generate_suggestions(
        test_user.id, db,
        priority_settings=get_priority_settings(test_user),
    )
    await db.commit()

    s = next((s for s in suggestions if s.contact_id == c.id), None)
    assert s is not None
    assert s.pool == "A"
