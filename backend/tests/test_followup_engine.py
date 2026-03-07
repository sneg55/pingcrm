"""Unit tests for the follow-up engine service."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.detected_event import DetectedEvent
from app.models.follow_up import FollowUpSuggestion
from app.services.followup_engine import (
    MAX_SUGGESTIONS_PER_RUN,
    generate_suggestions,
    get_weekly_digest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_MESSAGE = "Hey, just checking in!"


def _patch_compose():
    """Return a context-manager that mocks compose_followup_message."""
    return patch(
        "app.services.followup_engine.compose_followup_message",
        new_callable=AsyncMock,
        return_value=MOCK_MESSAGE,
    )


# ---------------------------------------------------------------------------
# _get_best_channel — tested indirectly through generate_suggestions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_best_channel_falls_back_to_email(
    db: AsyncSession, test_user, test_contact
):
    """When a contact has no recent interactions the channel should default to 'email'."""
    test_contact.relationship_score = 3
    test_contact.last_interaction_at = datetime.now(UTC) - timedelta(days=200)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    time_based = [s for s in suggestions if s.trigger_type == "time_based"]
    assert len(time_based) == 1
    assert time_based[0].suggested_channel == "email"


@pytest.mark.asyncio
async def test_get_best_channel_uses_last_interaction_platform(
    db: AsyncSession, test_user, test_contact, test_interaction
):
    """Channel should match the platform of the most recent interaction."""
    # test_interaction.platform == "email"
    test_contact.relationship_score = 2
    test_contact.last_interaction_at = datetime.now(UTC) - timedelta(days=100)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    time_based = [s for s in suggestions if s.trigger_type == "time_based"]
    assert len(time_based) >= 1
    assert time_based[0].suggested_channel == "email"


# ---------------------------------------------------------------------------
# generate_suggestions — time-based trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestions_time_based_created(
    db: AsyncSession, test_user, test_contact
):
    """Low score + no recent interaction creates a time_based suggestion."""
    test_contact.relationship_score = 2
    test_contact.last_interaction_at = datetime.now(UTC) - timedelta(days=100)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.trigger_type == "time_based"
    assert s.user_id == test_user.id
    assert s.contact_id == test_contact.id
    assert s.status == "pending"
    assert s.suggested_message == MOCK_MESSAGE


@pytest.mark.asyncio
async def test_generate_suggestions_time_based_null_last_interaction(
    db: AsyncSession, test_user, test_contact
):
    """last_interaction_at=None should NOT qualify (no previous interactions)."""
    test_contact.relationship_score = 1
    test_contact.last_interaction_at = None
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.trigger_type == "time_based" for s in suggestions)


@pytest.mark.asyncio
async def test_generate_suggestions_time_based_skipped_high_score(
    db: AsyncSession, test_user, test_contact
):
    """relationship_score >= 4 should NOT trigger a time_based suggestion."""
    test_contact.relationship_score = 5
    test_contact.last_interaction_at = datetime.now(UTC) - timedelta(days=100)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.trigger_type == "time_based" for s in suggestions)


@pytest.mark.asyncio
async def test_generate_suggestions_time_based_skipped_recent_interaction(
    db: AsyncSession, test_user, test_contact
):
    """A contact with a recent interaction should NOT trigger time_based."""
    test_contact.relationship_score = 2
    test_contact.last_interaction_at = datetime.now(UTC) - timedelta(days=10)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.trigger_type == "time_based" for s in suggestions)


# ---------------------------------------------------------------------------
# generate_suggestions — event-based trigger
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="function")
async def test_detected_event(db: AsyncSession, test_contact) -> DetectedEvent:
    """High-confidence event within the 7-day window."""
    event = DetectedEvent(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        event_type="job_change",
        confidence=0.9,
        summary="John Doe started a new role at TechCorp",
        detected_at=datetime.now(UTC) - timedelta(days=2),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@pytest.mark.asyncio
async def test_generate_suggestions_event_based_created(
    db: AsyncSession, test_user, test_contact, test_detected_event
):
    """A high-confidence recent event should trigger an event_based suggestion."""
    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    event_based = [s for s in suggestions if s.trigger_type == "event_based"]
    assert len(event_based) == 1
    s = event_based[0]
    assert s.trigger_event_id == test_detected_event.id
    assert s.contact_id == test_contact.id
    assert s.status == "pending"


@pytest.mark.asyncio
async def test_generate_suggestions_event_based_low_confidence_skipped(
    db: AsyncSession, test_user, test_contact
):
    """confidence <= 0.7 should NOT create a suggestion."""
    event = DetectedEvent(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        event_type="job_change",
        confidence=0.65,
        summary="Maybe changed jobs?",
        detected_at=datetime.now(UTC) - timedelta(days=2),
    )
    db.add(event)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.trigger_type == "event_based" for s in suggestions)


@pytest.mark.asyncio
async def test_generate_suggestions_event_based_old_event_skipped(
    db: AsyncSession, test_user, test_contact
):
    """An event older than 7 days should NOT create a suggestion."""
    event = DetectedEvent(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        event_type="funding_round",
        confidence=0.95,
        summary="Raised Series A",
        detected_at=datetime.now(UTC) - timedelta(days=10),
    )
    db.add(event)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.trigger_type == "event_based" for s in suggestions)


@pytest.mark.asyncio
async def test_generate_suggestions_event_based_boundary_confidence(
    db: AsyncSession, test_user, test_contact
):
    """An event with confidence exactly equal to EVENT_CONFIDENCE_THRESHOLD (0.7) is excluded."""
    event = DetectedEvent(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        event_type="promotion",
        confidence=0.7,  # not > 0.7
        summary="Got promoted",
        detected_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.add(event)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.trigger_type == "event_based" for s in suggestions)


# ---------------------------------------------------------------------------
# generate_suggestions — scheduled trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestions_scheduled_created(
    db: AsyncSession, test_user, test_contact
):
    """last_followup_at older than 30 days triggers a scheduled suggestion."""
    test_contact.last_followup_at = datetime.now(UTC) - timedelta(days=35)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    scheduled = [s for s in suggestions if s.trigger_type == "scheduled"]
    assert len(scheduled) == 1
    assert scheduled[0].contact_id == test_contact.id


@pytest.mark.asyncio
async def test_generate_suggestions_scheduled_skipped_recent_followup(
    db: AsyncSession, test_user, test_contact
):
    """A contact followed up within 30 days should NOT trigger scheduled."""
    test_contact.last_followup_at = datetime.now(UTC) - timedelta(days=10)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.trigger_type == "scheduled" for s in suggestions)


@pytest.mark.asyncio
async def test_generate_suggestions_scheduled_skipped_null_followup(
    db: AsyncSession, test_user, test_contact
):
    """last_followup_at=None should NOT trigger scheduled (isnot filter)."""
    test_contact.last_followup_at = None
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.trigger_type == "scheduled" for s in suggestions)


# ---------------------------------------------------------------------------
# generate_suggestions — deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestions_no_duplicate_per_contact(
    db: AsyncSession, test_user, test_contact
):
    """A contact matching multiple triggers should appear at most once."""
    test_contact.relationship_score = 2
    test_contact.last_interaction_at = datetime.now(UTC) - timedelta(days=100)
    test_contact.last_followup_at = datetime.now(UTC) - timedelta(days=40)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    contact_ids = [s.contact_id for s in suggestions]
    assert len(contact_ids) == len(set(contact_ids)), "Duplicate contact_id in suggestions"


# ---------------------------------------------------------------------------
# generate_suggestions — MAX_SUGGESTIONS_PER_RUN cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestions_respects_max_cap(db: AsyncSession, test_user):
    """generate_suggestions should not return more than MAX_SUGGESTIONS_PER_RUN items."""
    for i in range(MAX_SUGGESTIONS_PER_RUN + 3):
        contact = Contact(
            id=uuid.uuid4(),
            user_id=test_user.id,
            full_name=f"Contact {i}",
            given_name=f"Contact{i}",
            relationship_score=1,
            last_interaction_at=datetime.now(UTC) - timedelta(days=100),
            source="manual",
        )
        db.add(contact)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert len(suggestions) <= MAX_SUGGESTIONS_PER_RUN


# ---------------------------------------------------------------------------
# generate_suggestions — no qualifying contacts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestions_no_qualifying_contacts(db: AsyncSession, test_user):
    """When no contacts qualify, an empty list is returned."""
    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert suggestions == []


# ---------------------------------------------------------------------------
# generate_suggestions — error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestions_skips_contact_on_compose_error(
    db: AsyncSession, test_user, test_contact
):
    """If compose_followup_message raises, the contact is skipped without crashing."""
    test_contact.relationship_score = 1
    test_contact.last_interaction_at = datetime.now(UTC) - timedelta(days=200)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with patch(
        "app.services.followup_engine.compose_followup_message",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Anthropic API unavailable"),
    ):
        suggestions = await generate_suggestions(test_user.id, db)

    assert suggestions == []


# ---------------------------------------------------------------------------
# generate_suggestions — user isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestions_user_isolation(db: AsyncSession, test_user):
    """Suggestions are only created for the requesting user's contacts."""
    from app.core.auth import hash_password
    from app.models.user import User

    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password=hash_password("testpass123"),
        full_name="Other User",
    )
    db.add(other_user)
    await db.flush()

    other_contact = Contact(
        id=uuid.uuid4(),
        user_id=other_user.id,
        full_name="Other Contact",
        relationship_score=1,
        last_interaction_at=datetime.now(UTC) - timedelta(days=200),
        source="manual",
    )
    db.add(other_contact)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert suggestions == []


