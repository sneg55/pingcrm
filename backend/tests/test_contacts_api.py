"""Tests for contacts API endpoints."""
import io
import uuid

import pytest
from httpx import AsyncClient

from app.models.contact import Contact
from app.models.user import User


@pytest.mark.asyncio
async def test_create_contact(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/contacts", json={
        "full_name": "Jane Smith",
        "emails": ["jane@test.com"],
        "company": "TestCorp",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["full_name"] == "Jane Smith"
    assert data["emails"] == ["jane@test.com"]


@pytest.mark.asyncio
async def test_list_contacts(client: AsyncClient, auth_headers: dict, test_contact: Contact):
    resp = await client.get("/api/v1/contacts", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) >= 1
    assert data["meta"]["total"] >= 1


@pytest.mark.asyncio
async def test_list_contacts_search(client: AsyncClient, auth_headers: dict, test_contact: Contact):
    resp = await client.get("/api/v1/contacts?search=John", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1

    resp = await client.get("/api/v1/contacts?search=NonExistent", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 0


@pytest.mark.asyncio
async def test_list_contacts_search_escapes_wildcards(client: AsyncClient, auth_headers: dict, test_contact: Contact):
    resp = await client.get("/api/v1/contacts?search=%25", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 0


@pytest.mark.asyncio
async def test_get_contact(client: AsyncClient, auth_headers: dict, test_contact: Contact):
    resp = await client.get(f"/api/v1/contacts/{test_contact.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["full_name"] == "John Doe"


@pytest.mark.asyncio
async def test_get_contact_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/contacts/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_contact(client: AsyncClient, auth_headers: dict, test_contact: Contact):
    resp = await client.put(f"/api/v1/contacts/{test_contact.id}", json={
        "company": "New Corp",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["company"] == "New Corp"


@pytest.mark.asyncio
async def test_delete_contact(client: AsyncClient, auth_headers: dict, test_contact: Contact):
    resp = await client.delete(f"/api/v1/contacts/{test_contact.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] is True

    resp = await client.get(f"/api/v1/contacts/{test_contact.id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_csv(client: AsyncClient, auth_headers: dict):
    csv_content = "full_name,emails,phones,company,twitter_handle,telegram_username,notes,tags\n"
    csv_content += "Alice Bob,alice@test.com,+1111,TestCo,@alice,alice_tg,Some notes,vip;friend\n"
    csv_content += "Bob Carol,bob@test.com,,OtherCo,,,,"

    resp = await client.post(
        "/api/v1/contacts/import/csv",
        files={"file": ("contacts.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["created"]) == 2
    assert len(data["errors"]) == 0


@pytest.mark.asyncio
async def test_import_csv_bad_file(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/contacts/import/csv",
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_contacts_score_filter_strong(
    client: AsyncClient, auth_headers: dict, db, test_user: User
):
    """Filter contacts by score=strong returns only high-score contacts."""
    from sqlalchemy.ext.asyncio import AsyncSession

    strong = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Strong",
        emails=["strong@test.com"], relationship_score=9,
    )
    weak = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Weak",
        emails=["weak@test.com"], relationship_score=2,
    )
    db.add_all([strong, weak])
    await db.commit()

    resp = await client.get("/api/v1/contacts?score=strong", headers=auth_headers)
    assert resp.status_code == 200
    names = [c["full_name"] for c in resp.json()["data"]]
    assert "Strong" in names
    assert "Weak" not in names


@pytest.mark.asyncio
async def test_list_contacts_score_filter_dormant(
    client: AsyncClient, auth_headers: dict, db, test_user: User
):
    """Filter contacts by score=dormant returns only low-score contacts."""
    strong = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Active",
        emails=["active@test.com"], relationship_score=8,
    )
    dormant = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Dormant",
        emails=["dormant@test.com"], relationship_score=1,
    )
    db.add_all([strong, dormant])
    await db.commit()

    resp = await client.get("/api/v1/contacts?score=dormant", headers=auth_headers)
    assert resp.status_code == 200
    names = [c["full_name"] for c in resp.json()["data"]]
    assert "Dormant" in names
    assert "Active" not in names


@pytest.mark.asyncio
async def test_list_contacts_score_filter_active(
    client: AsyncClient, auth_headers: dict, db, test_user: User
):
    """Filter contacts by score=active returns mid-range contacts."""
    mid = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Mid",
        emails=["mid@test.com"], relationship_score=5,
    )
    high = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="High",
        emails=["high@test.com"], relationship_score=9,
    )
    db.add_all([mid, high])
    await db.commit()

    resp = await client.get("/api/v1/contacts?score=active", headers=auth_headers)
    assert resp.status_code == 200
    names = [c["full_name"] for c in resp.json()["data"]]
    assert "Mid" in names
    assert "High" not in names


@pytest.mark.asyncio
async def test_recalculate_scores(
    client: AsyncClient, auth_headers: dict, test_contact: Contact
):
    """POST /contacts/scores/recalculate returns updated count."""
    resp = await client.post("/api/v1/contacts/scores/recalculate", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["updated"] >= 1


@pytest.mark.asyncio
async def test_refresh_bios_rate_limited(
    client: AsyncClient, auth_headers: dict, test_contact: Contact
):
    """POST /contacts/{id}/refresh-bios returns changes on first call, skipped on second."""
    import app.api.contacts as contacts_module

    # Clear rate-limit cache for this contact
    contacts_module._bio_check_cache.pop(str(test_contact.id), None)

    resp = await client.post(
        f"/api/v1/contacts/{test_contact.id}/refresh-bios", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # First call should not be skipped
    assert "skipped" not in data or data.get("skipped") is not True

    # Second immediate call should be rate-limited
    resp2 = await client.post(
        f"/api/v1/contacts/{test_contact.id}/refresh-bios", headers=auth_headers
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["skipped"] is True


@pytest.mark.asyncio
async def test_refresh_bios_not_found(client: AsyncClient, auth_headers: dict):
    """POST /contacts/{id}/refresh-bios returns 404 for non-existent contact."""
    import app.api.contacts as contacts_module

    fake_id = uuid.uuid4()
    contacts_module._bio_check_cache.pop(str(fake_id), None)

    resp = await client.post(
        f"/api/v1/contacts/{fake_id}/refresh-bios", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_find_duplicates(client: AsyncClient, auth_headers: dict, db, test_user: User):
    """GET /contacts/{id}/duplicates returns possible duplicates sorted by score."""
    target = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Alice Johnson",
        emails=["alice@company.com"], company="TechCorp",
    )
    similar = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Alice Johnson",
        emails=["alice.j@other.com"], company="TechCorp",
    )
    unrelated = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Zara Totally Different",
        emails=["zara@unrelated.com"],
    )
    db.add_all([target, similar, unrelated])
    await db.commit()

    resp = await client.get(f"/api/v1/contacts/{target.id}/duplicates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    # Should find the similar contact, not the unrelated one
    dup_ids = [d["id"] for d in data]
    assert str(similar.id) in dup_ids
    assert str(unrelated.id) not in dup_ids
    # Should have score field
    assert data[0]["score"] > 0


@pytest.mark.asyncio
async def test_find_duplicates_not_found(client: AsyncClient, auth_headers: dict):
    """GET /contacts/{id}/duplicates returns 404 for non-existent contact."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/contacts/{fake_id}/duplicates", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_find_duplicates_empty(client: AsyncClient, auth_headers: dict, test_contact: Contact):
    """GET /contacts/{id}/duplicates returns empty list when no duplicates."""
    resp = await client.get(f"/api/v1/contacts/{test_contact.id}/duplicates", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_merge_contacts(client: AsyncClient, auth_headers: dict, db, test_user: User):
    """POST /contacts/{id}/merge/{other_id} merges two contacts."""
    from sqlalchemy.ext.asyncio import AsyncSession

    primary = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Alice Primary",
        emails=["alice@primary.com"], company="PrimaryCorp",
    )
    secondary = Contact(
        id=uuid.uuid4(), user_id=test_user.id, full_name="Alice Secondary",
        emails=["alice@secondary.com"], phones=["+1234567890"],
    )
    db.add_all([primary, secondary])
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{primary.id}/merge/{secondary.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["merged_contact_id"] == str(secondary.id)

    # Secondary should be deleted
    resp2 = await client.get(f"/api/v1/contacts/{secondary.id}", headers=auth_headers)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_merge_contacts_not_found(client: AsyncClient, auth_headers: dict):
    """POST /contacts/{id}/merge/{other_id} returns 404 for missing contact."""
    fake_a = uuid.uuid4()
    fake_b = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/contacts/{fake_a}/merge/{fake_b}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_contacts_require_auth(client: AsyncClient):
    resp = await client.get("/api/v1/contacts")
    assert resp.status_code == 401
