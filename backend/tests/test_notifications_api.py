"""Tests for notifications API endpoints."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_notification(
    db: AsyncSession,
    user: User,
    *,
    notification_type: str = "suggestion",
    title: str = "Test",
    body: str = "Body",
    link: str | None = None,
    read: bool = False,
) -> Notification:
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        notification_type=notification_type,
        title=title,
        body=body,
        link=link,
        read=read,
    )
    db.add(notif)
    await db.flush()
    return notif


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_notifications(client: AsyncClient, auth_headers: dict, test_notification: Notification):
    resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) >= 1
    assert data["data"][0]["notification_type"] == "suggestion"


@pytest.mark.asyncio
async def test_unread_count(client: AsyncClient, auth_headers: dict, test_notification: Notification):
    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["count"] >= 1


@pytest.mark.asyncio
async def test_mark_read(client: AsyncClient, auth_headers: dict, test_notification: Notification):
    resp = await client.put(f"/api/v1/notifications/{test_notification.id}/read", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["read"] is True

    # Count should decrease
    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["count"] == 0


@pytest.mark.asyncio
async def test_mark_read_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.put(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read(client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User):
    # Create multiple unread notifications
    for i in range(3):
        n = Notification(
            user_id=test_user.id,
            notification_type="event",
            title=f"Event {i}",
            body=f"Body {i}",
            read=False,
        )
        db.add(n)
    await db.flush()

    resp = await client.put("/api/v1/notifications/read-all", headers=auth_headers)
    assert resp.status_code == 200

    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["count"] == 0


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_notifications_pagination(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
):
    """page_size=2 with 5 notifications should return only 2 items and correct meta."""
    for i in range(5):
        await _create_notification(db, test_user, title=f"Notif {i}")
    await db.commit()

    resp = await client.get(
        "/api/v1/notifications",
        params={"page": 1, "page_size": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 5
    assert body["meta"]["page"] == 1
    assert body["meta"]["page_size"] == 2
    assert body["meta"]["total_pages"] == 3


@pytest.mark.asyncio
async def test_list_notifications_pagination_second_page(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
):
    for i in range(4):
        await _create_notification(db, test_user, title=f"Notif {i}")
    await db.commit()

    resp = await client.get(
        "/api/v1/notifications",
        params={"page": 2, "page_size": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["meta"]["page"] == 2


# ---------------------------------------------------------------------------
# Mark read — response shape and idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_single_notification_read_response_shape(
    client: AsyncClient,
    auth_headers: dict,
    test_notification: Notification,
):
    """Response must contain id and read=True inside data envelope."""
    resp = await client.put(
        f"/api/v1/notifications/{test_notification.id}/read",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["id"] == str(test_notification.id)
    assert body["data"]["read"] is True


@pytest.mark.asyncio
async def test_mark_single_notification_read_idempotent(
    client: AsyncClient,
    auth_headers: dict,
    test_notification: Notification,
):
    """Marking an already-read notification read again must return 200."""
    # First mark
    resp = await client.put(
        f"/api/v1/notifications/{test_notification.id}/read",
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Second mark — should still succeed
    resp = await client.put(
        f"/api/v1/notifications/{test_notification.id}/read",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["read"] is True


# ---------------------------------------------------------------------------
# Mark all read — count verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_all_read_reduces_unread_count_to_zero(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
):
    for i in range(4):
        await _create_notification(db, test_user, title=f"Unread {i}", read=False)
    await db.commit()

    # Confirm there are unread notifications
    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["count"] >= 4

    resp = await client.put("/api/v1/notifications/read-all", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["marked"] is True

    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["count"] == 0


# ---------------------------------------------------------------------------
# Unread count edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unread_count_excludes_already_read(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
):
    await _create_notification(db, test_user, title="Unread", read=False)
    await _create_notification(db, test_user, title="Already read", read=True)
    await db.commit()

    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["count"] == 1


@pytest.mark.asyncio
async def test_unread_count_zero_when_empty(
    client: AsyncClient,
    auth_headers: dict,
):
    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["count"] == 0


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_notifications_filter_by_link(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
):
    await _create_notification(db, test_user, title="Link A", link="/suggestions")
    await _create_notification(db, test_user, title="Link B", link="/suggestions")
    await _create_notification(db, test_user, title="Other", link="/contacts")
    await db.commit()

    resp = await client.get(
        "/api/v1/notifications",
        params={"link": "/suggestions"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 2
    for item in body["data"]:
        assert item["link"] == "/suggestions"


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_notifications_empty_state(
    client: AsyncClient,
    auth_headers: dict,
):
    """A fresh user with no notifications should get an empty list."""
    resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0
    assert body["meta"]["total_pages"] == 1


# ---------------------------------------------------------------------------
# Authentication required (401)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_notifications_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unread_count_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/notifications/unread-count")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mark_all_read_requires_auth(client: AsyncClient):
    resp = await client.put("/api/v1/notifications/read-all")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mark_single_read_requires_auth(client: AsyncClient):
    resp = await client.put(f"/api/v1/notifications/{uuid.uuid4()}/read")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notifications_scoped_to_current_user(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
):
    """Notifications belonging to another user must not appear in the list."""
    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="x",
        full_name="Other User",
    )
    db.add(other_user)
    await db.flush()
    await _create_notification(db, other_user, title="Other user's notification")
    await db.commit()

    resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_mark_read_another_users_notification_returns_404(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
):
    other_user = User(
        id=uuid.uuid4(),
        email="other2@example.com",
        hashed_password="x",
        full_name="Other User 2",
    )
    db.add(other_user)
    await db.flush()
    other_notif = await _create_notification(db, other_user, title="Not yours")
    await db.commit()

    resp = await client.put(
        f"/api/v1/notifications/{other_notif.id}/read",
        headers=auth_headers,
    )
    assert resp.status_code == 404
