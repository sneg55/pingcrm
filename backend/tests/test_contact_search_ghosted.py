"""Tests for the `ghosted` filter in build_contact_filter_query.

A contact is ghosted iff their 3 most recent interactions where
direction ∈ ('outbound', 'inbound') are all 'outbound'. Contacts with
fewer than 3 such interactions are not ghosted.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.services.contact_search import build_contact_filter_query


def _contact(user_id: uuid.UUID, name: str) -> Contact:
    return Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=name,
        relationship_score=5,
        priority_level="medium",
        source="manual",
    )


def _interaction(
    contact: Contact,
    user_id: uuid.UUID,
    *,
    direction: str,
    minutes_ago: int,
    platform: str = "telegram",
) -> Interaction:
    return Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user_id,
        platform=platform,
        direction=direction,
        occurred_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


async def _run(db: AsyncSession, user_id: uuid.UUID, **kwargs) -> list[Contact]:
    query = build_contact_filter_query(user_id, **kwargs)
    result = await db.execute(query)
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_three_outbound_zero_inbound_is_ghosted(
    db: AsyncSession, test_user: User
):
    c = _contact(test_user.id, "Ghosted Greta")
    db.add(c)
    db.add_all([
        _interaction(c, test_user.id, direction="outbound", minutes_ago=30),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=60),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=90),
    ])
    await db.commit()

    results = await _run(db, test_user.id, ghosted=True)

    assert [r.full_name for r in results] == ["Ghosted Greta"]


@pytest.mark.asyncio
async def test_three_outbound_with_older_inbound_is_ghosted(
    db: AsyncSession, test_user: User
):
    """An older inbound (before the trailing 3) does not save them."""
    c = _contact(test_user.id, "Faded Fiona")
    db.add(c)
    db.add_all([
        _interaction(c, test_user.id, direction="outbound", minutes_ago=10),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=20),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=30),
        _interaction(c, test_user.id, direction="inbound", minutes_ago=99999),
    ])
    await db.commit()

    results = await _run(db, test_user.id, ghosted=True)

    assert [r.full_name for r in results] == ["Faded Fiona"]


@pytest.mark.asyncio
async def test_recent_inbound_is_not_ghosted(db: AsyncSession, test_user: User):
    c = _contact(test_user.id, "Replied Rachel")
    db.add(c)
    db.add_all([
        _interaction(c, test_user.id, direction="inbound", minutes_ago=5),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=20),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=30),
    ])
    await db.commit()

    results = await _run(db, test_user.id, ghosted=True)

    assert results == []


@pytest.mark.asyncio
async def test_two_outbound_only_insufficient_data(
    db: AsyncSession, test_user: User
):
    c = _contact(test_user.id, "Two Outbound Tim")
    db.add(c)
    db.add_all([
        _interaction(c, test_user.id, direction="outbound", minutes_ago=10),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=20),
    ])
    await db.commit()

    results = await _run(db, test_user.id, ghosted=True)

    assert results == []


@pytest.mark.asyncio
async def test_event_rows_excluded_from_window(
    db: AsyncSession, test_user: User
):
    """Timeline (oldest→newest): outbound, outbound, outbound, event.
    The event is the most recent row but excluded; the trailing 3
    message-direction rows are all outbound, so the contact is ghosted."""
    c = _contact(test_user.id, "Event Edge Case")
    db.add(c)
    db.add_all([
        _interaction(c, test_user.id, direction="outbound", minutes_ago=40),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=30),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=20),
        _interaction(c, test_user.id, direction="event", minutes_ago=10),
    ])
    await db.commit()

    results = await _run(db, test_user.id, ghosted=True)

    assert [r.full_name for r in results] == ["Event Edge Case"]


@pytest.mark.asyncio
async def test_cross_platform_outbound_streak_counts(
    db: AsyncSession, test_user: User
):
    c = _contact(test_user.id, "Cross Platform Carl")
    db.add(c)
    db.add_all([
        _interaction(c, test_user.id, direction="outbound", minutes_ago=10, platform="twitter"),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=20, platform="telegram"),
        _interaction(c, test_user.id, direction="outbound", minutes_ago=30, platform="gmail"),
    ])
    await db.commit()

    results = await _run(db, test_user.id, ghosted=True)

    assert [r.full_name for r in results] == ["Cross Platform Carl"]


@pytest.mark.asyncio
async def test_ghosted_combined_with_priority_filter(
    db: AsyncSession, test_user: User
):
    high = _contact(test_user.id, "High Ghost")
    high.priority_level = "high"
    low = _contact(test_user.id, "Low Ghost")
    low.priority_level = "low"
    db.add_all([high, low])
    for c in (high, low):
        db.add_all([
            _interaction(c, test_user.id, direction="outbound", minutes_ago=10),
            _interaction(c, test_user.id, direction="outbound", minutes_ago=20),
            _interaction(c, test_user.id, direction="outbound", minutes_ago=30),
        ])
    await db.commit()

    results = await _run(db, test_user.id, ghosted=True, priority="high")

    assert [r.full_name for r in results] == ["High Ghost"]


@pytest.mark.asyncio
async def test_ghosted_excludes_archived_by_default(
    db: AsyncSession, test_user: User
):
    archived = _contact(test_user.id, "Archived Ghost")
    archived.priority_level = "archived"
    active = _contact(test_user.id, "Active Ghost")
    db.add_all([archived, active])
    for c in (archived, active):
        db.add_all([
            _interaction(c, test_user.id, direction="outbound", minutes_ago=10),
            _interaction(c, test_user.id, direction="outbound", minutes_ago=20),
            _interaction(c, test_user.id, direction="outbound", minutes_ago=30),
        ])
    await db.commit()

    default_results = await _run(db, test_user.id, ghosted=True)
    archived_results = await _run(
        db, test_user.id, ghosted=True, archived_only=True
    )

    assert [r.full_name for r in default_results] == ["Active Ghost"]
    assert [r.full_name for r in archived_results] == ["Archived Ghost"]


@pytest.mark.asyncio
async def test_contact_with_no_interactions_not_ghosted(
    db: AsyncSession, test_user: User
):
    c = _contact(test_user.id, "Silent Sam")
    db.add(c)
    await db.commit()

    results = await _run(db, test_user.id, ghosted=True)

    assert results == []


@pytest.mark.asyncio
async def test_ghosted_false_or_none_is_no_op(
    db: AsyncSession, test_user: User
):
    """ghosted=None or ghosted=False returns all contacts (filter is off)."""
    c1 = _contact(test_user.id, "Anyone One")
    c2 = _contact(test_user.id, "Anyone Two")
    db.add_all([c1, c2])
    await db.commit()

    none_results = await _run(db, test_user.id, ghosted=None)
    false_results = await _run(db, test_user.id, ghosted=False)

    assert {r.full_name for r in none_results} == {"Anyone One", "Anyone Two"}
    assert {r.full_name for r in false_results} == {"Anyone One", "Anyone Two"}
