"""Tests for identity resolution API endpoints."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.identity_match import IdentityMatch
from app.models.user import User


@pytest.mark.asyncio
async def test_list_pending_matches(client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User):
    # Create two contacts
    c1 = Contact(user_id=test_user.id, full_name="Alice", emails=["alice@test.com"])
    c2 = Contact(user_id=test_user.id, full_name="Alise", emails=["alise@test.com"])
    db.add_all([c1, c2])
    await db.commit()

    # Create a pending match
    match = IdentityMatch(
        contact_a_id=c1.id,
        contact_b_id=c2.id,
        match_score=0.8,
        match_method="probabilistic",
        status="pending_review",
    )
    db.add(match)
    await db.commit()

    resp = await client.get("/api/v1/identity/matches", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "pending_review"
    # Verify nested contact objects are present
    assert data[0]["contact_a"] is not None
    assert data[0]["contact_b"] is not None
    assert "full_name" in data[0]["contact_a"]
    assert "emails" in data[0]["contact_a"]


@pytest.mark.asyncio
async def test_reject_match(client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User):
    c1 = Contact(user_id=test_user.id, full_name="Bob", emails=["bob@test.com"])
    c2 = Contact(user_id=test_user.id, full_name="Robert", emails=["robert@test.com"])
    db.add_all([c1, c2])
    await db.commit()

    match = IdentityMatch(
        contact_a_id=c1.id,
        contact_b_id=c2.id,
        match_score=0.75,
        match_method="probabilistic",
        status="pending_review",
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)

    resp = await client.post(f"/api/v1/identity/matches/{match.id}/reject", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_merge_match(client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User):
    c1 = Contact(user_id=test_user.id, full_name="Charlie", emails=["charlie@test.com"])
    c2 = Contact(user_id=test_user.id, full_name="Charles", emails=["charles@test.com"])
    db.add_all([c1, c2])
    await db.commit()

    match = IdentityMatch(
        contact_a_id=c1.id,
        contact_b_id=c2.id,
        match_score=0.9,
        match_method="probabilistic",
        status="pending_review",
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)

    resp = await client.post(f"/api/v1/identity/matches/{match.id}/merge", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "merged"


@pytest.mark.asyncio
async def test_trigger_scan(client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User):
    # Create contacts with shared email
    c1 = Contact(user_id=test_user.id, full_name="Dup One", emails=["dup@test.com"])
    c2 = Contact(user_id=test_user.id, full_name="Dup Two", emails=["dup@test.com"])
    db.add_all([c1, c2])
    await db.commit()

    resp = await client.post("/api/v1/identity/scan", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["auto_merged"] >= 1
    assert "matches_found" in data
    assert "pending_review" in data


@pytest.mark.asyncio
async def test_reject_nonexistent_match(client: AsyncClient, auth_headers: dict):
    resp = await client.post(f"/api/v1/identity/matches/{uuid.uuid4()}/reject", headers=auth_headers)
    assert resp.status_code == 404
