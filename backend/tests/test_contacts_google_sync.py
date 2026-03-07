"""Tests for Google Contacts sync endpoint (background dispatch)."""
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.models.user import User


@pytest.mark.asyncio
async def test_google_sync_not_connected(client: AsyncClient, auth_headers: dict):
    """POST /contacts/sync/google returns 400 when Google not connected."""
    resp = await client.post("/api/v1/contacts/sync/google", headers=auth_headers)
    assert resp.status_code == 400
    detail = resp.json()["detail"].lower()
    assert "not connected" in detail or "no google account" in detail


@pytest.mark.asyncio
async def test_google_sync_dispatches_task(
    client: AsyncClient, db: AsyncSession, test_user: User
):
    """POST /contacts/sync/google dispatches a Celery task and returns immediately."""
    test_user.google_refresh_token = "valid_token"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.tasks.sync_google_contacts_for_user") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post("/api/v1/contacts/sync/google", headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "started"
    mock_task.delay.assert_called_once_with(str(test_user.id))


@pytest.mark.asyncio
async def test_google_calendar_sync_dispatches_task(
    client: AsyncClient, db: AsyncSession, test_user: User
):
    """POST /contacts/sync/google-calendar dispatches a Celery task."""
    test_user.google_refresh_token = "valid_token"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.tasks.sync_google_calendar_for_user") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post("/api/v1/contacts/sync/google-calendar", headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "started"
    mock_task.delay.assert_called_once_with(str(test_user.id))


@pytest.mark.asyncio
async def test_twitter_sync_dispatches_task(
    client: AsyncClient, db: AsyncSession, test_user: User
):
    """POST /contacts/sync/twitter dispatches a Celery task."""
    test_user.twitter_access_token = "valid_token"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.tasks.sync_twitter_dms_for_user") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post("/api/v1/contacts/sync/twitter", headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "started"
    mock_task.delay.assert_called_once_with(str(test_user.id))
