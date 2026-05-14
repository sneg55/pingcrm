"""Tests for /api/v1/contacts/tags/* (taxonomy) and /{id}/auto-tag endpoints."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.tag_taxonomy import TagTaxonomy
from app.models.user import User


# ---------------------------------------------------------------------------
# POST /tags/discover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/contacts/tags/discover")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_discover_400_when_no_contacts(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/contacts/tags/discover", headers=auth_headers
    )
    assert resp.status_code == 400
    assert "No contacts" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_discover_400_when_only_2nd_tier_contacts(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Contacts tagged '2nd tier' should be excluded from discovery, leaving zero analyzable."""
    db.add(Contact(
        user_id=test_user.id, full_name="LowTier", tags=["2nd tier"],
    ))
    await db.commit()

    resp = await client.post(
        "/api/v1/contacts/tags/discover", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_discover_creates_taxonomy(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """A successful discovery upserts a draft TagTaxonomy and returns the categories."""
    db.add_all([
        Contact(user_id=test_user.id, full_name="Alice", title="Engineer"),
        Contact(user_id=test_user.id, full_name="Bob", title="Designer"),
    ])
    await db.commit()

    discovered = {"Role": ["Engineer", "Designer"]}
    with patch(
        "app.services.auto_tagger.discover_taxonomy",
        new=AsyncMock(return_value=discovered),
    ), patch(
        "app.services.auto_tagger.deduplicate_taxonomy",
        new=AsyncMock(return_value=discovered),
    ):
        resp = await client.post(
            "/api/v1/contacts/tags/discover", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["categories"] == discovered
    assert data["total_tags"] == 2
    assert data["status"] == "draft"

    # Row was persisted
    tax = (await db.execute(
        select(TagTaxonomy).where(TagTaxonomy.user_id == test_user.id)
    )).scalar_one()
    assert tax.categories == discovered
    assert tax.status == "draft"


@pytest.mark.asyncio
async def test_discover_updates_existing_taxonomy(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Re-running discovery overwrites categories and resets status to draft."""
    db.add(TagTaxonomy(
        user_id=test_user.id, categories={"Old": ["x"]}, status="approved"
    ))
    db.add(Contact(user_id=test_user.id, full_name="A", title="Eng"))
    await db.commit()

    new_cats = {"New": ["y", "z"]}
    with patch(
        "app.services.auto_tagger.discover_taxonomy",
        new=AsyncMock(return_value=new_cats),
    ), patch(
        "app.services.auto_tagger.deduplicate_taxonomy",
        new=AsyncMock(return_value=new_cats),
    ):
        resp = await client.post(
            "/api/v1/contacts/tags/discover", headers=auth_headers
        )

    assert resp.status_code == 200
    tax = (await db.execute(
        select(TagTaxonomy).where(TagTaxonomy.user_id == test_user.id)
    )).scalar_one()
    assert tax.categories == new_cats
    assert tax.status == "draft"  # reset


@pytest.mark.asyncio
async def test_discover_ai_failure_returns_502(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    db.add(Contact(user_id=test_user.id, full_name="A", title="Eng"))
    await db.commit()

    with patch(
        "app.services.auto_tagger.discover_taxonomy",
        new=AsyncMock(side_effect=RuntimeError("anthropic down")),
    ):
        resp = await client.post(
            "/api/v1/contacts/tags/discover", headers=auth_headers
        )

    assert resp.status_code == 502
    assert "AI tag discovery failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /tags/taxonomy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_taxonomy_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/contacts/tags/taxonomy")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_taxonomy_none_when_missing(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/contacts/tags/taxonomy", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"] is None


@pytest.mark.asyncio
async def test_get_taxonomy_returns_categories(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    db.add(TagTaxonomy(
        user_id=test_user.id,
        categories={"Role": ["A", "B"], "Industry": ["C"]},
        status="approved",
    ))
    await db.commit()

    resp = await client.get(
        "/api/v1/contacts/tags/taxonomy", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["categories"] == {"Role": ["A", "B"], "Industry": ["C"]}
    assert data["total_tags"] == 3
    assert data["status"] == "approved"


@pytest.mark.asyncio
async def test_get_taxonomy_isolated_per_user(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, user_factory
):
    other = await user_factory()
    db.add(TagTaxonomy(
        user_id=other.id, categories={"Other": ["x"]}, status="approved"
    ))
    await db.commit()

    resp = await client.get(
        "/api/v1/contacts/tags/taxonomy", headers=auth_headers
    )
    assert resp.json()["data"] is None  # current user has none


# ---------------------------------------------------------------------------
# PUT /tags/taxonomy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_taxonomy_requires_auth(client: AsyncClient):
    resp = await client.put(
        "/api/v1/contacts/tags/taxonomy", json={"categories": {}}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_taxonomy_creates_when_missing(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    body = {"categories": {"Role": ["Eng"]}, "status": "approved"}
    resp = await client.put(
        "/api/v1/contacts/tags/taxonomy", json=body, headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["categories"] == {"Role": ["Eng"]}
    assert data["status"] == "approved"
    assert data["total_tags"] == 1

    tax = (await db.execute(
        select(TagTaxonomy).where(TagTaxonomy.user_id == test_user.id)
    )).scalar_one()
    assert tax.status == "approved"


@pytest.mark.asyncio
async def test_update_taxonomy_overwrites_categories(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    db.add(TagTaxonomy(
        user_id=test_user.id, categories={"Old": ["x"]}, status="draft"
    ))
    await db.commit()

    body = {"categories": {"New": ["a", "b"]}, "status": "approved"}
    resp = await client.put(
        "/api/v1/contacts/tags/taxonomy", json=body, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["categories"] == {"New": ["a", "b"]}

    tax = (await db.execute(
        select(TagTaxonomy).where(TagTaxonomy.user_id == test_user.id)
    )).scalar_one()
    assert tax.categories == {"New": ["a", "b"]}
    assert tax.status == "approved"


@pytest.mark.asyncio
async def test_update_taxonomy_keeps_status_when_not_provided(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    db.add(TagTaxonomy(
        user_id=test_user.id, categories={"Old": ["x"]}, status="approved"
    ))
    await db.commit()

    body = {"categories": {"X": ["y"]}}  # no status field
    resp = await client.put(
        "/api/v1/contacts/tags/taxonomy", json=body, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "approved"  # unchanged


@pytest.mark.asyncio
async def test_update_taxonomy_rejects_bad_status(
    client: AsyncClient, auth_headers: dict
):
    body = {"categories": {"R": []}, "status": "nonsense"}
    resp = await client.put(
        "/api/v1/contacts/tags/taxonomy", json=body, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_taxonomy_rejects_bad_payload(
    client: AsyncClient, auth_headers: dict
):
    # categories is required
    resp = await client.put(
        "/api/v1/contacts/tags/taxonomy", json={}, headers=auth_headers
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /tags/apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/contacts/tags/apply", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_apply_400_when_no_taxonomy(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/contacts/tags/apply", json={}, headers=auth_headers
    )
    assert resp.status_code == 400
    assert "approved" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_apply_400_when_taxonomy_draft(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    db.add(TagTaxonomy(
        user_id=test_user.id, categories={"Role": ["Eng"]}, status="draft"
    ))
    await db.commit()

    resp = await client.post(
        "/api/v1/contacts/tags/apply", json={}, headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_apply_inline_tags_small_set(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """Small contact_ids set is processed inline — assigned tags merged into each contact."""
    db.add(TagTaxonomy(
        user_id=test_user.id,
        categories={"Role": ["Eng", "Designer"]},
        status="approved",
    ))
    c1 = Contact(user_id=test_user.id, full_name="A", tags=["Existing"])
    c2 = Contact(user_id=test_user.id, full_name="B", tags=None)
    db.add_all([c1, c2])
    await db.commit()

    # Mock anthropic client builder + assign_tags returns deterministic tags
    with patch(
        "app.services.auto_tagger._get_anthropic_client",
        return_value=MagicMock(),
    ), patch(
        "app.services.auto_tagger.assign_tags",
        new=AsyncMock(return_value=["Eng"]),
    ):
        resp = await client.post(
            "/api/v1/contacts/tags/apply",
            json={"contact_ids": [str(c1.id), str(c2.id)]},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["task_id"] is None
    assert data["tagged_count"] == 2

    await db.refresh(c1)
    await db.refresh(c2)
    assert "Eng" in c1.tags
    assert "Existing" in c1.tags  # preserved
    assert "Eng" in c2.tags


@pytest.mark.asyncio
async def test_apply_inline_skips_when_assign_returns_empty(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    db.add(TagTaxonomy(
        user_id=test_user.id,
        categories={"Role": ["Eng"]},
        status="approved",
    ))
    c = Contact(user_id=test_user.id, full_name="A", tags=["X"])
    db.add(c)
    await db.commit()

    with patch(
        "app.services.auto_tagger._get_anthropic_client",
        return_value=MagicMock(),
    ), patch(
        "app.services.auto_tagger.assign_tags",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.post(
            "/api/v1/contacts/tags/apply",
            json={"contact_ids": [str(c.id)]},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["tagged_count"] == 0
    await db.refresh(c)
    assert c.tags == ["X"]  # unchanged


@pytest.mark.asyncio
async def test_apply_defaults_to_all_user_contacts(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """No contact_ids → apply to all user's non-archived, non-2nd-tier contacts."""
    db.add(TagTaxonomy(
        user_id=test_user.id,
        categories={"Role": ["Eng"]},
        status="approved",
    ))
    eligible = Contact(user_id=test_user.id, full_name="Yes", tags=None)
    excluded_archived = Contact(
        user_id=test_user.id, full_name="Archived", priority_level="archived"
    )
    excluded_2nd = Contact(
        user_id=test_user.id, full_name="LowTier", tags=["2nd tier"]
    )
    db.add_all([eligible, excluded_archived, excluded_2nd])
    await db.commit()

    with patch(
        "app.services.auto_tagger._get_anthropic_client",
        return_value=MagicMock(),
    ), patch(
        "app.services.auto_tagger.assign_tags",
        new=AsyncMock(return_value=["Eng"]),
    ):
        resp = await client.post(
            "/api/v1/contacts/tags/apply",
            json={},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["tagged_count"] == 1

    await db.refresh(eligible)
    await db.refresh(excluded_archived)
    await db.refresh(excluded_2nd)
    assert "Eng" in (eligible.tags or [])
    # excluded ones not modified
    assert excluded_archived.tags in (None, [])
    assert "Eng" not in (excluded_2nd.tags or [])


@pytest.mark.asyncio
async def test_apply_enqueues_celery_for_large_set(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """When >20 contact ids, route enqueues Celery and returns task_id."""
    db.add(TagTaxonomy(
        user_id=test_user.id,
        categories={"Role": ["Eng"]},
        status="approved",
    ))
    contact_ids = [uuid.uuid4() for _ in range(21)]
    await db.commit()

    fake_task = MagicMock()
    fake_task.id = "fake-celery-task-id"
    with patch(
        "app.services.tasks.apply_tags_to_contacts.delay",
        return_value=fake_task,
    ) as mock_delay:
        resp = await client.post(
            "/api/v1/contacts/tags/apply",
            json={"contact_ids": [str(cid) for cid in contact_ids]},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["task_id"] == "fake-celery-task-id"
    assert data["tagged_count"] == 0
    mock_delay.assert_called_once()


# ---------------------------------------------------------------------------
# POST /{contact_id}/auto-tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_tag_requires_auth(client: AsyncClient):
    resp = await client.post(f"/api/v1/contacts/{uuid.uuid4()}/auto-tag")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auto_tag_400_when_no_approved_taxonomy(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    # taxonomy exists but draft
    db.add(TagTaxonomy(
        user_id=test_user.id, categories={"R": ["A"]}, status="draft"
    ))
    c = Contact(user_id=test_user.id, full_name="X")
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/auto-tag", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_auto_tag_404_for_missing_contact(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    db.add(TagTaxonomy(
        user_id=test_user.id, categories={"R": ["A"]}, status="approved"
    ))
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{uuid.uuid4()}/auto-tag", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auto_tag_cross_user_returns_404(
    client: AsyncClient, auth_headers: dict, db: AsyncSession,
    test_user: User, user_factory
):
    db.add(TagTaxonomy(
        user_id=test_user.id, categories={"R": ["A"]}, status="approved"
    ))
    other = await user_factory()
    c = Contact(user_id=other.id, full_name="Theirs")
    db.add(c)
    await db.commit()

    resp = await client.post(
        f"/api/v1/contacts/{c.id}/auto-tag", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auto_tag_assigns_and_merges(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    db.add(TagTaxonomy(
        user_id=test_user.id,
        categories={"Role": ["Eng", "PM"]},
        status="approved",
    ))
    c = Contact(user_id=test_user.id, full_name="X", tags=["Friend"])
    db.add(c)
    await db.commit()

    with patch(
        "app.services.auto_tagger.assign_tags",
        new=AsyncMock(return_value=["Eng", "PM"]),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/auto-tag", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data["tags_added"]) == {"Eng", "PM"}
    assert "Friend" in data["all_tags"]
    assert "Eng" in data["all_tags"]
    assert "PM" in data["all_tags"]

    await db.refresh(c)
    assert "Friend" in c.tags
    assert "Eng" in c.tags
    assert "PM" in c.tags


@pytest.mark.asyncio
async def test_auto_tag_no_new_tags(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    """When assign_tags returns empty, tags_added is empty and existing tags are kept."""
    db.add(TagTaxonomy(
        user_id=test_user.id,
        categories={"Role": ["Eng"]},
        status="approved",
    ))
    c = Contact(user_id=test_user.id, full_name="X", tags=["Existing"])
    db.add(c)
    await db.commit()

    with patch(
        "app.services.auto_tagger.assign_tags",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.post(
            f"/api/v1/contacts/{c.id}/auto-tag", headers=auth_headers
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tags_added"] == []
    assert data["all_tags"] == ["Existing"]
