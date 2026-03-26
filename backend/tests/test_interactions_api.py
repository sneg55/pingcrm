"""Tests for interactions API endpoints."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="function")
async def second_user(db: AsyncSession) -> User:
    """A second user whose contacts should not be accessible by test_user."""
    user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password=hash_password("otherpass123"),
        full_name="Other User",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="function")
async def second_user_contact(db: AsyncSession, second_user: User) -> Contact:
    """A contact belonging to second_user."""
    contact = Contact(
        id=uuid.uuid4(),
        user_id=second_user.id,
        full_name="Jane Smith",
        emails=["jane@example.com"],
        phones=[],
        relationship_score=3,
        source="manual",
        last_interaction_at=None,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@pytest_asyncio.fixture(loop_scope="function")
async def multiple_interactions(
    db: AsyncSession, test_user: User, test_contact: Contact
) -> list[Interaction]:
    """Three interactions with different platforms and directions."""
    base_time = datetime.now(UTC) - timedelta(days=10)
    interactions = [
        Interaction(
            id=uuid.uuid4(),
            contact_id=test_contact.id,
            user_id=test_user.id,
            platform="telegram",
            direction="inbound",
            content_preview="Hey from Telegram",
            occurred_at=base_time,
        ),
        Interaction(
            id=uuid.uuid4(),
            contact_id=test_contact.id,
            user_id=test_user.id,
            platform="twitter",
            direction="outbound",
            content_preview="Tweet DM sent",
            occurred_at=base_time + timedelta(days=2),
        ),
        Interaction(
            id=uuid.uuid4(),
            contact_id=test_contact.id,
            user_id=test_user.id,
            platform="email",
            direction="inbound",
            content_preview="Email reply",
            occurred_at=base_time + timedelta(days=5),
        ),
    ]
    for i in interactions:
        db.add(i)
    await db.commit()
    for i in interactions:
        await db.refresh(i)
    return interactions


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_interactions(client: AsyncClient, auth_headers: dict, test_contact: Contact, test_interaction: Interaction):
    resp = await client.get(f"/api/v1/contacts/{test_contact.id}/interactions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 1
    assert data[0]["platform"] == "email"


@pytest.mark.asyncio
async def test_create_interaction(client: AsyncClient, auth_headers: dict, test_contact: Contact):
    resp = await client.post(f"/api/v1/contacts/{test_contact.id}/interactions", json={
        "platform": "manual",
        "direction": "outbound",
        "content_preview": "Had a great coffee chat",
        "occurred_at": datetime.now(UTC).isoformat(),
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["content_preview"] == "Had a great coffee chat"
    assert data["platform"] == "manual"


@pytest.mark.asyncio
async def test_create_interaction_nonexistent_contact(client: AsyncClient, auth_headers: dict):
    resp = await client.post(f"/api/v1/contacts/{uuid.uuid4()}/interactions", json={
        "platform": "manual",
        "direction": "outbound",
        "content_preview": "Test",
        "occurred_at": datetime.now(UTC).isoformat(),
    }, headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_interactions_nonexistent_contact(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/v1/contacts/{uuid.uuid4()}/interactions", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_interactions_requires_auth(client: AsyncClient, test_contact: Contact):
    """GET interactions without a token must return 401."""
    resp = await client.get(f"/api/v1/contacts/{test_contact.id}/interactions")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_interaction_requires_auth(client: AsyncClient, test_contact: Contact):
    """POST interaction without a token must return 401."""
    resp = await client.post(
        f"/api/v1/contacts/{test_contact.id}/interactions",
        json={
            "platform": "manual",
            "direction": "outbound",
            "content_preview": "No auth test",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Multiple platforms and directions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_interactions_with_multiple_platforms(
    client: AsyncClient,
    auth_headers: dict,
    test_contact: Contact,
    multiple_interactions: list[Interaction],
):
    """Listing interactions returns all platforms present for the contact."""
    resp = await client.get(
        f"/api/v1/contacts/{test_contact.id}/interactions", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    platforms = {item["platform"] for item in data}
    assert "telegram" in platforms
    assert "twitter" in platforms
    assert "email" in platforms


@pytest.mark.asyncio
async def test_list_interactions_contains_both_directions(
    client: AsyncClient,
    auth_headers: dict,
    test_contact: Contact,
    multiple_interactions: list[Interaction],
):
    """Listing interactions returns both inbound and outbound directions."""
    resp = await client.get(
        f"/api/v1/contacts/{test_contact.id}/interactions", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    directions = {item["direction"] for item in data}
    assert "inbound" in directions
    assert "outbound" in directions


# ---------------------------------------------------------------------------
# Ordering and pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_interactions_ordered_most_recent_first(
    client: AsyncClient,
    auth_headers: dict,
    test_contact: Contact,
    multiple_interactions: list[Interaction],
):
    """Interactions must be returned in descending occurred_at order."""
    resp = await client.get(
        f"/api/v1/contacts/{test_contact.id}/interactions", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    occurred_times = [item["occurred_at"] for item in data]
    assert occurred_times == sorted(occurred_times, reverse=True)


@pytest.mark.asyncio
async def test_list_interactions_pagination_via_client_slice(
    client: AsyncClient,
    auth_headers: dict,
    test_contact: Contact,
    multiple_interactions: list[Interaction],
):
    """All interactions are returned so client can paginate; count matches seeded data."""
    resp = await client.get(
        f"/api/v1/contacts/{test_contact.id}/interactions", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # We seeded 3 interactions via multiple_interactions fixture
    assert len(data) == 3


# ---------------------------------------------------------------------------
# Platform-specific creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_interaction_telegram_platform(
    client: AsyncClient, auth_headers: dict, test_contact: Contact
):
    """Creating a Telegram interaction stores the correct platform."""
    resp = await client.post(
        f"/api/v1/contacts/{test_contact.id}/interactions",
        json={
            "platform": "telegram",
            "direction": "inbound",
            "content_preview": "Telegram message",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["platform"] == "telegram"
    assert data["direction"] == "inbound"


@pytest.mark.asyncio
async def test_create_interaction_twitter_platform(
    client: AsyncClient, auth_headers: dict, test_contact: Contact
):
    """Creating a Twitter interaction stores the correct platform and raw_reference_id."""
    resp = await client.post(
        f"/api/v1/contacts/{test_contact.id}/interactions",
        json={
            "platform": "twitter",
            "direction": "outbound",
            "content_preview": "DM via Twitter",
            "raw_reference_id": "tweet-abc123",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["platform"] == "twitter"
    assert data["raw_reference_id"] == "tweet-abc123"


# ---------------------------------------------------------------------------
# Side effects
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_interaction_updates_contact_last_interaction_at(
    client: AsyncClient,
    auth_headers: dict,
    test_contact: Contact,
    db: AsyncSession,
):
    """Creating a newer interaction must update contact.last_interaction_at."""
    future_time = datetime.now(UTC) + timedelta(days=1)
    resp = await client.post(
        f"/api/v1/contacts/{test_contact.id}/interactions",
        json={
            "platform": "manual",
            "direction": "outbound",
            "content_preview": "Future note",
            "occurred_at": future_time.isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # Re-fetch the contact from the DB to verify the timestamp update
    result = await db.execute(select(Contact).where(Contact.id == test_contact.id))
    updated_contact = result.scalar_one()
    assert updated_contact.last_interaction_at is not None
    # The stored value should be at or after the fixture's original value
    assert updated_contact.last_interaction_at >= test_contact.last_interaction_at


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_interactions_isolation_between_users(
    client: AsyncClient,
    auth_headers: dict,
    second_user: User,
    second_user_contact: Contact,
):
    """test_user cannot list interactions for another user's contact (404)."""
    resp = await client.get(
        f"/api/v1/contacts/{second_user_contact.id}/interactions",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_interaction_isolation_between_users(
    client: AsyncClient,
    auth_headers: dict,
    second_user_contact: Contact,
):
    """test_user cannot create an interaction on another user's contact (404)."""
    resp = await client.post(
        f"/api/v1/contacts/{second_user_contact.id}/interactions",
        json={
            "platform": "manual",
            "direction": "outbound",
            "content_preview": "Should fail",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Response envelope structure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_interactions_returns_envelope_structure(
    client: AsyncClient,
    auth_headers: dict,
    test_contact: Contact,
):
    """Response must follow the standard { data, error, meta } envelope."""
    resp = await client.get(
        f"/api/v1/contacts/{test_contact.id}/interactions", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "error" in body
    assert "meta" in body
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_create_interaction_returns_envelope_structure(
    client: AsyncClient, auth_headers: dict, test_contact: Contact
):
    """Created interaction response must follow the standard envelope."""
    resp = await client.post(
        f"/api/v1/contacts/{test_contact.id}/interactions",
        json={
            "platform": "manual",
            "direction": "inbound",
            "content_preview": "Envelope check",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "data" in body
    assert "error" in body
    assert "meta" in body
    data = body["data"]
    assert "id" in data
    assert "contact_id" in data
    assert "user_id" in data
    assert "platform" in data
    assert "direction" in data
    assert "occurred_at" in data
    assert "created_at" in data
