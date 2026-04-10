"""Tests for the Meta (Facebook/Instagram) push endpoint."""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User


@pytest.mark.asyncio
async def test_push_creates_contact_and_interaction(client, test_user, auth_headers):
    """Push a new profile + message → creates contact and interaction."""
    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [
                {
                    "platform_id": "100012345",
                    "name": "Jane Doe",
                    "username": "janedoe",
                    "avatar_url": "https://example.com/avatar.jpg",
                }
            ],
            "messages": [
                {
                    "message_id": "mid.001",
                    "conversation_id": "conv_123",
                    "platform_id": "100012345",
                    "sender_name": "Jane Doe",
                    "direction": "inbound",
                    "content_preview": "Hey, how are you?",
                    "timestamp": "2026-04-09T14:30:00Z",
                    "reactions": [{"reactor_id": "100099", "type": "love"}],
                    "read_by": ["100012345"],
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contacts_created"] == 1
    assert data["interactions_created"] == 1


@pytest.mark.asyncio
async def test_push_deduplicates_messages(client, test_user, auth_headers):
    """Pushing the same message_id twice → second is skipped."""
    payload = {
        "platform": "facebook",
        "profiles": [],
        "messages": [
            {
                "message_id": "mid.dedup",
                "conversation_id": "conv_1",
                "platform_id": "100012345",
                "sender_name": "Jane Doe",
                "direction": "inbound",
                "content_preview": "Hello",
                "timestamp": "2026-04-09T10:00:00Z",
                "reactions": [],
                "read_by": [],
            }
        ],
    }
    resp1 = await client.post("/api/v1/meta/push", json=payload, headers=auth_headers)
    assert resp1.json()["data"]["interactions_created"] == 1

    resp2 = await client.post("/api/v1/meta/push", json=payload, headers=auth_headers)
    assert resp2.json()["data"]["interactions_created"] == 0
    assert resp2.json()["data"]["interactions_skipped"] == 1


@pytest.mark.asyncio
async def test_push_updates_existing_contact(client, db, test_user, auth_headers):
    """Push a profile whose facebook_id matches an existing contact → updates it."""
    contact = Contact(
        user_id=test_user.id,
        full_name="Jane D",
        facebook_id="100012345",
    )
    db.add(contact)
    await db.commit()

    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [
                {
                    "platform_id": "100012345",
                    "name": "Jane Doe",
                    "username": "janedoe",
                    "avatar_url": None,
                }
            ],
            "messages": [],
        },
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["contacts_created"] == 0
    assert data["contacts_updated"] == 1


@pytest.mark.asyncio
async def test_push_instagram_platform(client, test_user, auth_headers):
    """Push with platform=instagram uses instagram_id for contact matching."""
    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "instagram",
            "profiles": [
                {
                    "platform_id": "ig_555",
                    "name": "Bob Smith",
                    "username": "bobsmith",
                    "avatar_url": None,
                }
            ],
            "messages": [
                {
                    "message_id": "mid.ig001",
                    "conversation_id": "ig_conv_1",
                    "platform_id": "ig_555",
                    "sender_name": "Bob Smith",
                    "direction": "inbound",
                    "content_preview": "Nice pic!",
                    "timestamp": "2026-04-09T15:00:00Z",
                    "reactions": [],
                    "read_by": [],
                }
            ],
        },
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["contacts_created"] == 1
    assert data["interactions_created"] == 1


@pytest.mark.asyncio
async def test_push_stores_reactions_and_read_receipts(client, db, test_user, auth_headers):
    """Reactions and read_by are stored in interaction extra_data."""
    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [],
            "messages": [
                {
                    "message_id": "mid.react",
                    "conversation_id": "conv_r",
                    "platform_id": "100012345",
                    "sender_name": "Jane Doe",
                    "direction": "inbound",
                    "content_preview": "Check this out",
                    "timestamp": "2026-04-09T16:00:00Z",
                    "reactions": [{"reactor_id": "100099", "type": "love"}],
                    "read_by": ["100012345", "100099"],
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.json()["data"]["interactions_created"] == 1

    result = await db.execute(
        select(Interaction).where(Interaction.raw_reference_id == "facebook:mid.react")
    )
    interaction = result.scalar_one()
    assert interaction.extra_data is not None
    assert interaction.extra_data["reactions"][0]["type"] == "love"
    assert "100099" in interaction.extra_data["read_by"]


@pytest.mark.asyncio
async def test_push_sets_meta_connected_flag(client, db, test_user, auth_headers):
    """First push sets meta_connected=True on the user."""
    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [
                {
                    "platform_id": "100012345",
                    "name": "Jane Doe",
                    "username": None,
                    "avatar_url": None,
                }
            ],
            "messages": [],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    await db.refresh(test_user)
    assert test_user.meta_connected is True


@pytest.mark.asyncio
async def test_push_cross_platform_name_match(client, db, test_user, auth_headers):
    """A Facebook message with name matching an existing LinkedIn contact → links to it."""
    contact = Contact(
        user_id=test_user.id,
        full_name="Jane Doe",
        linkedin_profile_id="janedoe",
    )
    db.add(contact)
    await db.commit()

    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [],
            "messages": [
                {
                    "message_id": "mid.xplat",
                    "conversation_id": "conv_x",
                    "platform_id": "100012345",
                    "sender_name": "Jane Doe",
                    "direction": "inbound",
                    "content_preview": "Hey!",
                    "timestamp": "2026-04-09T17:00:00Z",
                    "reactions": [],
                    "read_by": [],
                }
            ],
        },
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["contacts_created"] == 0  # Matched existing contact
    assert data["interactions_created"] == 1
