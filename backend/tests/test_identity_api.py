"""Tests for identity resolution API endpoints.

Covers:
- Auth required for all endpoints (401 without token)
- Empty state (no matches returns empty list)
- Scan triggers identity resolution and returns counts
- List matches returns duplicate pairs with full contact data
- Confidence levels (high vs low score)
- Merge endpoint merges two contacts and updates status
- Reject endpoint dismisses a match and sets resolved_at
- Error cases (invalid / non-existent UUIDs, wrong ownership, already-resolved matches)
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.identity_match import IdentityMatch
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_contact(user_id: uuid.UUID, name: str, emails: list[str] | None = None, **kwargs) -> Contact:
    return Contact(user_id=user_id, full_name=name, emails=emails or [], **kwargs)


def _make_match(
    contact_a: Contact,
    contact_b: Contact,
    score: float = 0.8,
    method: str = "probabilistic",
    status: str = "pending_review",
) -> IdentityMatch:
    return IdentityMatch(
        contact_a_id=contact_a.id,
        contact_b_id=contact_b.id,
        match_score=score,
        match_method=method,
        status=status,
    )


# ---------------------------------------------------------------------------
# Auth-required tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_matches_requires_auth(client: AsyncClient):
    """GET /matches without a token must return 401."""
    resp = await client.get("/api/v1/identity/matches")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_scan_requires_auth(client: AsyncClient):
    """POST /scan without a token must return 401."""
    resp = await client.post("/api/v1/identity/scan")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_merge_requires_auth(client: AsyncClient):
    """POST /matches/{id}/merge without a token must return 401."""
    resp = await client.post(f"/api/v1/identity/matches/{uuid.uuid4()}/merge")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reject_requires_auth(client: AsyncClient):
    """POST /matches/{id}/reject without a token must return 401."""
    resp = await client.post(f"/api/v1/identity/matches/{uuid.uuid4()}/reject")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Empty-state tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_matches_empty_state(client: AsyncClient, auth_headers: dict, test_user: User):
    """When there are no pending matches the response data is an empty list."""
    resp = await client.get("/api/v1/identity/matches", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["meta"]["count"] == 0


@pytest.mark.asyncio
async def test_scan_with_no_contacts_returns_zeros(client: AsyncClient, auth_headers: dict):
    """Scanning when the user has no contacts returns all-zero counts."""
    resp = await client.post("/api/v1/identity/scan", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["auto_merged"] == 0
    assert data["pending_review"] == 0
    assert data["matches_found"] == 0


# ---------------------------------------------------------------------------
# Scan tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_triggers_identity_resolution(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Scan detects a duplicate pair that shares the same email."""
    c1 = _make_contact(test_user.id, "Diana Prince", ["diana@example.com"])
    c2 = _make_contact(test_user.id, "Diana P.", ["diana@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    resp = await client.post("/api/v1/identity/scan", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    # The shared email triggers deterministic auto-merge.
    assert data["auto_merged"] >= 1
    assert data["matches_found"] >= 1


@pytest.mark.asyncio
async def test_scan_returns_meta_id_lists(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Scan meta contains lists of auto_merged_ids and pending_review_ids."""
    c1 = _make_contact(test_user.id, "Eve Adams", ["eve@example.com"])
    c2 = _make_contact(test_user.id, "Eve A.", ["eve@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    resp = await client.post("/api/v1/identity/scan", headers=auth_headers)
    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert "auto_merged_ids" in meta
    assert "pending_review_ids" in meta
    assert isinstance(meta["auto_merged_ids"], list)
    assert isinstance(meta["pending_review_ids"], list)


# ---------------------------------------------------------------------------
# List matches tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_matches_returns_nested_contact_data(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Each match in the list includes full contact_a and contact_b objects."""
    c1 = _make_contact(test_user.id, "Frank Castle", ["frank@example.com"], company="Punisher LLC")
    c2 = _make_contact(test_user.id, "Frank C.", ["frank2@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    match = _make_match(c1, c2, score=0.85)
    db.add(match)
    await db.commit()

    resp = await client.get("/api/v1/identity/matches", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    item = data[0]
    assert item["contact_a"]["full_name"] == "Frank Castle"
    assert item["contact_a"]["company"] == "Punisher LLC"
    assert item["contact_b"]["full_name"] == "Frank C."
    assert item["match_score"] == pytest.approx(0.85)
    assert item["match_method"] == "probabilistic"


@pytest.mark.asyncio
async def test_list_matches_only_shows_pending_not_resolved(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Rejected or merged matches are not included in the list endpoint."""
    c1 = _make_contact(test_user.id, "Grace Hopper", ["grace@example.com"])
    c2 = _make_contact(test_user.id, "Grace H.", ["grace2@example.com"])
    c3 = _make_contact(test_user.id, "Grace Hops", ["graceh@example.com"])
    c4 = _make_contact(test_user.id, "G. Hopper", ["ghopper@example.com"])
    db.add_all([c1, c2, c3, c4])
    await db.commit()

    pending = _make_match(c1, c2, status="pending_review")
    rejected = _make_match(c3, c4, status="rejected")
    db.add_all([pending, rejected])
    await db.commit()

    resp = await client.get("/api/v1/identity/matches", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    # Only the pending match should be listed.
    assert len(data) == 1
    assert data[0]["status"] == "pending_review"


@pytest.mark.asyncio
async def test_list_matches_does_not_return_other_users_matches(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Matches belonging to another user are not returned."""
    # Create a second user's contacts and match.
    other_user = User(
        email=f"other-{uuid.uuid4()}@example.com",
        hashed_password="x",
        full_name="Other User",
    )
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    o1 = _make_contact(other_user.id, "Ivy Lee", ["ivy@example.com"])
    o2 = _make_contact(other_user.id, "Ivy L.", ["ivy2@example.com"])
    db.add_all([o1, o2])
    await db.commit()

    other_match = _make_match(o1, o2, status="pending_review")
    db.add(other_match)
    await db.commit()

    resp = await client.get("/api/v1/identity/matches", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# Confidence level tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_matches_high_confidence_score(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """A high-confidence match (score >= 0.95) is listed correctly."""
    c1 = _make_contact(test_user.id, "Jack Ryan", ["jack@example.com"])
    c2 = _make_contact(test_user.id, "Jack R.", ["jackr@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    match = _make_match(c1, c2, score=0.97)
    db.add(match)
    await db.commit()

    resp = await client.get("/api/v1/identity/matches", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["match_score"] >= 0.95


@pytest.mark.asyncio
async def test_list_matches_low_confidence_score(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """A low-confidence match (score just above threshold) is still returned."""
    c1 = _make_contact(test_user.id, "Karen Page", ["karen@example.com"])
    c2 = _make_contact(test_user.id, "K. Page", ["kpage@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    match = _make_match(c1, c2, score=0.51)
    db.add(match)
    await db.commit()

    resp = await client.get("/api/v1/identity/matches", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["match_score"] == pytest.approx(0.51)


# ---------------------------------------------------------------------------
# Merge tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_merge_sets_status_to_merged(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Merging a pending match returns status='merged' and resolved_at is set."""
    c1 = _make_contact(test_user.id, "Luke Cage", ["luke@example.com"])
    c2 = _make_contact(test_user.id, "L. Cage", ["lcage@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    match = _make_match(c1, c2, score=0.9)
    db.add(match)
    await db.commit()
    await db.refresh(match)

    resp = await client.post(f"/api/v1/identity/matches/{match.id}/merge", headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["status"] == "merged"
    assert result["resolved_at"] is not None


@pytest.mark.asyncio
async def test_merge_nonexistent_match_returns_404(
    client: AsyncClient, auth_headers: dict
):
    """Attempting to merge a non-existent match UUID returns 404."""
    resp = await client.post(f"/api/v1/identity/matches/{uuid.uuid4()}/merge", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_merge_already_merged_match_returns_400(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Merging a match that is already resolved returns 400."""
    c1 = _make_contact(test_user.id, "Matt Murdock", ["matt@example.com"])
    c2 = _make_contact(test_user.id, "M. Murdock", ["mmurdock@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    # Insert the match already in merged status.
    match = _make_match(c1, c2, status="merged")
    db.add(match)
    await db.commit()
    await db.refresh(match)

    resp = await client.post(f"/api/v1/identity/matches/{match.id}/merge", headers=auth_headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Reject (dismiss) tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_sets_resolved_at(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Rejecting a match sets resolved_at to a non-null ISO timestamp."""
    c1 = _make_contact(test_user.id, "Natasha Romanoff", ["natasha@example.com"])
    c2 = _make_contact(test_user.id, "N. Romanoff", ["nromanoff@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    match = _make_match(c1, c2, score=0.72)
    db.add(match)
    await db.commit()
    await db.refresh(match)

    resp = await client.post(f"/api/v1/identity/matches/{match.id}/reject", headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["status"] == "rejected"
    assert result["resolved_at"] is not None


@pytest.mark.asyncio
async def test_reject_nonexistent_match_returns_404(client: AsyncClient, auth_headers: dict):
    """Attempting to reject a non-existent match UUID returns 404."""
    resp = await client.post(f"/api/v1/identity/matches/{uuid.uuid4()}/reject", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_already_rejected_match_returns_400(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Attempting to reject an already-rejected match returns 400."""
    c1 = _make_contact(test_user.id, "Okoye Okafor", ["okoye@example.com"])
    c2 = _make_contact(test_user.id, "O. Okafor", ["ookafor@example.com"])
    db.add_all([c1, c2])
    await db.commit()

    match = _make_match(c1, c2, status="rejected")
    db.add(match)
    await db.commit()
    await db.refresh(match)

    resp = await client.post(f"/api/v1/identity/matches/{match.id}/reject", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reject_match_belonging_to_other_user_returns_403(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Trying to reject a match owned by another user returns 403."""
    other_user = User(
        email=f"villain-{uuid.uuid4()}@example.com",
        hashed_password="x",
        full_name="Villain",
    )
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    o1 = _make_contact(other_user.id, "Peter Parker", ["peter@example.com"])
    o2 = _make_contact(other_user.id, "P. Parker", ["pparker@example.com"])
    db.add_all([o1, o2])
    await db.commit()

    match = _make_match(o1, o2, status="pending_review")
    db.add(match)
    await db.commit()
    await db.refresh(match)

    # test_user tries to reject a match they don't own.
    resp = await client.post(f"/api/v1/identity/matches/{match.id}/reject", headers=auth_headers)
    assert resp.status_code == 403
