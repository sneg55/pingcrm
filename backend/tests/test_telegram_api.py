"""Unit tests for the Telegram authentication and sync API endpoints.

Covers:
- POST /api/v1/auth/telegram/connect   (initiate OTP flow, mocked Telegram client)
- POST /api/v1/auth/telegram/verify    (complete sign-in with OTP code)
- POST /api/v1/contacts/sync/telegram  (trigger chat sync)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token
from app.models.user import User


# ---------------------------------------------------------------------------
# POST /api/v1/auth/telegram/connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_returns_phone_code_hash(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """connect endpoint returns the phone_code_hash produced by connect_telegram."""
    with patch(
        "app.integrations.telegram.connect_telegram",
        new=AsyncMock(return_value="hash_abc123"),
    ):
        response = await client.post(
            "/api/v1/auth/telegram/connect",
            json={"phone": "+15551234567"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["phone_code_hash"] == "hash_abc123"


@pytest.mark.asyncio
async def test_connect_strips_whitespace_from_phone(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """connect endpoint strips leading/trailing whitespace from the phone number."""
    with patch(
        "app.integrations.telegram.connect_telegram",
        new=AsyncMock(return_value="hash_stripped"),
    ) as mock_connect:
        response = await client.post(
            "/api/v1/auth/telegram/connect",
            json={"phone": "  +15551234567  "},
            headers=auth_headers,
        )

    assert response.status_code == 200
    # The phone passed to the integration must be stripped
    call_args = mock_connect.call_args
    assert call_args.args[1] == "+15551234567"


@pytest.mark.asyncio
async def test_connect_missing_phone_returns_422(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """connect endpoint returns 422 when phone field is absent from the body."""
    response = await client.post(
        "/api/v1/auth/telegram/connect",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_connect_empty_phone_returns_422(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """connect endpoint returns 422 when phone is a blank string."""
    response = await client.post(
        "/api/v1/auth/telegram/connect",
        json={"phone": "   "},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_connect_telegram_error_returns_502(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """connect endpoint returns 502 when the Telegram integration raises an exception."""
    with patch(
        "app.integrations.telegram.connect_telegram",
        new=AsyncMock(side_effect=RuntimeError("Telegram service unavailable")),
    ):
        response = await client.post(
            "/api/v1/auth/telegram/connect",
            json={"phone": "+15551234567"},
            headers=auth_headers,
        )

    assert response.status_code == 502
    assert "Failed to send Telegram OTP" in response.json()["detail"]


@pytest.mark.asyncio
async def test_connect_requires_auth(client: AsyncClient):
    """connect endpoint returns 401 without auth headers."""
    response = await client.post(
        "/api/v1/auth/telegram/connect",
        json={"phone": "+15551234567"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/auth/telegram/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_returns_connected_true(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """verify endpoint returns connected:True on successful OTP verification."""
    with patch(
        "app.integrations.telegram.verify_telegram",
        new=AsyncMock(return_value=None),
    ):
        response = await client.post(
            "/api/v1/auth/telegram/verify",
            json={
                "phone": "+15551234567",
                "code": "12345",
                "phone_code_hash": "hash_abc123",
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["connected"] is True


@pytest.mark.asyncio
async def test_verify_passes_correct_args_to_integration(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """verify endpoint passes stripped phone and code to verify_telegram."""
    with patch(
        "app.integrations.telegram.verify_telegram",
        new=AsyncMock(return_value=None),
    ) as mock_verify:
        await client.post(
            "/api/v1/auth/telegram/verify",
            json={
                "phone": " +15551234567 ",
                "code": " 99999 ",
                "phone_code_hash": "myhash",
            },
            headers=auth_headers,
        )

    call_args = mock_verify.call_args
    # positional args: (current_user, phone, code, phone_code_hash, db)
    assert call_args.args[1] == "+15551234567"
    assert call_args.args[2] == "99999"
    assert call_args.args[3] == "myhash"


@pytest.mark.asyncio
async def test_verify_missing_fields_returns_422(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """verify endpoint returns 422 when required fields are missing from the body."""
    response = await client.post(
        "/api/v1/auth/telegram/verify",
        json={"phone": "+15551234567"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_verify_telegram_error_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """verify endpoint returns 400 when the Telegram integration raises an exception."""
    with patch(
        "app.integrations.telegram.verify_telegram",
        new=AsyncMock(side_effect=ValueError("Invalid OTP code")),
    ):
        response = await client.post(
            "/api/v1/auth/telegram/verify",
            json={
                "phone": "+15551234567",
                "code": "00000",
                "phone_code_hash": "badhash",
            },
            headers=auth_headers,
        )

    assert response.status_code == 400
    assert "Telegram verification failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_verify_requires_auth(client: AsyncClient):
    """verify endpoint returns 401 without auth headers."""
    response = await client.post(
        "/api/v1/auth/telegram/verify",
        json={
            "phone": "+15551234567",
            "code": "12345",
            "phone_code_hash": "abc",
        },
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/contacts/sync/telegram
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_telegram_dispatches_task(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """sync endpoint dispatches a Celery task and returns immediately."""
    test_user.telegram_session = "serialised_session_string"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.tasks.sync_telegram_for_user") as mock_task:
        mock_task.delay.return_value = None
        response = await client.post(
            "/api/v1/contacts/sync/telegram",
            headers=headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["status"] == "started"
    mock_task.delay.assert_called_once_with(str(test_user.id))


@pytest.mark.asyncio
async def test_common_groups_without_session_returns_empty(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_user: User,
):
    """common-groups endpoint returns empty list when user has no telegram session."""
    from app.models.contact import Contact

    contact = Contact(user_id=test_user.id, full_name="Test", telegram_username="test_user")
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    response = await client.get(
        f"/api/v1/contacts/{contact.id}/telegram/common-groups",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_common_groups_without_telegram_username(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """common-groups endpoint returns empty list when contact has no telegram username."""
    from app.models.contact import Contact

    test_user.telegram_session = "session_string"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    contact = Contact(user_id=test_user.id, full_name="No TG")
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    response = await client.get(
        f"/api/v1/contacts/{contact.id}/telegram/common-groups",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_common_groups_contact_not_found(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """common-groups endpoint returns 404 for non-existent contact."""
    test_user.telegram_session = "session_string"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(
        f"/api/v1/contacts/{uuid.uuid4()}/telegram/common-groups",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_common_groups_requires_auth(client: AsyncClient):
    """common-groups endpoint returns 401 without auth."""
    response = await client.get(
        f"/api/v1/contacts/{uuid.uuid4()}/telegram/common-groups",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sync_telegram_without_session_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """sync endpoint returns 400 when the user has no telegram_session."""
    # test_user has telegram_session=None by default
    response = await client.post(
        "/api/v1/contacts/sync/telegram",
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "not connected" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_sync_telegram_dispatches_even_with_valid_session(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """sync endpoint dispatches task as long as telegram_session is set."""
    test_user.telegram_session = "valid_session"
    db.add(test_user)
    await db.commit()

    token = create_access_token(data={"sub": str(test_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.tasks.sync_telegram_for_user") as mock_task:
        mock_task.delay.return_value = None
        response = await client.post(
            "/api/v1/contacts/sync/telegram",
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "started"


@pytest.mark.asyncio
async def test_sync_telegram_requires_auth(client: AsyncClient):
    """sync endpoint returns 401 without auth headers."""
    response = await client.post("/api/v1/contacts/sync/telegram")
    assert response.status_code == 401
