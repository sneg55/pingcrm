"""Tests for /api/v1/contacts/{id}/enrich, /extract-bio, /promote endpoints."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.apollo import ApolloError
from app.models.contact import Contact
from app.models.organization import Organization
from app.models.user import User


# ---------------------------------------------------------------------------
# POST /{contact_id}/enrich
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_requires_auth(client: AsyncClient):
    cid = uuid.uuid4()
    resp = await client.post(f"/api/v1/contacts/{cid}/enrich")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_enrich_contact_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/v1/contacts/{uuid.uuid4()}/enrich", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enrich_cross_user_returns_404(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    user_factory,
):
    other = await user_factory()
    c = Contact(
        user_id=other.id, full_name="Other Owner",
        emails=["nope@example.com"],
    )
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/enrich", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enrich_requires_email_or_linkedin(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    c = Contact(user_id=test_user.id, full_name="No Identifiers")
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/enrich", headers=auth_headers
    )
    assert resp.status_code == 400
    assert "email or LinkedIn" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_enrich_fills_empty_fields_only(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Apollo data should populate empty fields but never overwrite existing values."""
    c = Contact(
        user_id=test_user.id,
        full_name="Existing Name",  # already set — should NOT be overwritten
        emails=["alice@example.com"],
        company=None,
        title=None,
    )
    db.add(c)
    await db.commit()

    apollo_payload = {
        "given_name": "Alice",
        "family_name": "Smith",
        "full_name": "Alice Smith (Apollo)",  # ignored: existing
        "title": "CEO",
        "company": "Acme",
        "phones": ["+1-555-1234"],
        "emails": ["alice.alt@example.com"],
    }

    with patch(
        "app.integrations.apollo.enrich_person",
        new=AsyncMock(return_value=apollo_payload),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/enrich", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source"] == "apollo"
    # given_name, family_name, title, company filled; full_name skipped
    assert "given_name" in data["fields_updated"]
    assert "family_name" in data["fields_updated"]
    assert "title" in data["fields_updated"]
    assert "company" in data["fields_updated"]
    assert "phones" in data["fields_updated"]
    assert "emails" in data["fields_updated"]
    assert "full_name" not in data["fields_updated"]

    await db.refresh(c)
    assert c.full_name == "Existing Name"  # preserved
    assert c.given_name == "Alice"
    assert c.title == "CEO"
    assert c.company == "Acme"
    assert "+1-555-1234" in c.phones
    assert "alice@example.com" in c.emails
    assert "alice.alt@example.com" in c.emails


