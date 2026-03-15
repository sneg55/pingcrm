"""Tests for the /api/v1/activity/recent endpoint."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User


@pytest.mark.asyncio
async def test_recent_activity_requires_auth(client: AsyncClient):
    """GET /api/v1/activity/recent returns 401 when no auth token is provided."""
    resp = await client.get("/api/v1/activity/recent")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_recent_activity_returns_interactions(
    client: AsyncClient,
    auth_headers: dict,
    test_interaction: Interaction,
    test_contact: Contact,
):
    """GET /api/v1/activity/recent returns a list of recent interactions."""
    resp = await client.get("/api/v1/activity/recent", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["error"] is None
    events = body["data"]
    assert isinstance(events, list)
    assert len(events) >= 1

    event = events[0]
    assert event["type"] == "message"
    assert event["contact_name"] == test_contact.full_name
    assert event["contact_id"] == str(test_contact.id)
    assert event["platform"] == test_interaction.platform
    assert event["direction"] == test_interaction.direction
    assert event["content_preview"] == test_interaction.content_preview
    assert "timestamp" in event


@pytest.mark.asyncio
async def test_recent_activity_empty_when_no_interactions(
    client: AsyncClient,
    auth_headers: dict,
):
    """GET /api/v1/activity/recent returns an empty list when there are no interactions."""
    resp = await client.get("/api/v1/activity/recent", headers=auth_headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["error"] is None
    assert body["data"] == []


@pytest.mark.asyncio
async def test_recent_activity_excludes_old_interactions(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
    test_contact: Contact,
):
    """GET /api/v1/activity/recent excludes interactions older than 7 days."""
    old_interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=test_user.id,
        platform="email",
        direction="outbound",
        content_preview="This is old",
        occurred_at=datetime.now(UTC) - timedelta(days=10),
    )
    db.add(old_interaction)
    await db.commit()

    resp = await client.get("/api/v1/activity/recent", headers=auth_headers)
    assert resp.status_code == 200

    events = resp.json()["data"]
    previews = [e["content_preview"] for e in events]
    assert "This is old" not in previews


@pytest.mark.asyncio
async def test_recent_activity_limit_param(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
    test_contact: Contact,
):
    """GET /api/v1/activity/recent respects the limit query parameter (deduped by contact)."""
    from app.models.contact import Contact

    now = datetime.now(UTC)
    # Create 5 different contacts with 1 interaction each
    for i in range(5):
        c = Contact(id=uuid.uuid4(), user_id=test_user.id, full_name=f"Limit Contact {i}")
        db.add(c)
        await db.flush()
        db.add(Interaction(
            id=uuid.uuid4(),
            contact_id=c.id,
            user_id=test_user.id,
            platform="email",
            direction="inbound",
            content_preview=f"Message {i}",
            occurred_at=now - timedelta(hours=i),
        ))
    await db.commit()

    resp = await client.get("/api/v1/activity/recent?limit=3", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 3


@pytest.mark.asyncio
async def test_recent_activity_only_returns_own_interactions(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
    test_contact: Contact,
):
    """GET /api/v1/activity/recent does not return interactions belonging to another user."""
    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="hashed",
        full_name="Other User",
    )
    db.add(other_user)
    await db.flush()

    other_contact = Contact(
        id=uuid.uuid4(),
        user_id=other_user.id,
        full_name="Other Contact",
        emails=["other@contact.com"],
    )
    db.add(other_contact)
    await db.flush()

    other_interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=other_contact.id,
        user_id=other_user.id,
        platform="telegram",
        direction="inbound",
        content_preview="Secret message from other user",
        occurred_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.add(other_interaction)

    own_interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=test_user.id,
        platform="email",
        direction="outbound",
        content_preview="My own message",
        occurred_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.add(own_interaction)
    await db.commit()

    resp = await client.get("/api/v1/activity/recent", headers=auth_headers)
    assert resp.status_code == 200

    previews = [e["content_preview"] for e in resp.json()["data"]]
    assert "Secret message from other user" not in previews
    assert "My own message" in previews


@pytest.mark.asyncio
async def test_recent_activity_ordered_newest_first(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
    test_contact: Contact,
):
    """GET /api/v1/activity/recent returns events ordered by timestamp descending (deduped per contact)."""
    from app.models.contact import Contact

    now = datetime.now(UTC)
    # Create 3 different contacts so dedup doesn't collapse them
    for i, preview in enumerate(["oldest", "middle", "newest"]):
        c = Contact(id=uuid.uuid4(), user_id=test_user.id, full_name=f"Order Contact {preview}")
        db.add(c)
        await db.flush()
        db.add(Interaction(
            id=uuid.uuid4(),
            contact_id=c.id,
            user_id=test_user.id,
            platform="email",
            direction="inbound",
            content_preview=preview,
            occurred_at=now - timedelta(hours=10 - i * 3),
        ))
    await db.commit()

    resp = await client.get("/api/v1/activity/recent", headers=auth_headers)
    assert resp.status_code == 200

    events = resp.json()["data"]
    previews = [e["content_preview"] for e in events]
    assert previews.index("newest") < previews.index("middle")
    assert previews.index("middle") < previews.index("oldest")