# ---------------------------------------------------------------------------
# get_weekly_digest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_weekly_digest_returns_pending_suggestions(
    db: AsyncSession, test_user, test_suggestion
):
    """get_weekly_digest returns all pending suggestions for the user."""
    suggestions = await get_weekly_digest(test_user.id, db)

    assert len(suggestions) >= 1
    assert all(s.status == "pending" for s in suggestions)
    assert all(s.user_id == test_user.id for s in suggestions)


@pytest.mark.asyncio
async def test_get_weekly_digest_excludes_non_pending(
    db: AsyncSession, test_user, test_contact
):
    """Suggestions with status != 'pending' must be excluded."""
    sent = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="Already sent message",
        suggested_channel="email",
        status="sent",
    )
    db.add(sent)
    await db.commit()

    suggestions = await get_weekly_digest(test_user.id, db)

    assert all(s.status == "pending" for s in suggestions)


@pytest.mark.asyncio
async def test_get_weekly_digest_empty_when_no_suggestions(
    db: AsyncSession, test_user
):
    """Returns empty list when there are no pending suggestions."""
    suggestions = await get_weekly_digest(test_user.id, db)
    assert suggestions == []


@pytest.mark.asyncio
async def test_get_weekly_digest_ordered_most_recent_first(
    db: AsyncSession, test_user, test_contact
):
    """Suggestions should be ordered by created_at descending."""
    s1 = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="First message",
        suggested_channel="email",
        status="pending",
    )
    db.add(s1)
    await db.flush()

    s2 = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=test_user.id,
        trigger_type="scheduled",
        suggested_message="Second message",
        suggested_channel="email",
        status="pending",
    )
    db.add(s2)
    await db.commit()

    suggestions = await get_weekly_digest(test_user.id, db)

    assert len(suggestions) >= 2
    for i in range(len(suggestions) - 1):
        assert suggestions[i].created_at >= suggestions[i + 1].created_at


@pytest.mark.asyncio
async def test_get_weekly_digest_user_isolation(
    db: AsyncSession, test_user, test_contact
):
    """get_weekly_digest must not return suggestions belonging to another user."""
    from app.core.auth import hash_password
    from app.models.user import User

    other_user = User(
        id=uuid.uuid4(),
        email="other2@example.com",
        hashed_password=hash_password("testpass123"),
        full_name="Other User 2",
    )
    db.add(other_user)
    await db.flush()

    other_contact = Contact(
        id=uuid.uuid4(),
        user_id=other_user.id,
        full_name="Other Contact",
        relationship_score=3,
        source="manual",
    )
    db.add(other_contact)
    await db.flush()

    other_suggestion = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=other_contact.id,
        user_id=other_user.id,
        trigger_type="time_based",
        suggested_message="Other user message",
        suggested_channel="email",
        status="pending",
    )
    db.add(other_suggestion)
    await db.commit()

    suggestions = await get_weekly_digest(test_user.id, db)

    assert all(s.user_id == test_user.id for s in suggestions)