@pytest.mark.asyncio
async def test_enrich_no_match_returns_empty_fields_updated(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    c = Contact(user_id=test_user.id, full_name="X", emails=["x@example.com"])
    db.add(c)
    await db.commit()

    with patch(
        "app.integrations.apollo.enrich_person",
        new=AsyncMock(return_value={}),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/enrich", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["fields_updated"] == []
    assert data["source"] == "apollo"


@pytest.mark.asyncio
async def test_enrich_apollo_error_propagates_status(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    c = Contact(user_id=test_user.id, emails=["bad@example.com"])
    db.add(c)
    await db.commit()

    with patch(
        "app.integrations.apollo.enrich_person",
        new=AsyncMock(side_effect=ApolloError("rate limited", status_code=429)),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/enrich", headers=auth_headers
        )

    assert resp.status_code == 429
    assert "rate limited" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_enrich_apollo_error_without_status_defaults_to_502(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    c = Contact(user_id=test_user.id, emails=["bad@example.com"])
    db.add(c)
    await db.commit()

    with patch(
        "app.integrations.apollo.enrich_person",
        new=AsyncMock(side_effect=ApolloError("upstream broke")),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/enrich", headers=auth_headers
        )

    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_enrich_uses_linkedin_when_no_emails(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """If contact has no emails, the linkedin_url should be passed to Apollo."""
    c = Contact(
        user_id=test_user.id,
        full_name="LinkedIn Only",
        emails=[],
        linkedin_url="https://linkedin.com/in/lonly",
    )
    db.add(c)
    await db.commit()

    mock_enrich = AsyncMock(return_value={"title": "Engineer"})
    with patch("app.integrations.apollo.enrich_person", new=mock_enrich):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/enrich", headers=auth_headers
        )

    assert resp.status_code == 200
    mock_enrich.assert_awaited_once()
    kwargs = mock_enrich.call_args.kwargs
    assert kwargs["email"] is None
    assert kwargs["linkedin_url"] == "https://linkedin.com/in/lonly"


# ---------------------------------------------------------------------------
# POST /{contact_id}/extract-bio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_bio_requires_auth(client: AsyncClient):
    cid = uuid.uuid4()
    resp = await client.post(f"/api/v1/contacts/{cid}/extract-bio")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_extract_bio_404_for_missing_contact(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        f"/api/v1/contacts/{uuid.uuid4()}/extract-bio", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extract_bio_400_when_nothing_to_extract(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """No bios, no full_name → 400."""
    c = Contact(user_id=test_user.id, emails=["a@b.com"])
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/extract-bio", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_extract_bio_updates_name_and_title(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """given/family name overwrite; title fills only when empty."""
    c = Contact(
        user_id=test_user.id,
        full_name="Old Name",
        twitter_bio="Builder of things",
        title=None,
    )
    db.add(c)
    await db.commit()

    extracted = {
        "given_name": "Bob",
        "family_name": "Builder",
        "title": "Construction Engineer",
    }
    with patch(
        "app.services.bio_extractor.extract_from_bios",
        new=AsyncMock(return_value=extracted),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/extract-bio", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source"] == "ai_bio"
    assert "given_name" in data["fields_updated"]
    assert "family_name" in data["fields_updated"]
    assert "title" in data["fields_updated"]
    # full_name gets recomputed from given + family
    assert "full_name" in data["fields_updated"]

    await db.refresh(c)
    assert c.given_name == "Bob"
    assert c.family_name == "Builder"
    assert c.full_name == "Bob Builder"
    assert c.title == "Construction Engineer"


@pytest.mark.asyncio
async def test_extract_bio_preserves_existing_title(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """If title already set, AI must not overwrite it."""
    c = Contact(
        user_id=test_user.id,
        full_name="Jane Doe",
        twitter_bio="bio",
        title="VP Engineering",
    )
    db.add(c)
    await db.commit()

    with patch(
        "app.services.bio_extractor.extract_from_bios",
        new=AsyncMock(return_value={"title": "Junior Coder"}),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/extract-bio", headers=auth_headers
        )

    assert resp.status_code == 200
    assert "title" not in resp.json()["data"]["fields_updated"]
    await db.refresh(c)
    assert c.title == "VP Engineering"


@pytest.mark.asyncio
async def test_extract_bio_no_extractions(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    c = Contact(user_id=test_user.id, full_name="Nothing To See", twitter_bio="x")
    db.add(c)
    await db.commit()

    with patch(
        "app.services.bio_extractor.extract_from_bios",
        new=AsyncMock(return_value={}),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/extract-bio", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["fields_updated"] == []
    assert data["source"] == "ai_bio"


@pytest.mark.asyncio
async def test_extract_bio_creates_organization_and_enriches_it(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """When AI returns company + company metadata, an Organization should be created/updated."""
    c = Contact(
        user_id=test_user.id,
        full_name="Carol Lead",
        twitter_bio="CEO @ Whimsy Labs",
        company=None,
    )
    db.add(c)
    await db.commit()

    extracted = {
        "given_name": "Carol",
        "family_name": "Lead",
        "company": "Whimsy Labs",
        "company_website": "whimsy.example",
        "company_industry": "AI",
        "company_location": "Remote",
    }
    with patch(
        "app.services.bio_extractor.extract_from_bios",
        new=AsyncMock(return_value=extracted),
    ), patch(
        "app.services.organization_service.download_org_logo",
        new=AsyncMock(return_value=None),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/extract-bio", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "company" in data["fields_updated"]
    assert "company_website" in data["fields_updated"]
    assert "company_industry" in data["fields_updated"]
    assert "company_location" in data["fields_updated"]

    # Org row was created and tied to the contact
    await db.refresh(c)
    assert c.organization_id is not None
    org = (await db.execute(
        select(Organization).where(Organization.id == c.organization_id)
    )).scalar_one()
    assert org.website == "whimsy.example"
    assert org.industry == "AI"
    assert org.location == "Remote"


@pytest.mark.asyncio
async def test_extract_bio_cross_user_returns_404(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, user_factory
):
    other = await user_factory()
    c = Contact(user_id=other.id, full_name="theirs", twitter_bio="bio")
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/extract-bio", headers=auth_headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /{contact_id}/promote
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_requires_auth(client: AsyncClient):
    resp = await client.post(f"/api/v1/contacts/{uuid.uuid4()}/promote")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_promote_404_for_missing_contact(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        f"/api/v1/contacts/{uuid.uuid4()}/promote", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_promote_removes_2nd_tier_tag(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    c = Contact(
        user_id=test_user.id,
        full_name="Pending Promote",
        tags=["Founder", "2nd tier", "Crypto"],
    )
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/promote", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["promoted"] is True
    assert body["id"] == str(c.id)

    await db.refresh(c)
    assert "2nd tier" not in [t.lower() for t in (c.tags or [])]
    assert "Founder" in c.tags
    assert "Crypto" in c.tags


@pytest.mark.asyncio
async def test_promote_case_insensitive(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Tag may be stored with mixed case — promote must still strip it."""
    c = Contact(
        user_id=test_user.id,
        full_name="MixedCase",
        tags=["2ND TIER", "Founder"],
    )
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/promote", headers=auth_headers
    )
    assert resp.status_code == 200

    await db.refresh(c)
    assert "2ND TIER" not in (c.tags or [])


@pytest.mark.asyncio
async def test_promote_400_when_not_2nd_tier(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    c = Contact(user_id=test_user.id, full_name="Normal", tags=["Friend"])
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/promote", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_promote_cross_user_returns_404(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, user_factory
):
    other = await user_factory()
    c = Contact(user_id=other.id, full_name="theirs", tags=["2nd tier"])
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/promote", headers=auth_headers
    )
    assert resp.status_code == 404
