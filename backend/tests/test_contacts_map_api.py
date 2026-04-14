from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.contact import Contact
from app.models.user import User


@pytest.mark.asyncio
async def test_map_endpoint_returns_contacts_in_bbox(
    client: AsyncClient, test_user: User, auth_headers: dict, db
):
    db.add(Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Alice",
        location="SF",
        latitude=37.77,
        longitude=-122.42,
        relationship_score=80,
    ))
    db.add(Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Bob",
        location="NYC",
        latitude=40.71,
        longitude=-74.00,
        relationship_score=50,
    ))
    db.add(Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Carol",
        location="Mars",
    ))
    await db.commit()

    resp = await client.get(
        "/api/v1/contacts/map?bbox=-123,37,-122,38", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = [p["full_name"] for p in body["data"]]
    assert names == ["Alice"]
    assert body["data"][0]["latitude"] == pytest.approx(37.77)
    assert body["meta"]["total_in_bounds"] == 1


@pytest.mark.asyncio
async def test_map_endpoint_isolates_users(
    client: AsyncClient, test_user: User, auth_headers: dict, user_factory, db
):
    other = await user_factory()
    db.add(Contact(
        id=uuid.uuid4(),
        user_id=other.id,
        full_name="Eve",
        location="SF",
        latitude=37.77,
        longitude=-122.42,
    ))
    await db.commit()

    resp = await client.get(
        "/api/v1/contacts/map?bbox=-123,37,-122,38", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_map_endpoint_caps_at_500(
    client: AsyncClient, test_user: User, auth_headers: dict, db
):
    for _ in range(510):
        db.add(Contact(
            id=uuid.uuid4(),
            user_id=test_user.id,
            full_name="C",
            location="SF",
            latitude=37.77,
            longitude=-122.42,
        ))
    await db.commit()

    resp = await client.get(
        "/api/v1/contacts/map?bbox=-123,37,-122,38&limit=1000", headers=auth_headers
    )
    body = resp.json()
    assert len(body["data"]) == 500
    assert body["meta"]["total_in_bounds"] == 510


@pytest.mark.asyncio
async def test_map_endpoint_rejects_bad_bbox(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/contacts/map?bbox=not-a-bbox", headers=auth_headers
    )
    assert resp.status_code == 400
