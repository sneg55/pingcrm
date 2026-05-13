"""Tests for organization duplicate endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization
from app.models.user import User


@pytest.mark.asyncio
async def test_scan_duplicates_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/organizations/scan-duplicates", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_scan_duplicates_returns_summary(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic Inc", domain="anthropic.com")
    c = Organization(user_id=test_user.id, name="Stripe")
    d = Organization(user_id=test_user.id, name="Stripe Payments")
    db.add_all([a, b, c, d])
    await db.commit()

    resp = await client.post("/api/v1/organizations/scan-duplicates",
                              json={}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["matches_found"] >= 2
    assert data["auto_merged"] == 1  # Anthropic pair
    assert data["pending_review"] >= 1  # Stripe pair


@pytest.mark.asyncio
async def test_scan_duplicates_empty_user(
    client: AsyncClient, auth_headers: dict
):
    """User with no orgs gets zero-result summary."""
    resp = await client.post("/api/v1/organizations/scan-duplicates",
                              json={}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"matches_found": 0, "auto_merged": 0, "pending_review": 0}


from app.models.org_identity_match import OrgIdentityMatch


@pytest.mark.asyncio
async def test_list_duplicates_returns_pending(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    a = Organization(user_id=test_user.id, name="Stripe")
    b = Organization(user_id=test_user.id, name="Stripe Payments")
    db.add_all([a, b])
    await db.flush()

    match = OrgIdentityMatch(
        user_id=test_user.id,
        org_a_id=a.id, org_b_id=b.id,
        match_score=0.65,
        match_method="probabilistic",
        status="pending_review",
    )
    db.add(match)
    await db.commit()

    resp = await client.get("/api/v1/organizations/duplicates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["match_score"] == 0.65
    assert data[0]["status"] == "pending_review"
    assert data[0]["org_a"]["name"] in ("Stripe", "Stripe Payments")
    assert data[0]["org_b"]["name"] in ("Stripe", "Stripe Payments")


@pytest.mark.asyncio
async def test_list_duplicates_excludes_resolved(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    a = Organization(user_id=test_user.id, name="Foo")
    b = Organization(user_id=test_user.id, name="Foo Inc")
    db.add_all([a, b])
    await db.flush()

    db.add(OrgIdentityMatch(
        user_id=test_user.id, org_a_id=a.id, org_b_id=b.id,
        match_score=0.65, match_method="probabilistic", status="dismissed",
    ))
    await db.commit()

    resp = await client.get("/api/v1/organizations/duplicates", headers=auth_headers)
    assert resp.json()["data"] == []
