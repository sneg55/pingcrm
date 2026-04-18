"""Integration tests for contact_search service (build_contact_filter_query)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.services.contact_search import build_contact_filter_query, list_contacts_paginated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_contact(user_id: uuid.UUID, **kwargs) -> Contact:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name="Test Person",
        relationship_score=5,
        priority_level="medium",
        source="manual",
    )
    defaults.update(kwargs)
    return Contact(**defaults)


async def _run_query(db: AsyncSession, user_id: uuid.UUID, **kwargs) -> list[Contact]:
    """Execute a filter query and return the resulting contacts."""
    query = build_contact_filter_query(user_id, **kwargs)
    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_by_full_name_partial_match(db: AsyncSession, test_user: User):
    alice = _make_contact(test_user.id, full_name="Alice Wonderland")
    bob = _make_contact(test_user.id, full_name="Bob Builder")
    db.add_all([alice, bob])
    await db.commit()

    results = await _run_query(db, test_user.id, search="alice")

    names = [c.full_name for c in results]
    assert "Alice Wonderland" in names
    assert "Bob Builder" not in names


@pytest.mark.asyncio
async def test_search_by_family_name(db: AsyncSession, test_user: User):
    contact = _make_contact(test_user.id, full_name="Jane Smith", family_name="Smith")
    other = _make_contact(test_user.id, full_name="Jane Jones", family_name="Jones")
    db.add_all([contact, other])
    await db.commit()

    results = await _run_query(db, test_user.id, search="Smith")

    assert len(results) == 1
    assert results[0].family_name == "Smith"


@pytest.mark.asyncio
async def test_search_by_email(db: AsyncSession, test_user: User):
    contact = _make_contact(test_user.id, full_name="Email Person", emails=["unique@corp.io"])
    other = _make_contact(test_user.id, full_name="Other Person", emails=["other@example.com"])
    db.add_all([contact, other])
    await db.commit()

    results = await _run_query(db, test_user.id, search="unique@corp.io")

    assert len(results) == 1
    assert results[0].full_name == "Email Person"


@pytest.mark.asyncio
async def test_search_by_company(db: AsyncSession, test_user: User):
    contact = _make_contact(test_user.id, full_name="Corp Worker", company="Acme Corp")
    other = _make_contact(test_user.id, full_name="Solo Worker", company=None)
    db.add_all([contact, other])
    await db.commit()

    results = await _run_query(db, test_user.id, search="Acme")

    assert len(results) == 1
    assert results[0].company == "Acme Corp"


@pytest.mark.asyncio
async def test_filter_by_tag(db: AsyncSession, test_user: User):
    vip = _make_contact(test_user.id, full_name="VIP Person", tags=["vip", "investor"])
    regular = _make_contact(test_user.id, full_name="Regular Person", tags=["friend"])
    no_tags = _make_contact(test_user.id, full_name="No Tags Person", tags=[])
    db.add_all([vip, regular, no_tags])
    await db.commit()

    results = await _run_query(db, test_user.id, tag="vip")

    assert len(results) == 1
    assert results[0].full_name == "VIP Person"


@pytest.mark.asyncio
async def test_filter_by_source_platform(db: AsyncSession, test_user: User):
    gmail_contact = _make_contact(test_user.id, full_name="Gmail Person", source="gmail")
    tg_contact = _make_contact(test_user.id, full_name="Telegram Person", source="telegram")
    db.add_all([gmail_contact, tg_contact])
    await db.commit()

    results = await _run_query(db, test_user.id, source="gmail")

    assert len(results) == 1
    assert results[0].source == "gmail"


@pytest.mark.asyncio
async def test_filter_by_score_strong(db: AsyncSession, test_user: User):
    strong = _make_contact(test_user.id, full_name="Strong Tie", relationship_score=9)
    warm = _make_contact(test_user.id, full_name="Warm Tie", relationship_score=5)
    cold = _make_contact(test_user.id, full_name="Cold Tie", relationship_score=1)
    db.add_all([strong, warm, cold])
    await db.commit()

    results = await _run_query(db, test_user.id, score="strong")

    names = [c.full_name for c in results]
    assert "Strong Tie" in names
    assert "Warm Tie" not in names
    assert "Cold Tie" not in names


@pytest.mark.asyncio
async def test_filter_by_score_active(db: AsyncSession, test_user: User):
    strong = _make_contact(test_user.id, full_name="Strong Tie", relationship_score=10)
    active = _make_contact(test_user.id, full_name="Active Tie", relationship_score=6)
    dormant = _make_contact(test_user.id, full_name="Dormant Tie", relationship_score=2)
    db.add_all([strong, active, dormant])
    await db.commit()

    results = await _run_query(db, test_user.id, score="active")

    names = [c.full_name for c in results]
    assert "Active Tie" in names
    assert "Strong Tie" not in names
    assert "Dormant Tie" not in names


@pytest.mark.asyncio
async def test_filter_by_score_dormant(db: AsyncSession, test_user: User):
    active = _make_contact(test_user.id, full_name="Active Tie", relationship_score=5)
    dormant = _make_contact(test_user.id, full_name="Dormant Tie", relationship_score=2)
    db.add_all([active, dormant])
    await db.commit()

    results = await _run_query(db, test_user.id, score="dormant")

    assert len(results) == 1
    assert results[0].full_name == "Dormant Tie"


@pytest.mark.asyncio
async def test_filter_by_priority_high(db: AsyncSession, test_user: User):
    high = _make_contact(test_user.id, full_name="High Priority", priority_level="high")
    medium = _make_contact(test_user.id, full_name="Medium Priority", priority_level="medium")
    low = _make_contact(test_user.id, full_name="Low Priority", priority_level="low")
    db.add_all([high, medium, low])
    await db.commit()

    results = await _run_query(db, test_user.id, priority="high")

    assert len(results) == 1
    assert results[0].full_name == "High Priority"


@pytest.mark.asyncio
async def test_filter_by_date_from(db: AsyncSession, test_user: User):
    now = datetime.now(UTC)
    recent = _make_contact(test_user.id, full_name="Recent Contact", created_at=now)
    old = _make_contact(test_user.id, full_name="Old Contact", created_at=now - timedelta(days=30))
    db.add_all([recent, old])
    await db.commit()

    date_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    results = await _run_query(db, test_user.id, date_from=date_str)

    names = [c.full_name for c in results]
    assert "Recent Contact" in names
    assert "Old Contact" not in names


@pytest.mark.asyncio
async def test_filter_by_date_to(db: AsyncSession, test_user: User):
    now = datetime.now(UTC)
    recent = _make_contact(test_user.id, full_name="Recent Contact", created_at=now)
    old = _make_contact(test_user.id, full_name="Old Contact", created_at=now - timedelta(days=30))
    db.add_all([recent, old])
    await db.commit()

    date_str = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    results = await _run_query(db, test_user.id, date_to=date_str)

    names = [c.full_name for c in results]
    assert "Old Contact" in names
    assert "Recent Contact" not in names


@pytest.mark.asyncio
async def test_combined_filters_search_and_source(db: AsyncSession, test_user: User):
    match = _make_contact(test_user.id, full_name="Jane Gmail", source="gmail")
    wrong_source = _make_contact(test_user.id, full_name="Jane Telegram", source="telegram")
    wrong_name = _make_contact(test_user.id, full_name="Bob Gmail", source="gmail")
    db.add_all([match, wrong_source, wrong_name])
    await db.commit()

    results = await _run_query(db, test_user.id, search="Jane", source="gmail")

    assert len(results) == 1
    assert results[0].full_name == "Jane Gmail"


@pytest.mark.asyncio
async def test_combined_filters_tag_and_priority(db: AsyncSession, test_user: User):
    match = _make_contact(test_user.id, full_name="VIP High", tags=["vip"], priority_level="high")
    wrong_priority = _make_contact(test_user.id, full_name="VIP Low", tags=["vip"], priority_level="low")
    wrong_tag = _make_contact(test_user.id, full_name="No Tag High", tags=[], priority_level="high")
    db.add_all([match, wrong_priority, wrong_tag])
    await db.commit()

    results = await _run_query(db, test_user.id, tag="vip", priority="high")

    assert len(results) == 1
    assert results[0].full_name == "VIP High"


@pytest.mark.asyncio
async def test_empty_result_set(db: AsyncSession, test_user: User):
    contact = _make_contact(test_user.id, full_name="Alice Smith", source="gmail")
    db.add(contact)
    await db.commit()

    results = await _run_query(db, test_user.id, source="twitter")

    assert results == []


@pytest.mark.asyncio
async def test_user_isolation(db: AsyncSession, test_user: User):
    other_user = User(
        id=uuid.uuid4(),
        email=f"other_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="$2b$12$dummy",
        full_name="Other User",
    )
    db.add(other_user)
    await db.flush()

    mine = _make_contact(test_user.id, full_name="My Contact")
    theirs = _make_contact(other_user.id, full_name="Their Contact")
    db.add_all([mine, theirs])
    await db.commit()

    results = await _run_query(db, test_user.id)

    names = [c.full_name for c in results]
    assert "My Contact" in names
    assert "Their Contact" not in names


@pytest.mark.asyncio
async def test_archived_contacts_excluded_by_default(db: AsyncSession, test_user: User):
    active = _make_contact(test_user.id, full_name="Active Person", priority_level="medium")
    archived = _make_contact(test_user.id, full_name="Archived Person", priority_level="archived")
    db.add_all([active, archived])
    await db.commit()

    results = await _run_query(db, test_user.id)

    names = [c.full_name for c in results]
    assert "Active Person" in names
    assert "Archived Person" not in names


@pytest.mark.asyncio
async def test_archived_only_returns_archived(db: AsyncSession, test_user: User):
    active = _make_contact(test_user.id, full_name="Active Person", priority_level="medium")
    archived = _make_contact(test_user.id, full_name="Archived Person", priority_level="archived")
    db.add_all([active, archived])
    await db.commit()

    results = await _run_query(db, test_user.id, archived_only=True)

    assert len(results) == 1
    assert results[0].full_name == "Archived Person"


@pytest.mark.asyncio
async def test_search_via_interaction_content(db: AsyncSession, test_user: User):
    contact = _make_contact(test_user.id, full_name="Plain Name Person")
    db.add(contact)
    await db.flush()

    interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        platform="email",
        direction="inbound",
        content_preview="discussed quarterly budget forecast",
        occurred_at=datetime.now(UTC),
    )
    db.add(interaction)
    await db.commit()

    results = await _run_query(db, test_user.id, search="quarterly budget")

    assert len(results) == 1
    assert results[0].id == contact.id


@pytest.mark.asyncio
async def test_list_contacts_paginated_basic(db: AsyncSession, test_user: User):
    for i in range(5):
        db.add(_make_contact(test_user.id, full_name=f"Person {i}"))
    await db.commit()

    response = await list_contacts_paginated(db, test_user.id, page=1, page_size=3)

    assert response.meta.total == 5
    assert response.meta.page == 1
    assert response.meta.page_size == 3
    assert response.meta.total_pages == 2
    assert len(response.data) == 3


@pytest.mark.asyncio
async def test_list_contacts_paginated_second_page(db: AsyncSession, test_user: User):
    for i in range(5):
        db.add(_make_contact(test_user.id, full_name=f"Person {i}"))
    await db.commit()

    response = await list_contacts_paginated(db, test_user.id, page=2, page_size=3)

    assert len(response.data) == 2


@pytest.mark.asyncio
async def test_filter_invalid_date_format_ignored(db: AsyncSession, test_user: User):
    db.add(_make_contact(test_user.id, full_name="Any Person"))
    await db.commit()

    results = await _run_query(db, test_user.id, date_from="not-a-date", date_to="also-bad")

    assert len(results) == 1


@pytest.mark.asyncio
async def test_include_archived_returns_both(db: AsyncSession, test_user: User):
    active = _make_contact(test_user.id, full_name="Active Person", priority_level="medium")
    archived = _make_contact(test_user.id, full_name="Archived Person", priority_level="archived")
    db.add_all([active, archived])
    await db.commit()

    results = await _run_query(db, test_user.id, include_archived=True)

    names = {c.full_name for c in results}
    assert "Active Person" in names
    assert "Archived Person" in names


@pytest.mark.asyncio
async def test_archived_only_wins_over_include_archived(db: AsyncSession, test_user: User):
    active = _make_contact(test_user.id, full_name="Active Person", priority_level="medium")
    archived = _make_contact(test_user.id, full_name="Archived Person", priority_level="archived")
    db.add_all([active, archived])
    await db.commit()

    results = await _run_query(
        db, test_user.id, archived_only=True, include_archived=True
    )

    assert len(results) == 1
    assert results[0].full_name == "Archived Person"


@pytest.mark.asyncio
async def test_include_archived_with_search_matches_both(db: AsyncSession, test_user: User):
    active = _make_contact(
        test_user.id, full_name="Jane Active", priority_level="medium"
    )
    archived = _make_contact(
        test_user.id, full_name="Jane Archived", priority_level="archived"
    )
    other = _make_contact(
        test_user.id, full_name="Bob Active", priority_level="medium"
    )
    db.add_all([active, archived, other])
    await db.commit()

    results = await _run_query(db, test_user.id, search="Jane", include_archived=True)

    names = {c.full_name for c in results}
    assert names == {"Jane Active", "Jane Archived"}
