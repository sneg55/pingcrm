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
from app.models.interaction import Interaction
from app.services.followup_engine import (
    DORMANCY_THRESHOLD_DAYS,
    HARD_CAP_DORMANCY_YEARS,
    MAX_SUGGESTIONS_PER_RUN,
    MIN_INTERACTIONS_FOR_SUGGESTION,
    POOL_A_SLOTS,
    POOL_B_SLOTS,
    STALE_CONTACT_DAYS,
    compute_priority,
    compute_priority_b,
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


async def _make_contact(db, user_id, *, name="Test", **kwargs):
    """Create a contact with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=name,
        given_name=name.split()[0],
        emails=[f"{name.lower().replace(' ', '')}@test.com"],
        relationship_score=3,
        interaction_count=5,
        source="manual",
    )
    defaults.update(kwargs)
    contact = Contact(**defaults)
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return contact


async def _make_interactions(db, user_id, contact_id, count, *, span_days=0):
    """Create `count` interactions spread over `span_days`."""
    for i in range(count):
        offset = timedelta(days=span_days * i / max(count - 1, 1)) if span_days > 0 else timedelta()
        interaction = Interaction(
            id=uuid.uuid4(),
            contact_id=contact_id,
            user_id=user_id,
            platform="email",
            direction="inbound",
            content_preview=f"Message {i}",
            occurred_at=datetime.now(UTC) - timedelta(days=730) + offset,
        )
        db.add(interaction)
    await db.flush()


# ---------------------------------------------------------------------------
# _get_best_channel — tested indirectly through generate_suggestions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_best_channel_falls_back_to_email(
    db: AsyncSession, test_user, test_contact
):
    """When a contact has no recent interactions the channel should default to 'email'."""
    test_contact.relationship_score = 3
    test_contact.interaction_count = 5
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
    test_contact.interaction_count = 5
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
    test_contact.interaction_count = 5
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
    assert s.pool == "A"
    assert s.suggested_message == MOCK_MESSAGE


@pytest.mark.asyncio
async def test_generate_suggestions_time_based_null_last_interaction(
    db: AsyncSession, test_user, test_contact
):
    """last_interaction_at=None should NOT qualify for Pool A time-based."""
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
    assert s.pool == "A"


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
    """last_followup_at older than the medium-priority interval (60 days) triggers a scheduled suggestion."""
    test_contact.interaction_count = 5
    test_contact.last_followup_at = datetime.now(UTC) - timedelta(days=65)
    db.add(test_contact)
    await db.commit()
    await db.refresh(test_contact)

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    scheduled = [s for s in suggestions if s.trigger_type == "scheduled"]
    assert len(scheduled) == 1
    assert scheduled[0].contact_id == test_contact.id
    assert scheduled[0].pool == "A"


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
    test_contact.interaction_count = 5
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
            interaction_count=5,
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
    test_contact.interaction_count = 5
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
        interaction_count=5,
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


# ---------------------------------------------------------------------------
# Minimum interaction count & staleness filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_low_interaction_contact_excluded(db: AsyncSession, test_user):
    """A low-priority contact with fewer than 3 interactions should NOT get a suggestion."""
    contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Low Interaction",
        emails=["low@test.com"],
        relationship_score=2,
        interaction_count=2,  # below low threshold of 3
        priority_level="low",
        last_interaction_at=datetime.now(UTC) - timedelta(days=100),
        source="manual",
    )
    db.add(contact)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert not any(s.contact_id == contact.id for s in suggestions)


@pytest.mark.asyncio
async def test_high_priority_one_interaction_included(db: AsyncSession, test_user):
    """A high-priority contact with just 1 interaction should still get a suggestion."""
    contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="VIP Investor",
        emails=["vip@test.com"],
        relationship_score=2,
        interaction_count=1,  # meets high threshold of 1
        priority_level="high",
        last_interaction_at=datetime.now(UTC) - timedelta(days=45),
        source="manual",
    )
    db.add(contact)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert any(s.contact_id == contact.id for s in suggestions)


@pytest.mark.asyncio
async def test_stale_score_zero_contact_excluded(db: AsyncSession, test_user):
    """A contact with score 0 and no interaction in 400+ days should be excluded even with enough interactions."""
    contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Dead Contact",
        emails=["dead@test.com"],
        relationship_score=0,
        interaction_count=6,  # above medium threshold
        last_interaction_at=datetime.now(UTC) - timedelta(days=400),
        source="manual",
    )
    db.add(contact)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    # Contact is dormant (>365 days) so won't appear in Pool A.
    # For Pool B, score=0 doesn't meet depth qualification.
    assert not any(s.contact_id == contact.id for s in suggestions)


# ---------------------------------------------------------------------------
# compute_priority — unit tests (Pool A)
# ---------------------------------------------------------------------------


def test_compute_priority_rich_history():
    """Tier 1: interaction_count >= 10 AND days_since > 90 → 1000+."""
    score = compute_priority(interaction_count=50, days_since_interaction=100, is_event_trigger=False)
    assert score >= 1000


def test_compute_priority_cooling_down():
    """Tier 2: interaction_count >= 10 AND 14 <= days_since <= 90 → 500-999."""
    score = compute_priority(interaction_count=15, days_since_interaction=20, is_event_trigger=False)
    assert 500 <= score < 1000


def test_compute_priority_standard():
    """Tier 3: everyone else → 0-499."""
    score = compute_priority(interaction_count=2, days_since_interaction=100, is_event_trigger=False)
    assert score < 500


def test_compute_priority_event_bonus():
    """Event triggers get a +200 bonus."""
    base = compute_priority(interaction_count=5, days_since_interaction=30, is_event_trigger=False)
    with_event = compute_priority(interaction_count=5, days_since_interaction=30, is_event_trigger=True)
    assert with_event == base + 200


def test_compute_priority_more_interactions_rank_higher():
    """Within a tier, more interactions = higher priority."""
    low = compute_priority(interaction_count=10, days_since_interaction=100, is_event_trigger=False)
    high = compute_priority(interaction_count=50, days_since_interaction=100, is_event_trigger=False)
    assert high > low


# ---------------------------------------------------------------------------
# compute_priority_b — unit tests (Pool B)
# ---------------------------------------------------------------------------


def test_compute_priority_b_tiers():
    """Verify depth-based tier scoring for Pool B."""
    # Tier 1: Deep (interactions >= 8 OR score >= 5)
    deep = compute_priority_b(interaction_count=10, relationship_score=3, span_days=100, has_event=False)
    assert deep >= 1000

    deep_score = compute_priority_b(interaction_count=3, relationship_score=6, span_days=100, has_event=False)
    assert deep_score >= 1000

    # Tier 2: Solid (interactions >= 4 OR score >= 3)
    solid = compute_priority_b(interaction_count=5, relationship_score=2, span_days=100, has_event=False)
    assert 500 <= solid < 1000

    solid_score = compute_priority_b(interaction_count=2, relationship_score=4, span_days=100, has_event=False)
    assert 500 <= solid_score < 1000

    # Tier 3: Qualifying (below tier 2 thresholds)
    qualifying = compute_priority_b(interaction_count=3, relationship_score=2, span_days=100, has_event=False)
    assert qualifying < 500


def test_compute_priority_b_event_bonus():
    """Verify +300 event bonus for Pool B."""
    base = compute_priority_b(interaction_count=10, relationship_score=5, span_days=100, has_event=False)
    with_event = compute_priority_b(interaction_count=10, relationship_score=5, span_days=100, has_event=True)
    assert with_event == base + 300


def test_compute_priority_b_span_bonus():
    """Verify +150 span bonus for span >= 180 days."""
    short_span = compute_priority_b(interaction_count=10, relationship_score=5, span_days=100, has_event=False)
    long_span = compute_priority_b(interaction_count=10, relationship_score=5, span_days=200, has_event=False)
    assert long_span == short_span + 150


# ---------------------------------------------------------------------------
# Priority-based ordering — integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rich_history_contacts_prioritized(db: AsyncSession, test_user):
    """A contact with 50 interactions should beat one with 2 interactions."""
    rich = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Rich History",
        emails=["rich@test.com"],
        relationship_score=2,
        interaction_count=50,
        last_interaction_at=datetime.now(UTC) - timedelta(days=100),
        source="manual",
    )
    poor = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Poor History",
        emails=["poor@test.com"],
        relationship_score=2,
        interaction_count=3,
        last_interaction_at=datetime.now(UTC) - timedelta(days=100),
        source="manual",
    )
    db.add_all([rich, poor])
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_a = [s for s in suggestions if s.pool == "A"]
    assert len(pool_a) == 2
    assert pool_a[0].contact_id == rich.id


@pytest.mark.asyncio
async def test_cooling_contacts_beat_standard(db: AsyncSession, test_user):
    """A cooling contact (15 interactions, 100 days ago) beats a standard contact (3 interactions, 100 days ago)."""
    cooling = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Cooling Down",
        emails=["cooling@test.com"],
        relationship_score=2,
        interaction_count=15,
        last_interaction_at=datetime.now(UTC) - timedelta(days=100),
        source="manual",
    )
    standard = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Standard",
        emails=["standard@test.com"],
        relationship_score=2,
        interaction_count=3,
        last_interaction_at=datetime.now(UTC) - timedelta(days=100),
        source="manual",
    )
    db.add_all([cooling, standard])
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_a = [s for s in suggestions if s.pool == "A"]
    assert len(pool_a) == 2
    assert pool_a[0].contact_id == cooling.id


@pytest.mark.asyncio
async def test_event_trigger_gets_priority_bonus(db: AsyncSession, test_user):
    """An event-triggered contact with few interactions should beat a standard contact with few interactions."""
    event_contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Event Contact",
        emails=["event@test.com"],
        relationship_score=2,
        interaction_count=3,
        last_interaction_at=datetime.now(UTC) - timedelta(days=5),
        source="manual",
    )
    standard_contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Standard Time-Based",
        emails=["standard@test.com"],
        relationship_score=2,
        interaction_count=3,
        last_interaction_at=datetime.now(UTC) - timedelta(days=100),
        source="manual",
    )
    db.add_all([event_contact, standard_contact])
    await db.flush()

    event = DetectedEvent(
        id=uuid.uuid4(),
        contact_id=event_contact.id,
        event_type="job_change",
        confidence=0.9,
        summary="Got promoted",
        detected_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.add(event)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_a = [s for s in suggestions if s.pool == "A"]
    assert len(pool_a) == 2
    assert pool_a[0].contact_id == event_contact.id
    assert pool_a[0].trigger_type == "event_based"


# ---------------------------------------------------------------------------
# Pool B qualification tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_b_qualifies_by_interaction_count(db: AsyncSession, test_user):
    """A dormant contact with 10 interactions qualifies for Pool B."""
    contact = await _make_contact(
        db, test_user.id,
        name="Deep Dormant",
        interaction_count=10,
        relationship_score=3,
        last_interaction_at=datetime.now(UTC) - timedelta(days=730),  # 2 years
    )
    await _make_interactions(db, test_user.id, contact.id, 10, span_days=200)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    assert any(s.contact_id == contact.id for s in pool_b)


@pytest.mark.asyncio
async def test_pool_b_qualifies_by_score(db: AsyncSession, test_user):
    """A dormant contact with score 7 qualifies for Pool B via B1 trigger."""
    contact = await _make_contact(
        db, test_user.id,
        name="High Score Dormant",
        interaction_count=5,
        relationship_score=7,
        last_interaction_at=datetime.now(UTC) - timedelta(days=730),  # 2 years
    )
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    assert any(s.contact_id == contact.id for s in pool_b)


@pytest.mark.asyncio
async def test_pool_b_qualifies_by_span(db: AsyncSession, test_user):
    """A dormant contact with span >= 180 days and enough interactions qualifies for Pool B via B2."""
    contact = await _make_contact(
        db, test_user.id,
        name="Long Span Dormant",
        interaction_count=10,
        relationship_score=3,
        last_interaction_at=datetime.now(UTC) - timedelta(days=730),  # 2 years
    )
    await _make_interactions(db, test_user.id, contact.id, 10, span_days=200)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    assert any(s.contact_id == contact.id for s in pool_b)


@pytest.mark.asyncio
async def test_pool_b_excluded_insufficient_depth(db: AsyncSession, test_user):
    """A dormant contact with 1 interaction, score 0 should be excluded from Pool B."""
    contact = await _make_contact(
        db, test_user.id,
        name="Shallow Dormant",
        interaction_count=1,
        relationship_score=0,
        last_interaction_at=datetime.now(UTC) - timedelta(days=730),  # 2 years
    )
    await _make_interactions(db, test_user.id, contact.id, 1, span_days=0)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    assert not any(s.contact_id == contact.id for s in pool_b)


# ---------------------------------------------------------------------------
# Pool B trigger tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_b1_deep_dormant(db: AsyncSession, test_user):
    """20 interactions, dormant 3 years → dormant_deep suggestion."""
    contact = await _make_contact(
        db, test_user.id,
        name="Deep History",
        interaction_count=20,
        relationship_score=5,
        last_interaction_at=datetime.now(UTC) - timedelta(days=1095),  # 3 years
    )
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    matching = [s for s in pool_b if s.contact_id == contact.id]
    assert len(matching) == 1
    assert matching[0].trigger_type == "dormant_deep"


@pytest.mark.asyncio
async def test_trigger_b2_mid_dormant(db: AsyncSession, test_user):
    """10 interactions, span 120 days, dormant 2 years → dormant_mid suggestion."""
    contact = await _make_contact(
        db, test_user.id,
        name="Mid Dormant",
        interaction_count=10,
        relationship_score=3,
        last_interaction_at=datetime.now(UTC) - timedelta(days=730),  # 2 years
    )
    await _make_interactions(db, test_user.id, contact.id, 10, span_days=120)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    matching = [s for s in pool_b if s.contact_id == contact.id]
    assert len(matching) == 1
    assert matching[0].trigger_type in ("dormant_mid", "dormant_deep")


@pytest.mark.asyncio
async def test_trigger_b3_event_revival(db: AsyncSession, test_user):
    """Event in last 14 days + dormant contact → dormant_event suggestion."""
    contact = await _make_contact(
        db, test_user.id,
        name="Event Revival",
        interaction_count=10,
        relationship_score=5,
        last_interaction_at=datetime.now(UTC) - timedelta(days=730),  # 2 years
    )
    event = DetectedEvent(
        id=uuid.uuid4(),
        contact_id=contact.id,
        event_type="funding_round",
        confidence=0.9,
        summary="Company raised Series B",
        detected_at=datetime.now(UTC) - timedelta(days=5),
    )
    db.add(event)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    matching = [s for s in pool_b if s.contact_id == contact.id]
    assert len(matching) == 1
    assert matching[0].trigger_type == "dormant_event"


@pytest.mark.asyncio
async def test_trigger_b3_overrides_hard_cap(db: AsyncSession, test_user):
    """Dormant 6 years + fresh event → included (B3 overrides hard cap)."""
    contact = await _make_contact(
        db, test_user.id,
        name="Ancient Contact",
        interaction_count=10,
        relationship_score=5,
        last_interaction_at=datetime.now(UTC) - timedelta(days=2190),  # 6 years
    )
    event = DetectedEvent(
        id=uuid.uuid4(),
        contact_id=contact.id,
        event_type="job_change",
        confidence=0.85,
        summary="Started new role at BigCorp",
        detected_at=datetime.now(UTC) - timedelta(days=3),
    )
    db.add(event)
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    assert any(s.contact_id == contact.id for s in pool_b)


@pytest.mark.asyncio
async def test_hard_cap_excludes_ancient(db: AsyncSession, test_user):
    """Dormant 6 years, no event → excluded by hard cap."""
    contact = await _make_contact(
        db, test_user.id,
        name="Ancient No Event",
        interaction_count=20,
        relationship_score=8,
        last_interaction_at=datetime.now(UTC) - timedelta(days=2190),  # 6 years
    )
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    assert not any(s.contact_id == contact.id for s in pool_b)


# ---------------------------------------------------------------------------
# Budget & rollover tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_budgets_default_3a_2b(db: AsyncSession, test_user):
    """Both pools have candidates → 3 from Pool A + 2 from Pool B."""
    # Create 5 Pool A candidates (active, recent enough)
    for i in range(5):
        await _make_contact(
            db, test_user.id,
            name=f"Active {i}",
            interaction_count=5,
            relationship_score=2,
            last_interaction_at=datetime.now(UTC) - timedelta(days=100),
        )

    # Create 4 Pool B candidates (dormant, deep)
    for i in range(4):
        contact = await _make_contact(
            db, test_user.id,
            name=f"Dormant {i}",
            interaction_count=20,
            relationship_score=5,
            last_interaction_at=datetime.now(UTC) - timedelta(days=730),
        )
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_a_count = sum(1 for s in suggestions if s.pool == "A")
    pool_b_count = sum(1 for s in suggestions if s.pool == "B")
    assert pool_a_count == POOL_A_SLOTS
    assert pool_b_count == POOL_B_SLOTS
    assert len(suggestions) == POOL_A_SLOTS + POOL_B_SLOTS


@pytest.mark.asyncio
async def test_pool_b_empty_rollover_to_a(db: AsyncSession, test_user):
    """No Pool B candidates → all 5 slots go to Pool A."""
    for i in range(6):
        await _make_contact(
            db, test_user.id,
            name=f"Active {i}",
            interaction_count=5,
            relationship_score=2,
            last_interaction_at=datetime.now(UTC) - timedelta(days=100),
        )
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    assert all(s.pool == "A" for s in suggestions)
    assert len(suggestions) == POOL_A_SLOTS + POOL_B_SLOTS


@pytest.mark.asyncio
async def test_pool_a_short_rollover_to_b(db: AsyncSession, test_user):
    """Pool A has 1 candidate → Pool B gets up to 4."""
    # 1 active contact
    await _make_contact(
        db, test_user.id,
        name="Solo Active",
        interaction_count=5,
        relationship_score=2,
        last_interaction_at=datetime.now(UTC) - timedelta(days=100),
    )

    # 5 dormant contacts
    for i in range(5):
        await _make_contact(
            db, test_user.id,
            name=f"Dormant {i}",
            interaction_count=20,
            relationship_score=5,
            last_interaction_at=datetime.now(UTC) - timedelta(days=730),
        )
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    pool_a_count = sum(1 for s in suggestions if s.pool == "A")
    pool_b_count = sum(1 for s in suggestions if s.pool == "B")
    assert pool_a_count == 1
    assert pool_b_count == 4
    assert len(suggestions) == 5


# ---------------------------------------------------------------------------
# Pool field on suggestions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_field_on_suggestions(db: AsyncSession, test_user):
    """Verify `pool` is 'A' or 'B' on created suggestion records."""
    # Pool A contact
    await _make_contact(
        db, test_user.id,
        name="Active Contact",
        interaction_count=5,
        relationship_score=2,
        last_interaction_at=datetime.now(UTC) - timedelta(days=100),
    )

    # Pool B contact
    await _make_contact(
        db, test_user.id,
        name="Dormant Contact",
        interaction_count=20,
        relationship_score=5,
        last_interaction_at=datetime.now(UTC) - timedelta(days=730),
    )
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    for s in suggestions:
        assert s.pool in ("A", "B")

    pools = {s.pool for s in suggestions}
    assert "A" in pools
    assert "B" in pools


# ---------------------------------------------------------------------------
# Revival context passed for Pool B
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revival_context_passed_for_pool_b(db: AsyncSession, test_user):
    """Verify compose_followup_message is called with revival_context=True for Pool B contacts."""
    contact = await _make_contact(
        db, test_user.id,
        name="Revival Target",
        interaction_count=20,
        relationship_score=5,
        last_interaction_at=datetime.now(UTC) - timedelta(days=730),
    )
    await db.commit()

    mock_compose = AsyncMock(return_value=MOCK_MESSAGE)
    with patch("app.services.followup_engine.compose_followup_message", mock_compose):
        suggestions = await generate_suggestions(test_user.id, db)

    pool_b = [s for s in suggestions if s.pool == "B"]
    assert len(pool_b) >= 1

    # Find the call for our Pool B contact
    for call in mock_compose.call_args_list:
        if call.kwargs.get("contact_id") == contact.id or (call.args and call.args[0] == contact.id):
            assert call.kwargs.get("revival_context") is True
            break
    else:
        pytest.fail("compose_followup_message was not called for Pool B contact")


# ---------------------------------------------------------------------------
# Dormancy boundary — contacts at exactly 365 days go to Pool B, not A
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dormancy_boundary_routes_to_pool_b(db: AsyncSession, test_user):
    """A contact with last_interaction_at exactly at dormancy threshold goes to Pool B, not Pool A."""
    contact = await _make_contact(
        db, test_user.id,
        name="Boundary Contact",
        interaction_count=20,
        relationship_score=7,
        last_interaction_at=datetime.now(UTC) - timedelta(days=DORMANCY_THRESHOLD_DAYS + 1),
    )
    await db.commit()

    with _patch_compose():
        suggestions = await generate_suggestions(test_user.id, db)

    matching = [s for s in suggestions if s.contact_id == contact.id]
    assert len(matching) == 1
    assert matching[0].pool == "B"
