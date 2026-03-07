"""Follow-Up Engine — generates FollowUpSuggestion records for a user."""
from __future__ import annotations

import logging
import uuid
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


async def _get_best_channel(contact_id: uuid.UUID, db: AsyncSession) -> str:
    """Return the platform of the most recent interaction, or 'email' as default."""
    result = await db.execute(
        select(Interaction)
        .where(Interaction.contact_id == contact_id)
        .order_by(Interaction.occurred_at.desc())
        .limit(1)
    )
    interaction = result.scalar_one_or_none()
    return interaction.platform if interaction else "email"


async def generate_suggestions(user_id: uuid.UUID, db: AsyncSession) -> list[FollowUpSuggestion]:
    """Main follow-up engine entry point.

    Scans for triggered contacts across three trigger types and creates
    FollowUpSuggestion records (up to MAX_SUGGESTIONS_PER_RUN).

    Args:
        user_id: The user for whom suggestions are generated.
        db: Async database session (caller is responsible for commit).

    Returns:
        List of newly created FollowUpSuggestion objects.
    """
    now = datetime.now(UTC)
    created: list[FollowUpSuggestion] = []

    # Skip contacts that already have a pending suggestion
    existing_result = await db.execute(
        select(FollowUpSuggestion.contact_id).where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "pending",
        )
    )
    queued_contact_ids: set[uuid.UUID] = {row[0] for row in existing_result.all()}

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
    time_based_contacts = time_based_result.scalars().all()

    for contact in time_based_contacts:
        if len(created) >= MAX_SUGGESTIONS_PER_RUN:
            break
        if contact.id in queued_contact_ids:
            continue

        try:
            channel = await _get_best_channel(contact.id, db)
            message = await compose_followup_message(
                contact_id=contact.id,
                trigger_type="time_based",
                event_summary=None,
                db=db,
            )
            suggestion = FollowUpSuggestion(
                contact_id=contact.id,
                user_id=user_id,
                trigger_type="time_based",
                suggested_message=message,
                suggested_channel=channel,
                status="pending",
            )
            db.add(suggestion)
            await db.flush()
            await db.refresh(suggestion)
            created.append(suggestion)
            queued_contact_ids.add(contact.id)
            logger.info(
                "generate_suggestions: time_based suggestion created for contact %s", contact.id
            )
        except Exception:
            logger.exception(
                "generate_suggestions: failed to create time_based suggestion for contact %s",
                contact.id,
            )

    # ------------------------------------------------------------------
    # Trigger 2: Event-based — DetectedEvents in last 7 days, confidence > 0.7
    # ------------------------------------------------------------------
    event_cutoff = now - timedelta(days=EVENT_BASED_WINDOW_DAYS)
    events_result = await db.execute(
        select(DetectedEvent)
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
    recent_events = events_result.scalars().all()

    for event in recent_events:
        if len(created) >= MAX_SUGGESTIONS_PER_RUN:
            break
        if event.contact_id in queued_contact_ids:
            continue

        try:
            channel = await _get_best_channel(event.contact_id, db)
            message = await compose_followup_message(
                contact_id=event.contact_id,
                trigger_type="event_based",
                event_summary=event.summary,
                db=db,
            )
            suggestion = FollowUpSuggestion(
                contact_id=event.contact_id,
                user_id=user_id,
                trigger_type="event_based",
                trigger_event_id=event.id,
                suggested_message=message,
                suggested_channel=channel,
                status="pending",
            )
            db.add(suggestion)
            await db.flush()
            await db.refresh(suggestion)
            created.append(suggestion)
            queued_contact_ids.add(event.contact_id)
            logger.info(
                "generate_suggestions: event_based suggestion created for contact %s (event %s)",
                event.contact_id,
                event.id,
            )
        except Exception:
            logger.exception(
                "generate_suggestions: failed to create event_based suggestion for contact %s",
                event.contact_id,
            )

    # ------------------------------------------------------------------
    # Trigger 3: Scheduled — last_followup_at + snooze_duration < now
    # We approximate this as contacts whose last_followup_at is more than
    # 30 days ago (no snooze_duration field on Contact; use last_followup_at).
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
    scheduled_contacts = scheduled_result.scalars().all()

    for contact in scheduled_contacts:
        if len(created) >= MAX_SUGGESTIONS_PER_RUN:
            break
        if contact.id in queued_contact_ids:
            continue

        try:
            channel = await _get_best_channel(contact.id, db)
            message = await compose_followup_message(
                contact_id=contact.id,
                trigger_type="scheduled",
                event_summary=None,
                db=db,
            )
            suggestion = FollowUpSuggestion(
                contact_id=contact.id,
                user_id=user_id,
                trigger_type="scheduled",
                suggested_message=message,
                suggested_channel=channel,
                status="pending",
            )
            db.add(suggestion)
            await db.flush()
            await db.refresh(suggestion)
            created.append(suggestion)
            queued_contact_ids.add(contact.id)
            logger.info(
                "generate_suggestions: scheduled suggestion created for contact %s", contact.id
            )
        except Exception:
            logger.exception(
                "generate_suggestions: failed to create scheduled suggestion for contact %s",
                contact.id,
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
