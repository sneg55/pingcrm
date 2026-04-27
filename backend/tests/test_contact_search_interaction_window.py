"""Tests for the `interaction_from` / `interaction_to` filters.

These filter contacts by `last_interaction_at` (when you last actually spoke
to them), which is what the "Last Contact" UI control claims to do. They are
distinct from `date_from` / `date_to`, which filter `created_at` (when the
contact was added to the user's list).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.user import User
from app.services.contact_search import build_contact_filter_query


def _make_contact(
    user_id: uuid.UUID,
    *,
    name: str,
    last_interaction_at: datetime | None,
    created_at: datetime | None = None,
) -> Contact:
    kwargs = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=name,
        relationship_score=5,
        priority_level="medium",
        source="manual",
        last_interaction_at=last_interaction_at,
    )
    if created_at is not None:
        kwargs["created_at"] = created_at
    return Contact(**kwargs)


async def _run(db: AsyncSession, user_id: uuid.UUID, **kwargs) -> list[Contact]:
    query = build_contact_filter_query(user_id, **kwargs)
    result = await db.execute(query)
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_interaction_from_includes_recent_excludes_old(
    db: AsyncSession, test_user: User
):
    now = datetime.now(UTC)
    recent = _make_contact(
        test_user.id,
        name="Spoke Recently",
        last_interaction_at=now - timedelta(days=10),
    )
    old = _make_contact(
        test_user.id,
        name="Ghost From Long Ago",
        last_interaction_at=now - timedelta(days=400),
    )
    db.add_all([recent, old])
    await db.commit()

    cutoff = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    results = await _run(db, test_user.id, interaction_from=cutoff)

    names = {c.full_name for c in results}
    assert "Spoke Recently" in names
    assert "Ghost From Long Ago" not in names


@pytest.mark.asyncio
async def test_interaction_to_includes_old_excludes_recent(
    db: AsyncSession, test_user: User
):
    now = datetime.now(UTC)
    recent = _make_contact(
        test_user.id,
        name="Recent",
        last_interaction_at=now - timedelta(days=2),
    )
    old = _make_contact(
        test_user.id,
        name="Old",
        last_interaction_at=now - timedelta(days=200),
    )
    db.add_all([recent, old])
    await db.commit()

    cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    results = await _run(db, test_user.id, interaction_to=cutoff)

    names = {c.full_name for c in results}
    assert "Old" in names
    assert "Recent" not in names


@pytest.mark.asyncio
async def test_interaction_from_does_not_filter_on_created_at(
    db: AsyncSession, test_user: User
):
    """Recently *added* contact with a long-ago last interaction must NOT
    appear when we filter to interactions in the last 90 days. This is the
    bug the toolbar exposed: created_at vs last_interaction_at confusion.
    """
    now = datetime.now(UTC)
    # Recently added (created_at = today) but last spoke 492d ago.
    recently_added_long_ghost = _make_contact(
        test_user.id,
        name="Recently Added Long Ghost",
        last_interaction_at=now - timedelta(days=492),
        created_at=now - timedelta(days=1),
    )
    db.add(recently_added_long_ghost)
    await db.commit()

    cutoff = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    results = await _run(db, test_user.id, interaction_from=cutoff)

    assert results == []


@pytest.mark.asyncio
async def test_interaction_window_excludes_contacts_with_no_interactions(
    db: AsyncSession, test_user: User
):
    """A contact with last_interaction_at=NULL must not match an
    interaction window — we have no evidence we ever spoke to them."""
    now = datetime.now(UTC)
    silent = _make_contact(
        test_user.id, name="Silent", last_interaction_at=None
    )
    db.add(silent)
    await db.commit()

    cutoff = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    results = await _run(db, test_user.id, interaction_from=cutoff)

    assert results == []


@pytest.mark.asyncio
async def test_interaction_from_and_to_combine_as_range(
    db: AsyncSession, test_user: User
):
    now = datetime.now(UTC)
    in_range = _make_contact(
        test_user.id,
        name="In Range",
        last_interaction_at=now - timedelta(days=45),
    )
    too_recent = _make_contact(
        test_user.id,
        name="Too Recent",
        last_interaction_at=now - timedelta(days=2),
    )
    too_old = _make_contact(
        test_user.id,
        name="Too Old",
        last_interaction_at=now - timedelta(days=200),
    )
    db.add_all([in_range, too_recent, too_old])
    await db.commit()

    from_str = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    to_str = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    results = await _run(
        db, test_user.id, interaction_from=from_str, interaction_to=to_str
    )

    names = {c.full_name for c in results}
    assert names == {"In Range"}


@pytest.mark.asyncio
async def test_interaction_to_is_inclusive_of_full_day(
    db: AsyncSession, test_user: User
):
    """interaction_to=YYYY-MM-DD should include interactions that occurred
    anywhere within that day (mirrors how date_to behaves: < day+1)."""
    now = datetime.now(UTC)
    # Interaction at 23:00 on the cutoff day.
    cutoff_day = (now - timedelta(days=30)).replace(hour=23, minute=0, second=0, microsecond=0)
    contact = _make_contact(
        test_user.id, name="Late In Day", last_interaction_at=cutoff_day
    )
    db.add(contact)
    await db.commit()

    to_str = cutoff_day.strftime("%Y-%m-%d")
    results = await _run(db, test_user.id, interaction_to=to_str)

    assert [c.full_name for c in results] == ["Late In Day"]


@pytest.mark.asyncio
async def test_invalid_interaction_date_strings_are_ignored(
    db: AsyncSession, test_user: User
):
    """Mirror the date_from/date_to behavior: garbage strings don't error,
    they just don't apply the filter."""
    now = datetime.now(UTC)
    c = _make_contact(
        test_user.id, name="Anyone", last_interaction_at=now - timedelta(days=5)
    )
    db.add(c)
    await db.commit()

    results = await _run(
        db,
        test_user.id,
        interaction_from="not-a-date",
        interaction_to="also-bad",
    )

    assert [r.full_name for r in results] == ["Anyone"]
