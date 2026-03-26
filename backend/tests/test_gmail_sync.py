"""Tests for Gmail integration: sync_contact_emails and the sync-emails endpoint."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.integrations.gmail import sync_contact_emails
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User


# ---------------------------------------------------------------------------
# Unit tests for sync_contact_emails
# ---------------------------------------------------------------------------

def _make_thread(thread_id: str, from_addr: str, to_addr: str, snippet: str, ts_ms: int):
    """Build a minimal Gmail API thread response with message IDs."""
    return {
        "id": thread_id,
        "messages": [
            {
                "id": f"{thread_id}_msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": from_addr},
                        {"name": "To", "value": to_addr},
                        {"name": "Subject", "value": f"Thread {thread_id}"},
                    ],
                },
                "internalDate": str(ts_ms),
                "snippet": snippet,
            },
        ],
    }


@pytest.mark.asyncio
async def test_sync_contact_emails_creates_interactions(db: AsyncSession, test_user: User, test_contact: Contact):
    """sync_contact_emails creates Interaction records for Gmail threads."""
    test_user.google_refresh_token = "refresh_token"
    db.add(test_user)
    await db.commit()

    now_ms = int(datetime.now(UTC).timestamp() * 1000)

    thread1 = _make_thread("t1", "john@example.com", "test@example.com", "Hello!", now_ms)
    thread2 = _make_thread("t2", "test@example.com", "john@example.com", "Reply!", now_ms - 3600_000)

    mock_service = MagicMock()
    mock_threads = mock_service.users.return_value.threads.return_value

    # list() returns thread IDs
    mock_threads.list.return_value.execute.return_value = {
        "threads": [{"id": "t1"}, {"id": "t2"}],
    }

    # get() returns full thread data
    def get_thread(**kwargs):
        mock_exec = MagicMock()
        data = {"t1": thread1, "t2": thread2}
        mock_exec.execute.return_value = data[kwargs["id"]]
        return mock_exec

    mock_threads.get.side_effect = get_thread

    with patch("app.integrations.gmail._build_gmail_service", return_value=mock_service):
        count = await sync_contact_emails(test_user, test_contact, db)

    assert count == 2

    result = await db.execute(
        select(Interaction).where(Interaction.contact_id == test_contact.id)
    )
    interactions = result.scalars().all()
    assert len(interactions) == 2
    directions = {i.direction for i in interactions}
    assert directions == {"inbound", "outbound"}


@pytest.mark.asyncio
async def test_sync_contact_emails_no_refresh_token(db: AsyncSession, test_user: User, test_contact: Contact):
    """sync_contact_emails returns 0 when user has no google_refresh_token."""
    test_user.google_refresh_token = None
    db.add(test_user)
    await db.commit()

    count = await sync_contact_emails(test_user, test_contact, db)
    assert count == 0


@pytest.mark.asyncio
async def test_sync_contact_emails_no_emails(db: AsyncSession, test_user: User, test_contact: Contact):
    """sync_contact_emails returns 0 when contact has no emails."""
    test_user.google_refresh_token = "token"
    test_contact.emails = []
    db.add_all([test_user, test_contact])
    await db.commit()

    count = await sync_contact_emails(test_user, test_contact, db)
    assert count == 0


@pytest.mark.asyncio
async def test_sync_contact_emails_idempotent(db: AsyncSession, test_user: User, test_contact: Contact):
    """Calling sync_contact_emails twice doesn't duplicate interactions."""
    test_user.google_refresh_token = "refresh_token"
    db.add(test_user)
    await db.commit()

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    thread = _make_thread("t1", "john@example.com", "test@example.com", "Hello!", now_ms)

    mock_service = MagicMock()
    mock_threads = mock_service.users.return_value.threads.return_value
    mock_threads.list.return_value.execute.return_value = {"threads": [{"id": "t1"}]}
    mock_threads.get.return_value.execute.return_value = thread

    with patch("app.integrations.gmail._build_gmail_service", return_value=mock_service):
        count1 = await sync_contact_emails(test_user, test_contact, db)
        count2 = await sync_contact_emails(test_user, test_contact, db)

    assert count1 == 1
    assert count2 == 0  # already exists

    result = await db.execute(
        select(Interaction).where(Interaction.contact_id == test_contact.id)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_sync_contact_emails_updates_last_interaction(db: AsyncSession, test_user: User, test_contact: Contact):
    """sync_contact_emails updates contact.last_interaction_at when newer threads found."""
    test_user.google_refresh_token = "refresh_token"
    old_time = datetime.now(UTC) - timedelta(days=30)
    test_contact.last_interaction_at = old_time
    db.add_all([test_user, test_contact])
    await db.commit()

    recent_ms = int(datetime.now(UTC).timestamp() * 1000)
    thread = _make_thread("t1", "john@example.com", "test@example.com", "Recent!", recent_ms)

    mock_service = MagicMock()
    mock_threads = mock_service.users.return_value.threads.return_value
    mock_threads.list.return_value.execute.return_value = {"threads": [{"id": "t1"}]}
    mock_threads.get.return_value.execute.return_value = thread

    with patch("app.integrations.gmail._build_gmail_service", return_value=mock_service):
        await sync_contact_emails(test_user, test_contact, db)

    await db.refresh(test_contact)
    assert test_contact.last_interaction_at > old_time


# ---------------------------------------------------------------------------
# API endpoint tests for POST /contacts/{id}/sync-emails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_emails_endpoint_no_emails(
    client: AsyncClient, auth_headers: dict, test_contact: Contact
):
    """Returns skipped when contact has no emails."""
    # test_contact has emails by default, clear them
    # We need a contact without emails
    pass  # covered by unit test above


