"""Tests for the LinkedIn Chrome Extension push endpoint."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction


PUSH_URL = "/api/v1/linkedin/push"


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_requires_auth(client: AsyncClient):
    """Unauthenticated requests must be rejected with 401."""
    resp = await client.post(PUSH_URL, json={"profiles": [], "messages": []})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Profile push — new contact creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_creates_new_contact(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
):
    """A profile push for an unknown profile_id should create a new contact."""
    payload = {
        "profiles": [
            {
                "profile_id": "alice-smith-123",
                "profile_url": "https://www.linkedin.com/in/alice-smith-123",
                "full_name": "Alice Smith",
                "headline": "Product Manager at Acme",
                "company": "Acme",
                "location": "San Francisco",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["contacts_created"] == 1
    assert data["contacts_updated"] == 0
    assert data["interactions_created"] == 0
    assert data["interactions_skipped"] == 0

    # Verify the contact is actually in the DB
    result = await db.execute(
        select(Contact).where(Contact.linkedin_profile_id == "alice-smith-123")
    )
    contact = result.scalar_one_or_none()
    assert contact is not None
    assert contact.full_name == "Alice Smith"
    assert contact.company == "Acme"


# ---------------------------------------------------------------------------
# Profile push — existing contact update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_updates_existing_contact(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """A profile push matching an existing contact should update its fields."""
    # Pre-create a contact with a known linkedin_profile_id
    existing = Contact(
        user_id=test_user.id,
        full_name="Bob Jones",
        linkedin_profile_id="bob-jones-456",
        source="manual",
    )
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    payload = {
        "profiles": [
            {
                "profile_id": "bob-jones-456",
                "profile_url": "https://www.linkedin.com/in/bob-jones-456",
                "full_name": "Bob Jones",
                "headline": "Engineer at StartupCo",
                "company": "StartupCo",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["contacts_created"] == 0
    assert data["contacts_updated"] == 1

    # Verify updated fields in DB
    await db.refresh(existing)
    assert existing.linkedin_headline == "Engineer at StartupCo"
    assert existing.company == "StartupCo"


# ---------------------------------------------------------------------------
# Message push — interaction creation and dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_creates_interactions(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
):
    """Messages in the payload should create Interaction records."""
    payload = {
        "profiles": [],
        "messages": [
            {
                "profile_id": "carol-white-789",
                "profile_name": "Carol White",
                "direction": "inbound",
                "content_preview": "Hey, great meeting you!",
                "timestamp": "2026-01-15T10:00:00+00:00",
                "conversation_id": "conv-001",
                "content_hash": "hash-abc123",
            }
        ],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    # Contact auto-created from message
    assert data["contacts_created"] == 1
    assert data["interactions_created"] == 1
    assert data["interactions_skipped"] == 0

    # Verify interaction in DB
    result = await db.execute(
        select(Interaction).where(
            Interaction.raw_reference_id == "linkedin:conv-001:hash-abc123"
        )
    )
    interaction = result.scalar_one_or_none()
    assert interaction is not None
    assert interaction.platform == "linkedin"
    assert interaction.direction == "inbound"
    assert interaction.content_preview == "Hey, great meeting you!"


@pytest.mark.asyncio
async def test_push_deduplicates_interactions(
    client: AsyncClient,
    auth_headers: dict,
):
    """Sending the same message twice should skip the duplicate on the second push."""
    message = {
        "profile_id": "dave-green-999",
        "profile_name": "Dave Green",
        "direction": "outbound",
        "content_preview": "Looking forward to connecting.",
        "timestamp": "2026-02-01T09:00:00+00:00",
        "conversation_id": "conv-002",
        "content_hash": "hash-dup999",
    }
    payload = {"profiles": [], "messages": [message]}

    # First push — should create
    resp1 = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp1.status_code == 200
    assert resp1.json()["data"]["interactions_created"] == 1
    assert resp1.json()["data"]["interactions_skipped"] == 0

    # Second push — should skip (duplicate)
    resp2 = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["interactions_created"] == 0
    assert resp2.json()["data"]["interactions_skipped"] == 1


# ---------------------------------------------------------------------------
# Empty payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_empty_payload(client: AsyncClient, auth_headers: dict):
    """An empty push should succeed and return all-zero counts."""
    resp = await client.post(PUSH_URL, json={}, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["contacts_created"] == 0
    assert data["contacts_updated"] == 0
    assert data["interactions_created"] == 0
    assert data["interactions_skipped"] == 0


# ---------------------------------------------------------------------------
# Match contact by linkedin_url when profile_id is absent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_matches_contact_by_linkedin_url(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """If a contact exists with a matching linkedin_url, update it instead of creating."""
    existing = Contact(
        user_id=test_user.id,
        full_name="Eve Adams",
        linkedin_url="https://www.linkedin.com/in/eve-adams",
        source="manual",
    )
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    payload = {
        "profiles": [
            {
                "profile_id": "eve-adams",
                "profile_url": "https://www.linkedin.com/in/eve-adams",
                "full_name": "Eve Adams",
                "headline": "Designer",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["contacts_created"] == 0
    assert data["contacts_updated"] == 1

    await db.refresh(existing)
    assert existing.linkedin_profile_id == "eve-adams"
    assert existing.linkedin_headline == "Designer"


# ---------------------------------------------------------------------------
# Avatar: base64 data URI from browser
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_saves_avatar_from_base64_data(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """Profile push with avatar_data (base64) saves the image locally."""
    import base64
    from pathlib import Path

    # Tiny 1x1 red JPEG
    tiny_jpeg = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
        "BwYIDAoMCwsKCwsKDA8QDQ0PDAsLDhEREhMRExoLFBweGxsSGRI//8AAEQABAAEB"
        "AwERAAIRAQMRAf/EABQAAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAA"
        "AAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oA"
        "DAMBAAIRAxEAPwCwAB//2Q=="
    )
    b64_data = "data:image/jpeg;base64," + base64.b64encode(tiny_jpeg).decode()

    payload = {
        "profiles": [
            {
                "profile_id": "avatar-test",
                "profile_url": "https://www.linkedin.com/in/avatar-test",
                "full_name": "Avatar Test",
                "avatar_data": b64_data,
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["contacts_created"] == 1

    result = await db.execute(
        select(Contact).where(Contact.linkedin_profile_id == "avatar-test")
    )
    contact = result.scalar_one()
    assert contact.avatar_url is not None
    assert contact.avatar_url.startswith("/static/avatars/")

    # Verify file exists on disk
    avatar_path = Path(__file__).resolve().parent.parent / contact.avatar_url.lstrip("/")
    assert avatar_path.exists()
    assert avatar_path.stat().st_size > 0

    # Cleanup
    avatar_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# backfill_needed — contacts missing title / company / avatar_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_returns_backfill_needed_for_incomplete_contact(
    client: AsyncClient,
    auth_headers: dict,
):
    """Contacts created without title, company, or avatar should appear in backfill_needed."""
    payload = {
        "profiles": [
            {
                "profile_id": "backfill-test-001",
                "profile_url": "https://www.linkedin.com/in/backfill-test-001",
                "full_name": "Backfill User",
                # no headline → no title extracted, no company, no avatar
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["contacts_created"] == 1

    backfill = data["backfill_needed"]
    assert len(backfill) == 1
    assert backfill[0]["linkedin_profile_id"] == "backfill-test-001"
    assert "contact_id" in backfill[0]


@pytest.mark.asyncio
async def test_push_omits_complete_contact_from_backfill(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """Existing contacts that already have title, company, and avatar_url are excluded from backfill_needed."""
    # Pre-create a contact that already has all enrichment fields populated
    existing = Contact(
        user_id=test_user.id,
        full_name="Complete User",
        linkedin_profile_id="complete-profile-002",
        title="Senior Engineer",
        company="FullCo",
        avatar_url="/static/avatars/complete-profile-002.jpg",
        source="manual",
    )
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    payload = {
        "profiles": [
            {
                "profile_id": "complete-profile-002",
                "profile_url": "https://www.linkedin.com/in/complete-profile-002",
                "full_name": "Complete User",
                "headline": "Senior Engineer at FullCo",
                "company": "FullCo",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["contacts_updated"] == 1

    # Contact already has title, company, and avatar_url — should not appear in backfill
    backfill = data["backfill_needed"]
    assert backfill == []


@pytest.mark.asyncio
async def test_push_clears_broken_remote_avatar_url(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """Push clears a non-local avatar_url (broken LinkedIn CDN URL)."""
    existing = Contact(
        user_id=test_user.id,
        full_name="Broken Avatar",
        linkedin_profile_id="broken-avatar",
        avatar_url="https://media.licdn.com/broken/image.jpg",
    )
    db.add(existing)
    await db.commit()

    payload = {
        "profiles": [
            {
                "profile_id": "broken-avatar",
                "profile_url": "https://www.linkedin.com/in/broken-avatar",
                "full_name": "Broken Avatar",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    await db.refresh(existing)
    # Remote URL should be cleared (not displayable from server)
    assert existing.avatar_url is None


# ---------------------------------------------------------------------------
# backfill_needed — contact missing only avatar_url (has title + company)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_returns_backfill_needed_for_missing_avatar(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """A contact that has title and company but no avatar should appear in backfill_needed."""
    payload = {
        "profiles": [
            {
                "profile_id": "needs-avatar-only",
                "profile_url": "https://www.linkedin.com/in/needs-avatar-only",
                "full_name": "Needs Avatar Only",
                "headline": "Engineer at WidgetCo",
                "company": "WidgetCo",
                # no avatar_data and no avatar_url → contact gets no avatar
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["contacts_created"] == 1

    backfill = data["backfill_needed"]
    ids = [item["linkedin_profile_id"] for item in backfill]
    assert "needs-avatar-only" in ids


# ---------------------------------------------------------------------------
# Contact creation — full_name is split into given_name / family_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_splits_full_name_into_given_family(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
):
    """A newly created contact must have given_name and family_name set from full_name."""
    payload = {
        "profiles": [
            {
                "profile_id": "name-split-test",
                "profile_url": "https://www.linkedin.com/in/name-split-test",
                "full_name": "Alice Wonderland",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["contacts_created"] == 1

    result = await db.execute(
        select(Contact).where(Contact.linkedin_profile_id == "name-split-test")
    )
    contact = result.scalar_one()
    assert contact.given_name == "Alice"
    assert contact.family_name == "Wonderland"


@pytest.mark.asyncio
async def test_push_handles_single_word_name(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
):
    """A contact with a single-word name gets given_name set and family_name left None."""
    payload = {
        "profiles": [
            {
                "profile_id": "mononym-test",
                "profile_url": "https://www.linkedin.com/in/mononym-test",
                "full_name": "Cher",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["contacts_created"] == 1

    result = await db.execute(
        select(Contact).where(Contact.linkedin_profile_id == "mononym-test")
    )
    contact = result.scalar_one()
    assert contact.given_name == "Cher"
    assert contact.family_name is None


# ---------------------------------------------------------------------------
# Name-based contact matching — profile_id is a Voyager URN (ACoAAA...)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_matches_contact_by_name_when_profile_id_is_urn(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """When a message arrives with a Voyager URN as profile_id, the backend
    should match an existing contact by full_name and back-fill the profile_id.
    """
    # Pre-create a contact without a linkedin_profile_id (imported from CSV, etc.)
    existing = Contact(
        user_id=test_user.id,
        full_name="Frank Castle",
        source="import",
    )
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    urn_id = "ACoAABcDEfGhIjKl"
    payload = {
        "profiles": [],
        "messages": [
            {
                "profile_id": urn_id,
                "profile_name": "Frank Castle",
                "direction": "inbound",
                "content_preview": "Hey Frank, long time!",
                "timestamp": "2026-03-01T10:00:00+00:00",
                "conversation_id": "conv-urn-001",
                "content_hash": "hash-urn-001",
            }
        ],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    # Should match existing contact, not create a new one
    assert data["contacts_created"] == 0
    assert data["interactions_created"] == 1

    # Existing contact should now have the URN stored as linkedin_profile_id
    await db.refresh(existing)
    assert existing.linkedin_profile_id == urn_id


# ---------------------------------------------------------------------------
# Profile-visit enrichment: member_id matching, ACo repair, enrich_only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_push_repairs_aco_contact_via_member_id(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """A profile-visit push (slug + member_id) should match a contact created
    from a DM under the anonymized ACo member id, enrich it, and upgrade its
    identity to the real public slug."""
    aco_id = "ACoAAAFS80wBexample"
    existing = Contact(
        user_id=test_user.id,
        full_name="Matt Lam",
        linkedin_profile_id=aco_id,  # created from a DM — anonymized id
        linkedin_url=f"https://www.linkedin.com/in/{aco_id}",
        source="linkedin",
    )
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    payload = {
        "enrich_only": True,
        "profiles": [
            {
                "profile_id": "mattjlam",
                "member_id": aco_id,
                "profile_url": "https://www.linkedin.com/in/mattjlam",
                "full_name": "Matt Lam",
                "headline": "Builder of Web3 Services",
                "company": "Bloq",
                "location": "San Francisco Bay Area",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contacts_created"] == 0
    assert data["contacts_updated"] == 1

    await db.refresh(existing)
    assert existing.company == "Bloq"
    assert existing.linkedin_headline == "Builder of Web3 Services"
    # ACo identity repaired to the real slug
    assert existing.linkedin_profile_id == "mattjlam"


@pytest.mark.asyncio
async def test_enrich_only_does_not_create_unknown_contact(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """enrich_only push for a profile that matches no contact must NOT create one."""
    payload = {
        "enrich_only": True,
        "profiles": [
            {
                "profile_id": "stranger-xyz",
                "member_id": "ACoStrangerXyz",
                "profile_url": "https://www.linkedin.com/in/stranger-xyz",
                "full_name": "Random Stranger",
                "company": "NowhereCo",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contacts_created"] == 0
    assert data["contacts_updated"] == 0

    result = await db.execute(
        select(Contact).where(Contact.linkedin_profile_id == "stranger-xyz")
    )
    assert result.scalar_one_or_none() is None, "enrich_only must not create strangers"


@pytest.mark.asyncio
async def test_non_enrich_push_still_creates_contact(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user,
):
    """Default (non-enrich) profile push still creates contacts (backfill path)."""
    payload = {
        "profiles": [
            {
                "profile_id": "created-via-backfill",
                "profile_url": "https://www.linkedin.com/in/created-via-backfill",
                "full_name": "New Person",
                "company": "AcmeCorp",
            }
        ],
        "messages": [],
    }

    resp = await client.post(PUSH_URL, json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["contacts_created"] == 1

    result = await db.execute(
        select(Contact).where(Contact.linkedin_profile_id == "created-via-backfill")
    )
    c = result.scalar_one_or_none()
    assert c is not None
    assert c.company == "AcmeCorp"
