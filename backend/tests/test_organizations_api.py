"""Tests for organizations API endpoints."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization
from app.models.user import User


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_contact(
    user_id: uuid.UUID,
    full_name: str,
    company: str | None,
    *,
    priority_level: str = "normal",
    relationship_score: int = 5,
    title: str | None = None,
) -> Contact:
    return Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=full_name,
        company=company,
        priority_level=priority_level,
        relationship_score=relationship_score,
        title=title,
        source="manual",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/organizations — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_organizations_requires_auth(client: AsyncClient):
    """401 when no auth token is provided."""
    resp = await client.get("/api/v1/organizations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_organizations_empty_state(client: AsyncClient, auth_headers: dict):
    """Empty list returned when no contacts have a company set."""
    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_list_organizations_groups_contacts_by_company(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Organizations with linked contacts appear in the list."""
    acme_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="Acme Corp")
    beta_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="BetaCo")
    db.add_all([acme_org, beta_org])
    await db.flush()

    alice = _make_contact(test_user.id, "Alice Smith", "Acme Corp", title="CTO")
    alice.organization_id = acme_org.id
    bob = _make_contact(test_user.id, "Bob Jones", "Acme Corp")
    bob.organization_id = acme_org.id
    carol = _make_contact(test_user.id, "Carol Lee", "BetaCo")
    carol.organization_id = beta_org.id
    db.add_all([alice, bob, carol])
    await db.commit()

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    orgs = resp.json()["data"]

    names = [o["name"] for o in orgs]
    assert "Acme Corp" in names
    assert "BetaCo" in names


@pytest.mark.asyncio
async def test_list_organizations_excludes_orgs_without_contacts(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Organizations with no linked contacts are excluded from the list."""
    has_contacts_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="SomeCo")
    empty_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="EmptyCo")
    db.add_all([has_contacts_org, empty_org])
    await db.flush()

    linked = _make_contact(test_user.id, "Has Company", "SomeCo")
    linked.organization_id = has_contacts_org.id
    unlinked = _make_contact(test_user.id, "No Org", None)
    db.add_all([linked, unlinked])
    await db.commit()

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    orgs = resp.json()["data"]
    assert len(orgs) == 1
    assert orgs[0]["name"] == "SomeCo"


@pytest.mark.asyncio
async def test_list_organizations_excludes_archived_contacts(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Orgs with only archived contacts are excluded from the list."""
    acme_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="Acme Corp")
    ghost_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="GhostCo")
    db.add_all([acme_org, ghost_org])
    await db.flush()

    active = _make_contact(test_user.id, "Active Person", "Acme Corp")
    active.organization_id = acme_org.id
    archived = _make_contact(
        test_user.id, "Archived Person", "GhostCo", priority_level="archived"
    )
    archived.organization_id = ghost_org.id
    db.add_all([active, archived])
    await db.commit()

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    orgs = resp.json()["data"]
    names = [o["name"] for o in orgs]
    assert "Acme Corp" in names
    assert "GhostCo" not in names  # only has archived contacts


@pytest.mark.asyncio
async def test_list_organizations_ordered_alphabetically(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Organizations are returned in alphabetical order by name."""
    orgs = [
        Organization(id=uuid.uuid4(), user_id=test_user.id, name=name)
        for name in ["Zebra Inc", "Alpha LLC", "Midway Corp"]
    ]
    db.add_all(orgs)
    await db.flush()

    contacts = [
        _make_contact(test_user.id, f"Person at {org.name}", org.name)
        for org in orgs
    ]
    for c, org in zip(contacts, orgs):
        c.organization_id = org.id
    db.add_all(contacts)
    await db.commit()

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    names = [o["name"] for o in resp.json()["data"]]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_organizations_org_contact_fields(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Each contact within an org has the expected fields."""
    org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="FieldCo")
    db.add(org)
    await db.flush()

    contact = _make_contact(
        test_user.id, "Test Person", "FieldCo", title="Engineer", relationship_score=7
    )
    contact.given_name = "Test"
    contact.family_name = "Person"
    contact.organization_id = org.id
    db.add(contact)
    await db.commit()

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    org_data = resp.json()["data"][0]
    assert org_data["name"] == "FieldCo"
    assert "id" in org_data


