"""Tests for suggestions API endpoints.

Consolidated from test_suggestions_api.py, test_suggestions_extended.py,
and test_suggestions_api_extended2.py.

Covers:
- POST /api/v1/suggestions/generate  (mocked followup_engine)
- GET  /api/v1/suggestions            (list pending)
- GET  /api/v1/suggestions/digest     (mocked followup_engine)
- PUT  /api/v1/suggestions/{id}       (status transitions, edits)
- POST /api/v1/suggestions/{id}/regenerate  (AI message regeneration)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.user import User


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_suggestion(
    contact: Contact,
    user: User,
    *,
    status: str = "pending",
    pool: str | None = None,
    message: str = "Hey!",
    channel: str = "email",
) -> FollowUpSuggestion:
    return FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user.id,
        trigger_type="time_based",
        suggested_message=message,
        suggested_channel=channel,
        status=status,
        pool=pool,
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Generate — POST /api/v1/suggestions/generate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_generated_suggestions(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_contact: Contact,
    test_user: User,
):
    """generate endpoint returns suggestions produced by the engine."""
    mock_suggestions = [
        FollowUpSuggestion(
            id=uuid.uuid4(),
            contact_id=test_contact.id,
            user_id=test_user.id,
            trigger_type="time_based",
            suggested_message="Reach out to John Doe",
            suggested_channel="email",
            status="pending",
            created_at=datetime.now(UTC),
        )
    ]

    with patch(
        "app.services.followup_engine.generate_suggestions",
        new=AsyncMock(return_value=mock_suggestions),
    ) as mock_generate:
        response = await client.post(
            "/api/v1/suggestions/generate",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["generated"] == 1
    assert len(body["data"]) == 1
    mock_generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_returns_empty_when_no_suggestions(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """generate endpoint returns empty list when engine produces nothing."""
    with patch(
        "app.services.followup_engine.generate_suggestions",
        new=AsyncMock(return_value=[]),
    ):
        response = await client.post(
            "/api/v1/suggestions/generate",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["generated"] == 0


@pytest.mark.asyncio
async def test_generate_requires_auth(client: AsyncClient):
    """generate endpoint returns 401 without auth headers."""
    response = await client.post("/api/v1/suggestions/generate")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_multiple_suggestions(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_contact: Contact,
    test_user: User,
):
    """generate endpoint handles multiple suggestions from the engine."""
    mock_suggestions = [
        FollowUpSuggestion(
            id=uuid.uuid4(),
            contact_id=test_contact.id,
            user_id=test_user.id,
            trigger_type="time_based",
            suggested_message=f"Message {i}",
            suggested_channel="email",
            status="pending",
            created_at=datetime.now(UTC),
        )
        for i in range(3)
    ]

    with patch(
        "app.services.followup_engine.generate_suggestions",
        new=AsyncMock(return_value=mock_suggestions),
    ):
        response = await client.post(
            "/api/v1/suggestions/generate",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["generated"] == 3
    assert len(body["data"]) == 3


@pytest.mark.asyncio
async def test_generate_recalculates_scores_when_all_zero(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_contact: Contact,
    test_user: User,
) -> None:
    """POST /generate runs calculate_score for each scorable contact when all scores are 0."""
    test_contact.relationship_score = 0
    db.add(test_contact)
    await db.commit()

    mock_calculate = AsyncMock()
    with patch(
        "app.services.scoring.calculate_score",
        new=mock_calculate,
    ), patch(
        "app.services.followup_engine.generate_suggestions",
        new=AsyncMock(return_value=[]),
    ):
        response = await client.post(
            "/api/v1/suggestions/generate",
            headers=auth_headers,
        )

    assert response.status_code == 200
    mock_calculate.assert_awaited()


# ---------------------------------------------------------------------------
# List — GET /api/v1/suggestions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_suggestions_returns_pending(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """list endpoint returns pending suggestions with contact info attached."""
    response = await client.get("/api/v1/suggestions", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["count"] == 1
    items = body["data"]
    assert len(items) == 1
    assert items[0]["status"] == "pending"
    assert items[0]["contact"] is not None
    assert items[0]["contact"]["full_name"] == "John Doe"


@pytest.mark.asyncio
async def test_list_suggestions_empty_for_new_user(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """list endpoint returns empty list when user has no pending suggestions."""
    response = await client.get("/api/v1/suggestions", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["count"] == 0


@pytest.mark.asyncio
async def test_list_suggestions_excludes_non_pending(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_contact: Contact,
    test_user: User,
):
    """list endpoint only returns suggestions with status=pending."""
    sent_suggestion = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="Already sent",
        suggested_channel="email",
        status="sent",
        created_at=datetime.now(UTC),
    )
    db.add(sent_suggestion)
    await db.commit()

    response = await client.get("/api/v1/suggestions", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["count"] == 0


@pytest.mark.asyncio
async def test_list_suggestions_requires_auth(client: AsyncClient):
    """list endpoint returns 401 without auth headers."""
    response = await client.get("/api/v1/suggestions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_excludes_second_tier_contacts(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_user: User,
) -> None:
    """GET /suggestions excludes suggestions for contacts tagged '2nd tier'."""
    second_tier_contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Low Priority Person",
        emails=["lowpri@example.com"],
        relationship_score=3,
        source="manual",
        tags=["2nd tier"],
    )
    db.add(second_tier_contact)
    await db.commit()
    await db.refresh(second_tier_contact)

    suggestion = _make_suggestion(second_tier_contact, test_user, message="Should be filtered")
    db.add(suggestion)
    await db.commit()

    response = await client.get("/api/v1/suggestions", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    contact_ids_in_response = [item["contact_id"] for item in body["data"]]
    assert str(second_tier_contact.id) not in contact_ids_in_response


@pytest.mark.asyncio
async def test_list_excludes_unreachable_contacts(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_user: User,
) -> None:
    """GET /suggestions excludes suggestions for contacts with no emails, Telegram, Twitter, or LinkedIn."""
    unreachable_contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Ghost Person",
        emails=[],
        relationship_score=4,
        source="manual",
    )
    db.add(unreachable_contact)
    await db.commit()
    await db.refresh(unreachable_contact)

    suggestion = _make_suggestion(unreachable_contact, test_user, message="Unreachable draft")
    db.add(suggestion)
    await db.commit()

    response = await client.get("/api/v1/suggestions", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    contact_ids_in_response = [item["contact_id"] for item in body["data"]]
    assert str(unreachable_contact.id) not in contact_ids_in_response


# ---------------------------------------------------------------------------
# Digest — GET /api/v1/suggestions/digest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_digest_returns_weekly_suggestions(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_contact: Contact,
    test_user: User,
):
    """digest endpoint returns suggestions from get_weekly_digest."""
    mock_suggestions = [
        FollowUpSuggestion(
            id=uuid.uuid4(),
            contact_id=test_contact.id,
            user_id=test_user.id,
            trigger_type="time_based",
            suggested_message="Weekly check-in with John",
            suggested_channel="email",
            status="pending",
            created_at=datetime.now(UTC),
        )
    ]

    with patch(
        "app.services.followup_engine.get_weekly_digest",
        new=AsyncMock(return_value=mock_suggestions),
    ):
        response = await client.get("/api/v1/suggestions/digest", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["count"] == 1
    assert len(body["data"]) == 1


@pytest.mark.asyncio
async def test_digest_empty_result(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """digest endpoint returns empty list when no digest suggestions."""
    with patch(
        "app.services.followup_engine.get_weekly_digest",
        new=AsyncMock(return_value=[]),
    ):
        response = await client.get("/api/v1/suggestions/digest", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["count"] == 0


# ---------------------------------------------------------------------------
# Update — PUT /api/v1/suggestions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_suggestion_status_dismissed(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """PUT endpoint can dismiss a suggestion."""
    response = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={"status": "dismissed"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["status"] == "dismissed"


@pytest.mark.asyncio
async def test_update_suggestion_status_sent(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """PUT endpoint marks suggestion as sent and updates contact timestamp."""
    response = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={"status": "sent"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "sent"


@pytest.mark.asyncio
async def test_mark_sent_removes_from_pending_list(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_suggestion: FollowUpSuggestion,
    test_contact: Contact,
) -> None:
    """PUT /suggestions/{id} with status=sent removes it from the pending list.

    Verifies the DB write took effect by checking the list endpoint before and after.
    """
    list_before = await client.get("/api/v1/suggestions", headers=auth_headers)
    assert any(
        item["id"] == str(test_suggestion.id)
        for item in list_before.json()["data"]
    ), "Suggestion should appear in pending list before marking sent"

    response = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={"status": "sent"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "sent"

    list_after = await client.get("/api/v1/suggestions", headers=auth_headers)
    pending_ids = [item["id"] for item in list_after.json()["data"]]
    assert str(test_suggestion.id) not in pending_ids, (
        "Suggestion marked as sent must not appear in the pending suggestions list"
    )


@pytest.mark.asyncio
async def test_update_suggestion_status_snoozed_with_datetime(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """PUT endpoint accepts snoozed status when snooze_until is provided."""
    snooze_until = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    response = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={"status": "snoozed", "snooze_until": snooze_until},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "snoozed"


@pytest.mark.asyncio
async def test_snooze_via_scheduled_for_field(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
) -> None:
    """PUT /suggestions/{id} accepts scheduled_for as the snooze datetime."""
    future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    response = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={"status": "snoozed", "scheduled_for": future},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "snoozed"
    assert body["data"]["scheduled_for"] is not None


@pytest.mark.asyncio
async def test_update_suggestion_snoozed_without_datetime_returns_422(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """PUT endpoint returns 422 when snoozed status is missing snooze_until."""
    response = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={"status": "snoozed"},
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reactivate_snoozed_suggestion_to_pending(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_contact: Contact,
    test_user: User,
) -> None:
    """PUT /suggestions/{id} with status=pending reactivates a snoozed suggestion."""
    snoozed = _make_suggestion(test_contact, test_user, status="snoozed")
    snoozed.scheduled_for = datetime.now(UTC) - timedelta(hours=1)
    db.add(snoozed)
    await db.commit()
    await db.refresh(snoozed)

    response = await client.put(
        f"/api/v1/suggestions/{snoozed.id}",
        json={"status": "pending"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_update_suggestion_invalid_status(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """PUT endpoint returns 400 for an unrecognized status value."""
    response = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={"status": "invalid_status"},
        headers=auth_headers,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_suggestion_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """PUT endpoint returns 404 when suggestion does not exist."""
    non_existent_id = uuid.uuid4()
    response = await client.put(
        f"/api/v1/suggestions/{non_existent_id}",
        json={"status": "dismissed"},
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_suggestion_requires_auth(
    client: AsyncClient,
    test_suggestion: FollowUpSuggestion,
):
    """PUT endpoint returns 401 without auth headers."""
    response = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={"status": "dismissed"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_suggestion_cannot_access_other_users_suggestion(
    client: AsyncClient,
    db: AsyncSession,
    test_contact: Contact,
):
    """PUT endpoint returns 404 when accessing another user's suggestion."""
    from app.core.auth import create_access_token, hash_password

    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password=hash_password("otherpass123"),
        full_name="Other User",
    )
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    other_suggestion = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=other_user.id,
        trigger_type="time_based",
        suggested_message="Other user's suggestion",
        suggested_channel="email",
        status="pending",
        created_at=datetime.now(UTC),
    )
    db.add(other_suggestion)
    await db.commit()

    first_user = User(
        id=uuid.uuid4(),
        email="first@example.com",
        hashed_password=hash_password("firstpass123"),
        full_name="First User",
    )
    db.add(first_user)
    await db.commit()
    first_token = create_access_token(data={"sub": str(first_user.id)})
    first_headers = {"Authorization": f"Bearer {first_token}"}

    response = await client.put(
        f"/api/v1/suggestions/{other_suggestion.id}",
        json={"status": "dismissed"},
        headers=first_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_suggestion_persists_edited_message(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """PUT /suggestions/{id} persists an edited message and channel."""
    resp = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={
            "status": "sent",
            "suggested_message": "Edited draft for John",
            "suggested_channel": "telegram",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["suggested_message"] == "Edited draft for John"
    assert data["suggested_channel"] == "telegram"


@pytest.mark.asyncio
async def test_update_suggestion_partial_message_only(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """PUT /suggestions/{id} can update just the message without changing channel."""
    original_channel = test_suggestion.suggested_channel
    resp = await client.put(
        f"/api/v1/suggestions/{test_suggestion.id}",
        json={
            "status": "pending",
            "suggested_message": "Only message changed",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["suggested_message"] == "Only message changed"
    assert data["suggested_channel"] == original_channel


# ---------------------------------------------------------------------------
# Regenerate — POST /api/v1/suggestions/{id}/regenerate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_suggestion(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """POST /suggestions/{id}/regenerate returns a new AI-generated message."""
    with patch(
        "app.services.message_composer.compose_followup_message",
        new=AsyncMock(return_value="Fresh AI-generated message"),
    ):
        resp = await client.post(
            f"/api/v1/suggestions/{test_suggestion.id}/regenerate",
            json={"channel": "telegram"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["suggested_message"] == "Fresh AI-generated message"
    assert data["suggested_channel"] == "telegram"


@pytest.mark.asyncio
async def test_regenerate_suggestion_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """POST /suggestions/{id}/regenerate returns 404 for unknown suggestion."""
    resp = await client.post(
        f"/api/v1/suggestions/{uuid.uuid4()}/regenerate",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_suggestion_uses_existing_channel(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
):
    """POST /suggestions/{id}/regenerate falls back to existing channel when none specified."""
    with patch(
        "app.services.message_composer.compose_followup_message",
        new=AsyncMock(return_value="Regenerated with default channel"),
    ):
        resp = await client.post(
            f"/api/v1/suggestions/{test_suggestion.id}/regenerate",
            json={},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["suggested_channel"] == test_suggestion.suggested_channel


@pytest.mark.asyncio
async def test_regenerate_pool_b_sets_revival_context(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_contact: Contact,
    test_user: User,
) -> None:
    """POST /suggestions/{id}/regenerate passes revival_context=True for pool-B suggestions."""
    pool_b_suggestion = _make_suggestion(test_contact, test_user, pool="B")
    db.add(pool_b_suggestion)
    await db.commit()
    await db.refresh(pool_b_suggestion)

    mock_compose = AsyncMock(return_value="Revival message for John")
    with patch("app.services.message_composer.compose_followup_message", new=mock_compose):
        response = await client.post(
            f"/api/v1/suggestions/{pool_b_suggestion.id}/regenerate",
            json={},
            headers=auth_headers,
        )

    assert response.status_code == 200
    mock_compose.assert_awaited_once_with(
        contact_id=test_contact.id,
        trigger_type=ANY,
        event_summary=None,
        db=ANY,
        revival_context=True,
    )


@pytest.mark.asyncio
async def test_regenerate_persists_new_message_in_db(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_suggestion: FollowUpSuggestion,
) -> None:
    """POST /suggestions/{id}/regenerate stores the returned message, confirmed via response."""
    with patch(
        "app.services.message_composer.compose_followup_message",
        new=AsyncMock(return_value="Persisted AI draft"),
    ):
        response = await client.post(
            f"/api/v1/suggestions/{test_suggestion.id}/regenerate",
            json={},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["suggested_message"] == "Persisted AI draft"

    # A second regenerate call should still return the updated message
    with patch(
        "app.services.message_composer.compose_followup_message",
        new=AsyncMock(return_value="Second draft"),
    ):
        response2 = await client.post(
            f"/api/v1/suggestions/{test_suggestion.id}/regenerate",
            json={},
            headers=auth_headers,
        )
    assert response2.status_code == 200
    assert response2.json()["data"]["suggested_message"] == "Second draft"
