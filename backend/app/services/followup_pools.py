"""Pool A (active relationships) and Pool B (dormant revival) candidate collectors.

Kept separate from followup_engine.py so the main orchestration module stays
focused on dispatching candidates → suggestions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.detected_event import DetectedEvent
from app.models.interaction import Interaction
from app.services.followup_engine import (
    B1_MAX_DORMANCY_YEARS,
    B1_MIN_INTERACTIONS,
    B1_MIN_SCORE,
    B2_MAX_DORMANCY_YEARS,
    B2_MIN_INTERACTIONS,
    B2_MIN_SPAN_DAYS,
    B3_EVENT_WINDOW_DAYS,
    COOLING_RECENT_DAYS,
    DORMANCY_THRESHOLD_DAYS,
    EVENT_BASED_WINDOW_DAYS,
    EVENT_CONFIDENCE_THRESHOLD,
    HARD_CAP_DORMANCY_YEARS,
    MIN_INTERACTIONS_FOR_SUGGESTION,
    POOL_B_MIN_INTERACTIONS,
    POOL_B_MIN_SCORE,
    POOL_B_MIN_SPAN_DAYS,
    STALE_CONTACT_DAYS,
    TIME_BASED_MAX_SCORE,
    _Candidate,
    _days_since,
    _get_interval,
    _has_channel,
    _has_interactions,
    _not_2nd_tier,
    _not_archived,
    compute_priority,
    compute_priority_b,
)


async def _collect_pool_a_candidates(
    user_id: uuid.UUID,
    db: AsyncSession,
    now: datetime,
    queued_contact_ids: set[uuid.UUID],
    priority_settings: dict | None = None,
    dormancy_days: int = DORMANCY_THRESHOLD_DAYS,
) -> dict[uuid.UUID, _Candidate]:
    """Collect candidates from triggers 1-4 for active (non-dormant) contacts."""
    candidates: dict[uuid.UUID, _Candidate] = {}
    dormancy_cutoff = now - timedelta(days=dormancy_days)

    # Trigger 1: Time-based
    for level in ("high", "medium", "low"):
        interval_days = _get_interval(priority_settings, level)
        cutoff_time = now - timedelta(days=interval_days)
        time_based_result = await db.execute(
            select(Contact).where(
                Contact.user_id == user_id,
                _not_2nd_tier,
                _has_channel,
                _has_interactions,
                _not_archived,
                Contact.priority_level == level,
                Contact.relationship_score < TIME_BASED_MAX_SCORE,
                Contact.last_interaction_at < cutoff_time,
                Contact.last_interaction_at >= dormancy_cutoff,
                Contact.interaction_count >= MIN_INTERACTIONS_FOR_SUGGESTION.get(level, 3),
            )
        )
        for contact in time_based_result.scalars().all():
            if contact.id in queued_contact_ids:
                continue
            days_since = _days_since(contact.last_interaction_at, now)
            if contact.relationship_score == 0 and days_since > STALE_CONTACT_DAYS:
                continue
            priority_score = compute_priority(contact.interaction_count, days_since, False)
            if contact.id not in candidates or priority_score > candidates[contact.id].priority:
                candidates[contact.id] = _Candidate(
                    contact=contact, trigger_type="time_based", priority=priority_score, pool="A",
                )

    # Trigger 2: Event-based
    event_cutoff = now - timedelta(days=EVENT_BASED_WINDOW_DAYS)
    cooling_cutoff = now - timedelta(days=COOLING_RECENT_DAYS)
    events_result = await db.execute(
        select(DetectedEvent, Contact)
        .join(Contact, DetectedEvent.contact_id == Contact.id)
        .where(
            Contact.user_id == user_id,
            _not_2nd_tier,
            _has_channel,
            _has_interactions,
            _not_archived,
            Contact.last_interaction_at >= dormancy_cutoff,
            Contact.last_interaction_at < cooling_cutoff,
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
                contact=contact, trigger_type="event_based", event=event, priority=priority, pool="A",
            )

    # Trigger 3: Scheduled
    for level in ("high", "medium", "low"):
        interval_days = _get_interval(priority_settings, level)
        scheduled_cutoff = now - timedelta(days=interval_days)
        scheduled_result = await db.execute(
            select(Contact).where(
                Contact.user_id == user_id,
                _not_2nd_tier,
                _has_channel,
                _has_interactions,
                _not_archived,
                Contact.priority_level == level,
                Contact.last_followup_at.isnot(None),
                Contact.last_followup_at < scheduled_cutoff,
                Contact.last_interaction_at >= dormancy_cutoff,
                Contact.interaction_count >= MIN_INTERACTIONS_FOR_SUGGESTION.get(level, 3),
            )
        )
        for contact in scheduled_result.scalars().all():
            if contact.id in queued_contact_ids:
                continue
            days_since = _days_since(contact.last_interaction_at, now)
            if contact.relationship_score == 0 and days_since > STALE_CONTACT_DAYS:
                continue
            priority_score = compute_priority(contact.interaction_count, days_since, False)
            if contact.id not in candidates or priority_score > candidates[contact.id].priority:
                candidates[contact.id] = _Candidate(
                    contact=contact, trigger_type="scheduled", priority=priority_score, pool="A",
                )

    # Trigger 4: Birthday
    today = now.date()
    upcoming_mmdd = {(today + timedelta(days=d)).strftime("%m-%d") for d in range(4)}
    birthday_result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            _not_2nd_tier,
            _has_channel,
            _not_archived,
            Contact.birthday.isnot(None),
        )
    )
    for contact in birthday_result.scalars().all():
        if contact.id in queued_contact_ids:
            continue
        bday = contact.birthday.strip()
        mmdd = bday[-5:]
        if mmdd not in upcoming_mmdd:
            continue
        if contact.id not in candidates or 1500.0 > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="birthday", priority=1500.0, pool="A",
            )

    return candidates


async def _collect_pool_b_candidates(
    user_id: uuid.UUID,
    db: AsyncSession,
    now: datetime,
    queued_contact_ids: set[uuid.UUID],
    dormancy_days: int = DORMANCY_THRESHOLD_DAYS,
) -> dict[uuid.UUID, _Candidate]:
    """Collect candidates from dormant contacts worth reviving."""
    candidates: dict[uuid.UUID, _Candidate] = {}
    dormancy_cutoff = now - timedelta(days=dormancy_days)
    hard_cap_cutoff = now - timedelta(days=HARD_CAP_DORMANCY_YEARS * 365)

    span_subq = (
        select(
            Interaction.contact_id,
            func.extract(
                'epoch',
                func.max(Interaction.occurred_at) - func.min(Interaction.occurred_at)
            ).label('span_seconds'),
        )
        .group_by(Interaction.contact_id)
        .subquery()
    )

    _is_dormant = or_(
        Contact.last_interaction_at.is_(None),
        Contact.last_interaction_at < dormancy_cutoff,
    )

    _has_nonzero_score = Contact.relationship_score > 0

    # B1 — Deep Dormant
    b1_min_cutoff = now - timedelta(days=365)
    b1_max_cutoff = now - timedelta(days=B1_MAX_DORMANCY_YEARS * 365)
    b1_result = await db.execute(
        select(Contact, span_subq.c.span_seconds)
        .outerjoin(span_subq, Contact.id == span_subq.c.contact_id)
        .where(
            Contact.user_id == user_id,
            _not_2nd_tier,
            _has_channel,
            _not_archived,
            _has_nonzero_score,
            Contact.last_interaction_at.isnot(None),
            Contact.last_interaction_at < b1_min_cutoff,
            Contact.last_interaction_at >= b1_max_cutoff,
            or_(
                Contact.interaction_count >= B1_MIN_INTERACTIONS,
                Contact.relationship_score >= B1_MIN_SCORE,
            ),
        )
    )
    for contact, span_seconds in b1_result.all():
        if contact.id in queued_contact_ids:
            continue
        span_days = float(span_seconds or 0) / 86400.0
        priority = compute_priority_b(
            contact.interaction_count, contact.relationship_score, span_days, False,
        )
        if contact.id not in candidates or priority > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="dormant_deep", priority=priority, pool="B",
            )

    # B2 — Mid-Dormant
    b2_max_cutoff = now - timedelta(days=B2_MAX_DORMANCY_YEARS * 365)
    b2_result = await db.execute(
        select(Contact, span_subq.c.span_seconds)
        .outerjoin(span_subq, Contact.id == span_subq.c.contact_id)
        .where(
            Contact.user_id == user_id,
            _not_2nd_tier,
            _has_channel,
            _not_archived,
            _has_nonzero_score,
            Contact.last_interaction_at.isnot(None),
            Contact.last_interaction_at < b1_min_cutoff,
            Contact.last_interaction_at >= b2_max_cutoff,
            Contact.interaction_count >= B2_MIN_INTERACTIONS,
            func.coalesce(span_subq.c.span_seconds, 0) >= B2_MIN_SPAN_DAYS * 86400,
        )
    )
    for contact, span_seconds in b2_result.all():
        if contact.id in queued_contact_ids:
            continue
        if contact.id in candidates:
            continue
        span_days = float(span_seconds or 0) / 86400.0
        priority = compute_priority_b(
            contact.interaction_count, contact.relationship_score, span_days, False,
        )
        if contact.id not in candidates or priority > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="dormant_mid", priority=priority, pool="B",
            )

    # B3 — Event Revival
    b3_event_cutoff = now - timedelta(days=B3_EVENT_WINDOW_DAYS)
    b3_result = await db.execute(
        select(DetectedEvent, Contact, span_subq.c.span_seconds)
        .join(Contact, DetectedEvent.contact_id == Contact.id)
        .outerjoin(span_subq, Contact.id == span_subq.c.contact_id)
        .where(
            Contact.user_id == user_id,
            _not_2nd_tier,
            _has_channel,
            _not_archived,
            _has_nonzero_score,
            _is_dormant,
            DetectedEvent.detected_at >= b3_event_cutoff,
            DetectedEvent.confidence > EVENT_CONFIDENCE_THRESHOLD,
            or_(
                Contact.interaction_count >= POOL_B_MIN_INTERACTIONS,
                Contact.relationship_score >= POOL_B_MIN_SCORE,
                func.coalesce(span_subq.c.span_seconds, 0) >= POOL_B_MIN_SPAN_DAYS * 86400,
            ),
        )
        .order_by(DetectedEvent.confidence.desc())
    )
    for event, contact, span_seconds in b3_result.all():
        if contact.id in queued_contact_ids:
            continue
        span_days = float(span_seconds or 0) / 86400.0
        priority = compute_priority_b(
            contact.interaction_count, contact.relationship_score, span_days, True,
        )
        if contact.id not in candidates or priority > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="dormant_event", event=event, priority=priority, pool="B",
            )

    # Apply hard cap
    to_remove = []
    for cid, cand in candidates.items():
        if cand.trigger_type == "dormant_event":
            continue
        contact = cand.contact
        if contact.last_interaction_at and contact.last_interaction_at < hard_cap_cutoff:
            to_remove.append(cid)
        elif contact.last_interaction_at is None:
            to_remove.append(cid)
    for cid in to_remove:
        del candidates[cid]

    return candidates
