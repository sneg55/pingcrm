"""Follow-Up Engine — generates FollowUpSuggestion records for a user."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.detected_event import DetectedEvent
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction
from app.services.message_composer import compose_followup_message

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------
TIME_BASED_INACTIVITY_DAYS = 90
TIME_BASED_MAX_SCORE = 4
EVENT_BASED_WINDOW_DAYS = 7
EVENT_CONFIDENCE_THRESHOLD = 0.7
MAX_SUGGESTIONS_PER_RUN = 5

# Priority scoring constants
COOLING_RECENT_DAYS = 14
COOLING_WINDOW_DAYS = 90
RICH_HISTORY_THRESHOLD = 10
EVENT_TRIGGER_BONUS = 200

# Contact must have at least one reachable channel
_has_channel = or_(
    func.coalesce(func.array_length(Contact.emails, 1), 0) > 0,
    Contact.twitter_handle.isnot(None),
    Contact.telegram_username.isnot(None),
    Contact.linkedin_url.isnot(None),
)

# Exclude contacts tagged "2nd tier"
_not_2nd_tier = or_(Contact.tags.is_(None), ~Contact.tags.contains(["2nd tier"]))

# Only contacts with previous interactions
_has_interactions = Contact.last_interaction_at.isnot(None)


_SENDABLE_CHANNELS = {"email", "telegram", "twitter"}


@dataclass
class _Candidate:
    contact: Contact
    trigger_type: str
    event: DetectedEvent | None = None
    priority: float = 0.0


def compute_priority(
    interaction_count: int,
    days_since_interaction: float,
    is_event_trigger: bool,
) -> float:
    """Compute a priority score for a follow-up candidate.

    Tier 1 — Rich history:  interaction_count >= 10 AND days_since > 90   → 1000+
    Tier 2 — Cooling down:  interaction_count >= 10 AND 14 <= days_since <= 90  → 500-999
    Tier 3 — Standard:      everyone else  → 0-499

    Within each tier, more interactions rank higher.
    Event-based triggers get a +200 bonus.
    """
    base = float(interaction_count)

    if interaction_count >= RICH_HISTORY_THRESHOLD and days_since_interaction > COOLING_WINDOW_DAYS:
        score = 1000.0 + base
    elif (
        interaction_count >= RICH_HISTORY_THRESHOLD
        and COOLING_RECENT_DAYS <= days_since_interaction <= COOLING_WINDOW_DAYS
    ):
        score = 500.0 + base
    else:
        score = base

    if is_event_trigger:
        score += EVENT_TRIGGER_BONUS

    return score


def _days_since(last_interaction_at: datetime | None, now: datetime) -> float:
    """Return days since last interaction, handling timezone-naive datetimes."""
    if not last_interaction_at:
        return 999.0
    ts = last_interaction_at if last_interaction_at.tzinfo else last_interaction_at.replace(tzinfo=UTC)
    return (now - ts).days


async def _get_best_channel(contact_id: uuid.UUID, db: AsyncSession) -> str:
    """Return the platform of the most recent sendable interaction, or 'email' as default."""
    result = await db.execute(
        select(Interaction)
        .where(Interaction.contact_id == contact_id)
        .order_by(Interaction.occurred_at.desc())
        .limit(5)
    )
    for interaction in result.scalars().all():
        if interaction.platform in _SENDABLE_CHANNELS:
            return interaction.platform
    return "email"


async def generate_suggestions(user_id: uuid.UUID, db: AsyncSession) -> list[FollowUpSuggestion]:
    """Main follow-up engine entry point.

    Collects candidates from all 3 trigger types, scores them by priority,
    and creates FollowUpSuggestion records for the top MAX_SUGGESTIONS_PER_RUN.

    Args:
        user_id: The user for whom suggestions are generated.
        db: Async database session (caller is responsible for commit).

    Returns:
        List of newly created FollowUpSuggestion objects.
    """
    now = datetime.now(UTC)

    # Skip contacts that already have a pending suggestion
    existing_result = await db.execute(
        select(FollowUpSuggestion.contact_id).where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "pending",
        )
    )
    queued_contact_ids: set[uuid.UUID] = {row[0] for row in existing_result.all()}

    # Phase 1: Collect all candidates from the 3 triggers
    candidates: dict[uuid.UUID, _Candidate] = {}

    # ------------------------------------------------------------------
    # Trigger 1: Time-based — no interaction in 90+ days AND score < 4
    # ------------------------------------------------------------------
    cutoff_time = now - timedelta(days=TIME_BASED_INACTIVITY_DAYS)
    time_based_result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            _not_2nd_tier,
            _has_channel,
            _has_interactions,
            Contact.relationship_score < TIME_BASED_MAX_SCORE,
            Contact.last_interaction_at < cutoff_time,
        )
    )
    for contact in time_based_result.scalars().all():
        if contact.id in queued_contact_ids:
            continue
        days_since = _days_since(contact.last_interaction_at, now)
        priority = compute_priority(contact.interaction_count, days_since, False)
        if contact.id not in candidates or priority > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="time_based", priority=priority,
            )

    # ------------------------------------------------------------------
    # Trigger 2: Event-based — DetectedEvents in last 7 days, confidence > 0.7
    # ------------------------------------------------------------------
    event_cutoff = now - timedelta(days=EVENT_BASED_WINDOW_DAYS)
    events_result = await db.execute(
        select(DetectedEvent, Contact)
        .join(Contact, DetectedEvent.contact_id == Contact.id)
        .where(
            Contact.user_id == user_id,
            _not_2nd_tier,
            _has_channel,
            _has_interactions,
            DetectedEvent.detected_at >= event_cutoff,
            DetectedEvent.confidence > EVENT_CONFIDENCE_THRESHOLD,
        )
        .order_by(DetectedEvent.confidence.desc())
    )
    for event, contact in events_result.all():
        if contact.id in queued_contact_ids:
            continue
        days_since = _days_since(contact.last_interaction_at, now)
        priority = compute_priority(contact.interaction_count, days_since, True)
        if contact.id not in candidates or priority > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="event_based", event=event, priority=priority,
            )

    # ------------------------------------------------------------------
    # Trigger 3: Scheduled — last_followup_at > 30 days ago
    # ------------------------------------------------------------------
    scheduled_cutoff = now - timedelta(days=30)
    scheduled_result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            _not_2nd_tier,
            _has_channel,
            _has_interactions,
            Contact.last_followup_at.isnot(None),
            Contact.last_followup_at < scheduled_cutoff,
        )
    )
    for contact in scheduled_result.scalars().all():
        if contact.id in queued_contact_ids:
            continue
        days_since = _days_since(contact.last_interaction_at, now)
        priority = compute_priority(contact.interaction_count, days_since, False)
        if contact.id not in candidates or priority > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="scheduled", priority=priority,
            )

    # Phase 2: Sort by priority descending, take top N
    sorted_candidates = sorted(candidates.values(), key=lambda c: c.priority, reverse=True)
    top_candidates = sorted_candidates[:MAX_SUGGESTIONS_PER_RUN]

    # Phase 3: Create FollowUpSuggestion records for winners
    created: list[FollowUpSuggestion] = []
    for candidate in top_candidates:
        contact = candidate.contact
        try:
            channel = await _get_best_channel(contact.id, db)
            event_summary = candidate.event.summary if candidate.event else None
            message = await compose_followup_message(
                contact_id=contact.id,
                trigger_type=candidate.trigger_type,
                event_summary=event_summary,
                db=db,
            )
            suggestion = FollowUpSuggestion(
                contact_id=contact.id,
                user_id=user_id,
                trigger_type=candidate.trigger_type,
                trigger_event_id=candidate.event.id if candidate.event else None,
                suggested_message=message,
                suggested_channel=channel,
                status="pending",
            )
            db.add(suggestion)
            await db.flush()
            await db.refresh(suggestion)
            created.append(suggestion)
            logger.info(
                "generate_suggestions: %s suggestion created for contact %s (priority=%.1f)",
                candidate.trigger_type, contact.id, candidate.priority,
            )
        except Exception:
            logger.exception(
                "generate_suggestions: failed to create %s suggestion for contact %s",
                candidate.trigger_type, contact.id,
            )

    logger.info(
        "generate_suggestions: created %d suggestion(s) for user %s", len(created), user_id
    )
    return created


async def get_weekly_digest(user_id: uuid.UUID, db: AsyncSession) -> list[FollowUpSuggestion]:
    """Fetch pending suggestions for a user ordered by creation date (most recent first).

    Args:
        user_id: Target user's UUID.
        db: Async database session.

    Returns:
        List of pending FollowUpSuggestion objects.
    """
    result = await db.execute(
        select(FollowUpSuggestion)
        .where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "pending",
        )
        .order_by(FollowUpSuggestion.created_at.desc())
    )
    return list(result.scalars().all())