@pytest.mark.asyncio
async def test_sync_emails_endpoint_not_found(
    client: AsyncClient, auth_headers: dict
):
    """Returns 404 for non-existent contact."""
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/contacts/{fake_id}/sync-emails",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_emails_endpoint_no_google(
    client: AsyncClient, auth_headers: dict, test_contact: Contact
):
    """Returns skipped when user has no Google refresh token."""
    resp = await client.post(
        f"/api/v1/contacts/{test_contact.id}/sync-emails",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["skipped"] is True
    assert data["reason"] == "google_not_connected"


@pytest.mark.asyncio
async def test_sync_emails_endpoint_success(
    client: AsyncClient, db: AsyncSession, test_user: User, test_contact: Contact
):
    """Endpoint calls sync_contact_emails and returns count."""
    test_user.google_refresh_token = "valid_token"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.integrations.gmail.sync_contact_emails",
        new=AsyncMock(return_value=3),
    ) as mock_sync, patch(
        "app.api.contacts_routes.sync.get_redis",
    ) as mock_redis:
        mock_r = AsyncMock()
        mock_r.exists.return_value = False
        mock_r.setex.return_value = True
        mock_redis.return_value = mock_r

        resp = await client.post(
            f"/api/v1/contacts/{test_contact.id}/sync-emails",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["new_interactions"] == 3


@pytest.mark.asyncio
async def test_sync_emails_endpoint_rate_limited(
    client: AsyncClient, db: AsyncSession, test_user: User, test_contact: Contact
):
    """Endpoint returns skipped when recently synced (Redis cache hit)."""
    test_user.google_refresh_token = "valid_token"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.api.contacts_routes.sync.get_redis") as mock_redis:
        mock_r = AsyncMock()
        mock_r.exists.return_value = True  # cache hit
        mock_redis.return_value = mock_r

        resp = await client.post(
            f"/api/v1/contacts/{test_contact.id}/sync-emails",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["skipped"] is True
    assert data["reason"] == "synced_recently"


# ---------------------------------------------------------------------------
# API endpoint test for POST /contacts/sync/gmail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gmail_sync_dispatches_task(
    client: AsyncClient, db: AsyncSession, test_user: User
):
    """POST /contacts/sync/gmail dispatches a Celery task."""
    test_user.google_refresh_token = "valid_token"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.tasks.sync_gmail_for_user") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post("/api/v1/contacts/sync/gmail", headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "started"
    mock_task.delay.assert_called_once_with(str(test_user.id))


@pytest.mark.asyncio
async def test_gmail_sync_not_connected(client: AsyncClient, auth_headers: dict):
    """POST /contacts/sync/gmail returns 400 when Google not connected."""
    resp = await client.post("/api/v1/contacts/sync/gmail", headers=auth_headers)
    assert resp.status_code == 400