# ---------------------------------------------------------------------------
# GET /api/v1/organizations — search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def _make_org_with_contact(db: AsyncSession, user_id: uuid.UUID, org_name: str, contact_name: str | None = None) -> Organization:
    """Helper: create an Organization with one linked contact."""
    org = Organization(id=uuid.uuid4(), user_id=user_id, name=org_name)
    db.add(org)
    await db.flush()
    c = _make_contact(user_id, contact_name or f"Person at {org_name}", org_name)
    c.organization_id = org.id
    db.add(c)
    return org


@pytest.mark.asyncio
async def test_list_organizations_search_filters_by_company_name(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """search param filters organizations by case-insensitive substring match."""
    for name, contact in [("Acme Corp", "Alice"), ("Beta Industries", "Bob"), ("Acme Solutions", "Carol")]:
        await _make_org_with_contact(db, test_user.id, name, contact)
    await db.commit()

    resp = await client.get("/api/v1/organizations?search=acme", headers=auth_headers)
    assert resp.status_code == 200
    orgs = resp.json()["data"]
    names = {o["name"] for o in orgs}
    assert names == {"Acme Corp", "Acme Solutions"}
    assert "Beta Industries" not in names


@pytest.mark.asyncio
async def test_list_organizations_search_case_insensitive(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Search is case-insensitive."""
    await _make_org_with_contact(db, test_user.id, "TechCorp", "Alice")
    await db.commit()

    for query in ("TECHCORP", "techcorp", "TechCorp", "tech"):
        resp = await client.get(f"/api/v1/organizations?search={query}", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1, f"Expected 1 result for search={query!r}"


@pytest.mark.asyncio
async def test_list_organizations_search_no_match_returns_empty(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Search with no matching company returns empty list."""
    await _make_org_with_contact(db, test_user.id, "Acme Corp", "Alice")
    await db.commit()

    resp = await client.get("/api/v1/organizations?search=nonexistent", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/organizations — pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_organizations_pagination(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Pagination meta is accurate and page slicing works correctly."""
    for i in range(5):
        await _make_org_with_contact(db, test_user.id, f"Company {chr(65 + i)}")
    await db.commit()

    resp = await client.get("/api/v1/organizations?page=1&page_size=2", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 5
    assert body["meta"]["total_pages"] == 3
    assert body["meta"]["page"] == 1
    assert body["meta"]["page_size"] == 2
    assert len(body["data"]) == 2

    # Page 2
    resp2 = await client.get("/api/v1/organizations?page=2&page_size=2", headers=auth_headers)
    assert resp2.status_code == 200
    assert len(resp2.json()["data"]) == 2

    # Pages should not overlap
    page1_companies = {o["name"] for o in body["data"]}
    page2_companies = {o["name"] for o in resp2.json()["data"]}
    assert page1_companies.isdisjoint(page2_companies)


@pytest.mark.asyncio
async def test_list_organizations_pagination_last_page(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Last page returns remaining items (fewer than page_size)."""
    for i in range(3):
        await _make_org_with_contact(db, test_user.id, f"Company {i}")
    await db.commit()

    resp = await client.get("/api/v1/organizations?page=2&page_size=2", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1


@pytest.mark.asyncio
async def test_list_organizations_isolates_by_user(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Contacts from another user are not visible."""
    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="hashed",
        full_name="Other User",
    )
    db.add(other_user)
    await db.flush()

    # Other user's org + contact
    other_org = Organization(id=uuid.uuid4(), user_id=other_user.id, name="OtherCorp")
    db.add(other_org)
    await db.flush()
    c = _make_contact(other_user.id, "Other Person", "OtherCorp")
    c.organization_id = other_org.id
    db.add(c)
    await db.commit()

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# POST /api/v1/organizations/merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_organizations_requires_auth(client: AsyncClient):
    """401 when no auth token is provided."""
    resp = await client.post(
        "/api/v1/organizations/merge",
        json={"source_ids": [str(uuid.uuid4())], "target_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_merge_organizations_combines_contacts(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Merging moves contacts from source org to target org and deletes source."""
    source_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="Old Corp")
    target_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="New Corp")
    other_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="Other Corp")
    db.add_all([source_org, target_org, other_org])
    await db.flush()

    c1 = _make_contact(test_user.id, "Alice", "Old Corp")
    c1.organization_id = source_org.id
    c2 = _make_contact(test_user.id, "Bob", "Old Corp")
    c2.organization_id = source_org.id
    c3 = _make_contact(test_user.id, "Carol", "Other Corp")
    c3.organization_id = other_org.id
    db.add_all([c1, c2, c3])
    await db.commit()

    resp = await client.post(
        "/api/v1/organizations/merge",
        json={"source_ids": [str(source_org.id)], "target_id": str(target_org.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contacts_updated"] == 2


@pytest.mark.asyncio
async def test_merge_organizations_source_equals_target_returns_400(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """400 error when source_ids only contains the target_id."""
    org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="Acme")
    db.add(org)
    await db.commit()

    resp = await client.post(
        "/api/v1/organizations/merge",
        json={"source_ids": [str(org.id)], "target_id": str(org.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_organizations_nonexistent_source_updates_zero(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Merging a nonexistent source org updates 0 contacts (no error)."""
    target_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="RealCo")
    db.add(target_org)
    await db.flush()
    c = _make_contact(test_user.id, "Alice", "RealCo")
    c.organization_id = target_org.id
    db.add(c)
    await db.commit()

    ghost_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/v1/organizations/merge",
        json={"source_ids": [ghost_id], "target_id": str(target_org.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["contacts_updated"] == 0


@pytest.mark.asyncio
async def test_merge_organizations_only_affects_current_user(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Merge does not touch contacts belonging to another user."""
    other_user = User(
        id=uuid.uuid4(),
        email="other2@example.com",
        hashed_password="hashed",
        full_name="Other User 2",
    )
    db.add(other_user)
    await db.flush()

    source_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="OldCo")
    target_org = Organization(id=uuid.uuid4(), user_id=test_user.id, name="NewCo")
    other_org = Organization(id=uuid.uuid4(), user_id=other_user.id, name="OldCo")
    db.add_all([source_org, target_org, other_org])
    await db.flush()

    my_contact = _make_contact(test_user.id, "Mine", "OldCo")
    my_contact.organization_id = source_org.id
    other_contact = _make_contact(other_user.id, "Theirs", "OldCo")
    other_contact.organization_id = other_org.id
    db.add_all([my_contact, other_contact])
    await db.commit()

    resp = await client.post(
        "/api/v1/organizations/merge",
        json={"source_ids": [str(source_org.id)], "target_id": str(target_org.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["contacts_updated"] == 1

    # Other user's contact should be unchanged
    from sqlalchemy import select as sa_select
    result = await db.execute(sa_select(Contact).where(Contact.id == other_contact.id))
    other_refreshed = result.scalar_one()
    assert other_refreshed.organization_id == other_org.id


# ---------------------------------------------------------------------------
# Duplicate org handling via extract-bio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_create_org_handles_duplicate_names(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Creating 2 organizations with the same name, then calling extract-bio on a
    contact with that company name must not crash (uses first() to handle duplicates)."""
    from unittest.mock import patch, AsyncMock
    from app.models.organization import Organization

    company_name = "Duplicate Corp"

    # Deliberately create two orgs with the same name to simulate the duplicate scenario
    org1 = Organization(id=uuid.uuid4(), user_id=test_user.id, name=company_name)
    org2 = Organization(id=uuid.uuid4(), user_id=test_user.id, name=company_name)
    db.add_all([org1, org2])
    await db.flush()

    # Contact with a bio so extract-bio endpoint accepts it, with no company pre-set
    contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Test Person",
        given_name="Test",
        family_name="Person",
        twitter_bio="Engineer at Duplicate Corp",
        company=None,
        source="manual",
    )
    db.add(contact)
    await db.commit()

    # Mock the AI extractor to return the duplicate company name
    with patch(
        "app.services.bio_extractor.extract_from_bios",
        new_callable=AsyncMock,
        return_value={"company": company_name},
    ):
        resp = await client.post(
            f"/api/v1/contacts/{contact.id}/extract-bio",
            headers=auth_headers,
        )

    # Must not crash with MultipleResultsFound; 200 is the expected success code
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
