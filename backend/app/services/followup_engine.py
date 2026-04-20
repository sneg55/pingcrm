"""Follow-Up Engine v2 — generates FollowUpSuggestion records for a user.

Two parallel pools:
- Pool A: maintains active relationships (recent contacts)
- Pool B: surfaces dormant contacts worth reviving (ranked by historical depth)
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.detected_event import DetectedEvent
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction
from app.models.user import User
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

# Minimum interactions required for a follow-up suggestion (per priority level)
MIN_INTERACTIONS_FOR_SUGGESTION = {"high": 1, "medium": 1, "low": 3}

# Score-0 contacts with no interaction in this many days are considered dead
STALE_CONTACT_DAYS = 365

# Priority scoring constants
COOLING_RECENT_DAYS = 14
COOLING_WINDOW_DAYS = 90
FOLLOWUP_COOLDOWN_DAYS = 14  # Don't re-suggest a contact within N days of last follow-up
RICH_HISTORY_THRESHOLD = 10
EVENT_TRIGGER_BONUS = 200

# Pool configuration
POOL_A_SLOTS = 3
POOL_B_SLOTS = 2
DORMANCY_THRESHOLD_DAYS = 365

# Pool B qualification
POOL_B_MIN_INTERACTIONS = 2
POOL_B_MIN_SCORE = 3
POOL_B_MIN_SPAN_DAYS = 30

# Pool B triggers
B1_MIN_INTERACTIONS = 5
B1_MIN_SCORE = 5
B1_MAX_DORMANCY_YEARS = 5
B2_MIN_INTERACTIONS = 2
B2_MIN_SPAN_DAYS = 0
B2_MAX_DORMANCY_YEARS = 3
B3_EVENT_WINDOW_DAYS = 14
POOL_B_EVENT_BONUS = 300
HARD_CAP_DORMANCY_YEARS = 5

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

# Exclude archived contacts
_not_archived = Contact.priority_level != "archived"


_SENDABLE_CHANNELS = {"email", "telegram", "twitter"}


@dataclass
class _Candidate:
    contact: Contact
    trigger_type: str
    event: DetectedEvent | None = None
    priority: float = 0.0
    pool: str = "A"


def compute_priority(
    interaction_count: int,
    days_since_interaction: float,
    is_event_trigger: bool,
) -> float:
    """Compute a priority score for a Pool A follow-up candidate.

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


def compute_priority_b(
    interaction_count: int,
    relationship_score: int,
    span_days: float,
    has_event: bool,
) -> float:
    """Compute a priority score for a Pool B (dormant revival) candidate.

    Depth-based, not recency-based:
    Tier 1 — Deep:       interactions >= 8 OR score >= 5   → 1000 + count
    Tier 2 — Solid:      interactions >= 4 OR score >= 3   → 500 + count
    Tier 3 — Qualifying: passes minimum depth              → 0 + count
    Bonus — Span:        span >= 180 days                  → +150
    Bonus — Event:       trigger B3                        → +300
    """
    base = float(interaction_count)

    if interaction_count >= 8 or relationship_score >= 5:
        score = 1000.0 + base
    elif interaction_count >= 4 or relationship_score >= 3:
        score = 500.0 + base
    else:
        score = base

    if span_days >= 180:
        score += 150.0

    if has_event:
        score += POOL_B_EVENT_BONUS

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


DEFAULT_PRIORITY_SETTINGS = {"high": 30, "medium": 60, "low": 180}


def _get_interval(priority_settings: dict | None, level: str) -> int:
    """Return the follow-up interval in days for a given priority level."""
    settings = priority_settings or DEFAULT_PRIORITY_SETTINGS
    return settings.get(level, DEFAULT_PRIORITY_SETTINGS.get(level, TIME_BASED_INACTIVITY_DAYS))


# -----------------------------------------------------------------------
# Pool A — Active relationships
# -----------------------------------------------------------------------


async def _collect_pool_a_candidates(
    user_id: uuid.UUID,
    db: AsyncSession,
    now: datetime,
    queued_contact_ids: set[uuid.UUID],
    priority_settings: dict | None = None,
) -> dict[uuid.UUID, _Candidate]:
    """Collect candidates from triggers 1-4 for active (non-dormant) contacts."""
    candidates: dict[uuid.UUID, _Candidate] = {}
    dormancy_cutoff = now - timedelta(days=DORMANCY_THRESHOLD_DAYS)

    # ------------------------------------------------------------------
    # Trigger 1: Time-based — no interaction in N+ days, score < 4, not dormant
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Trigger 2: Event-based — DetectedEvents in last 7 days, confidence > 0.7, not dormant
    # Skip contacts contacted in the last COOLING_RECENT_DAYS — even with
    # a noteworthy event, a follow-up 5 days after the last conversation
    # is too soon.
    # ------------------------------------------------------------------
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
            Contact.last_interaction_at < cooling_cutoff,  # respect cooldown
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

    # ------------------------------------------------------------------
    # Trigger 3: Scheduled — last_followup_at > N days ago, not dormant
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Trigger 4: Birthday — birthday within next 3 days (no dormancy filter)
    # ------------------------------------------------------------------
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
        mmdd = bday[-5:]  # last 5 chars = "MM-DD"
        if mmdd not in upcoming_mmdd:
            continue
        if contact.id not in candidates or 1500.0 > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="birthday", priority=1500.0, pool="A",
            )

    return candidates


# -----------------------------------------------------------------------
# Pool B — Dormant revival
# -----------------------------------------------------------------------


async def _collect_pool_b_candidates(
    user_id: uuid.UUID,
    db: AsyncSession,
    now: datetime,
    queued_contact_ids: set[uuid.UUID],
) -> dict[uuid.UUID, _Candidate]:
    """Collect candidates from dormant contacts worth reviving."""
    candidates: dict[uuid.UUID, _Candidate] = {}
    dormancy_cutoff = now - timedelta(days=DORMANCY_THRESHOLD_DAYS)
    hard_cap_cutoff = now - timedelta(days=HARD_CAP_DORMANCY_YEARS * 365)

    # Build interaction span subquery (CTE)
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

    # Base dormant filter: last_interaction_at IS NULL or < dormancy cutoff
    _is_dormant = or_(
        Contact.last_interaction_at.is_(None),
        Contact.last_interaction_at < dormancy_cutoff,
    )

    # Score-0 contacts are dead relationships — not worth reviving
    _has_nonzero_score = Contact.relationship_score > 0

    # ------------------------------------------------------------------
    # Trigger B1 — Deep Dormant
    # interaction_count >= 15 OR relationship_score >= 7
    # last_interaction_at between 1-5 years ago
    # ------------------------------------------------------------------
    b1_min_cutoff = now - timedelta(days=365)  # at least 1 year dormant
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

    # ------------------------------------------------------------------
    # Trigger B2 — Mid-Dormant
    # interaction_count >= 8 AND span >= 90 days
    # last_interaction_at between 1-3 years ago
    # ------------------------------------------------------------------
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
            continue  # B1 already captured this contact with higher priority
        span_days = float(span_seconds or 0) / 86400.0
        priority = compute_priority_b(
            contact.interaction_count, contact.relationship_score, span_days, False,
        )
        if contact.id not in candidates or priority > candidates[contact.id].priority:
            candidates[contact.id] = _Candidate(
                contact=contact, trigger_type="dormant_mid", priority=priority, pool="B",
            )

    # ------------------------------------------------------------------
    # Trigger B3 — Event Revival
    # DetectedEvent in last 14 days, confidence > 0.7
    # Must pass depth qualification (interaction_count >= 8 OR score >= 6 OR span >= 180d)
    # Overrides 5-year hard cap (can surface ancient contacts)
    # ------------------------------------------------------------------
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

    # Apply hard cap: exclude contacts dormant > 5 years UNLESS they have a B3 event trigger
    to_remove = []
    for cid, cand in candidates.items():
        if cand.trigger_type == "dormant_event":
            continue  # B3 overrides hard cap
        contact = cand.contact
        if contact.last_interaction_at and contact.last_interaction_at < hard_cap_cutoff:
            to_remove.append(cid)
        elif contact.last_interaction_at is None:
            to_remove.append(cid)
    for cid in to_remove:
        del candidates[cid]

    return candidates


# -----------------------------------------------------------------------
# Main orchestrator
# -----------------------------------------------------------------------


async def generate_suggestions(
    user_id: uuid.UUID,
    db: AsyncSession,
    priority_settings: dict | None = None,
) -> list[FollowUpSuggestion]:
    """Main follow-up engine entry point.

    Collects candidates from Pool A (active) and Pool B (dormant revival),
    applies budget with rollover, and creates FollowUpSuggestion records.

    Uses a Redis lock to prevent concurrent generation runs from creating
    duplicate suggestions (e.g. user clicks "Generate" twice quickly).

    Args:
        user_id: The user for whom suggestions are generated.
        db: Async database session (caller is responsible for commit).
        priority_settings: Per-priority follow-up intervals (e.g. {"high": 30, "medium": 60, "low": 180}).
            Also supports "pool_a_slots" and "pool_b_slots" overrides.

    Returns:
        List of newly created FollowUpSuggestion objects.
    """
    import redis as _redis
    from app.core.config import settings as _cfg

    r = _redis.from_url(_cfg.REDIS_URL)
    lock_key = f"suggestions_gen_lock:{user_id}"
    if not r.set(lock_key, "1", nx=True, ex=120):
        logger.info("generate_suggestions: skipped for user %s (concurrent run in progress)", user_id)
        return []

    try:
        return await _generate_suggestions_inner(user_id, db, priority_settings)
    finally:
        r.delete(lock_key)


async def _generate_suggestions_inner(
    user_id: uuid.UUID,
    db: AsyncSession,
    priority_settings: dict | None = None,
) -> list[FollowUpSuggestion]:
    """Inner implementation — called with lock held."""
    now = datetime.now(UTC)
    settings = priority_settings or {}

    # Load the user once so we can pass bird cookies down to the composer.
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    # Skip contacts that already have a pending or snoozed suggestion
    existing_result = await db.execute(
        select(FollowUpSuggestion.contact_id).where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status.in_(["pending", "snoozed"]),
        )
    )
    queued_contact_ids: set[uuid.UUID] = {row[0] for row in existing_result.all()}

    # Skip contacts whose suggestion was recently dismissed (30-day cooldown)
    dismiss_cutoff = now - timedelta(days=30)
    dismissed_result = await db.execute(
        select(FollowUpSuggestion.contact_id).where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "dismissed",
            FollowUpSuggestion.updated_at >= dismiss_cutoff,
        )
    )
    queued_contact_ids.update(row[0] for row in dismissed_result.all())

    # Skip contacts that were recently followed up (cooldown period)
    cooldown_cutoff = now - timedelta(days=FOLLOWUP_COOLDOWN_DAYS)
    recently_followed_up = await db.execute(
        select(Contact.id).where(
            Contact.user_id == user_id,
            Contact.last_followup_at.isnot(None),
            Contact.last_followup_at >= cooldown_cutoff,
        )
    )
    queued_contact_ids.update(row[0] for row in recently_followed_up.all())

    # Collect candidates from both pools
    pool_a = await _collect_pool_a_candidates(user_id, db, now, queued_contact_ids, priority_settings)
    # Respect include_dormant preference — skip Pool B if disabled
    _prefs = settings.get("suggestion_prefs", {})
    if _prefs.get("include_dormant", True):
        pool_b = await _collect_pool_b_candidates(user_id, db, now, queued_contact_ids)
    else:
        pool_b = {}

    # Read receipt filter: skip contacts whose last outbound Telegram message is unread,
    # boost priority for "read but no reply" pattern
    all_candidate_ids = set(pool_a.keys()) | set(pool_b.keys())
    if all_candidate_ids:
        from app.models.interaction import Interaction
        # Get the latest outbound Telegram interaction per contact using a subquery
        latest_outbound_sq = (
            select(
                Interaction.contact_id,
                Interaction.is_read_by_recipient,
            )
            .where(
                Interaction.contact_id.in_(all_candidate_ids),
                Interaction.platform == "telegram",
                Interaction.direction == "outbound",
                Interaction.is_read_by_recipient.isnot(None),
            )
            .distinct(Interaction.contact_id)
            .order_by(Interaction.contact_id, Interaction.occurred_at.desc())
        )
        unread_outbound = await db.execute(latest_outbound_sq)
        for row in unread_outbound.all():
            cid, is_read = row[0], row[1]
            if not is_read:
                # Last outbound message is unread — suppress this candidate
                pool_a.pop(cid, None)
                pool_b.pop(cid, None)
                logger.debug("generate_suggestions: skipping contact %s (unread outbound)", cid)
            elif is_read:
                # Read but no reply — boost priority (+100)
                if cid in pool_a:
                    pool_a[cid].priority += 100.0
                if cid in pool_b:
                    pool_b[cid].priority += 100.0

    # Ghost detection: suppress contacts where last N interactions are all outbound (no reply)
    # Single query using row_number() window function instead of N+1 per-contact queries
    all_candidate_ids = set(pool_a.keys()) | set(pool_b.keys())
    if all_candidate_ids:
        from app.models.interaction import Interaction as _Interaction
        from sqlalchemy import literal_column
        rn = func.row_number().over(
            partition_by=_Interaction.contact_id,
            order_by=_Interaction.occurred_at.desc(),
        ).label("rn")
        subq = (
            select(
                _Interaction.contact_id,
                _Interaction.direction,
                rn,
            )
            .where(
                _Interaction.contact_id.in_(all_candidate_ids),
                _Interaction.direction.in_(["inbound", "outbound"]),
            )
            .subquery()
        )
        ghost_result = await db.execute(
            select(subq.c.contact_id, subq.c.direction)
            .where(subq.c.rn <= 3)
            .order_by(subq.c.contact_id, subq.c.rn)
        )
        # Group by contact_id
        from collections import defaultdict
        recent_dirs: dict[uuid.UUID, list[str]] = defaultdict(list)
        for row in ghost_result.all():
            recent_dirs[row[0]].append(row[1])

        for cid, directions in recent_dirs.items():
            consecutive_outbound = 0
            for d in directions:
                if d == "outbound":
                    consecutive_outbound += 1
                else:
                    break
            if consecutive_outbound >= 3:
                pool_a.pop(cid, None)
                pool_b.pop(cid, None)
                logger.debug("generate_suggestions: skipping contact %s (ghosting — %d consecutive outbound)", cid, consecutive_outbound)
            elif consecutive_outbound == 2:
                if cid in pool_a:
                    pool_a[cid].priority *= 0.5
                if cid in pool_b:
                    pool_b[cid].priority *= 0.5

    # Sort each pool by priority descending
    sorted_a = sorted(pool_a.values(), key=lambda c: c.priority, reverse=True)
    sorted_b = sorted(pool_b.values(), key=lambda c: c.priority, reverse=True)

    # Budget: respect user's max_suggestions preference
    suggestion_prefs = settings.get("suggestion_prefs", {})
    max_total = suggestion_prefs.get("max_suggestions", POOL_A_SLOTS + POOL_B_SLOTS)
    # Split budget: 60% pool A, 40% pool B (rounded)
    a_budget = settings.get("pool_a_slots", max(1, round(max_total * 0.6)))
    b_budget = settings.get("pool_b_slots", max(1, max_total - max(1, round(max_total * 0.6))))

    actual_a = min(len(sorted_a), a_budget)
    actual_b = min(len(sorted_b), b_budget)

    # Distribute remaining slots
    remaining = (a_budget - actual_a) + (b_budget - actual_b)
    if remaining > 0:
        # Give remaining to whichever pool has surplus candidates
        extra_a = min(len(sorted_a) - actual_a, remaining)
        if extra_a > 0:
            actual_a += extra_a
            remaining -= extra_a
        extra_b = min(len(sorted_b) - actual_b, remaining)
        if extra_b > 0:
            actual_b += extra_b

    top_candidates = sorted_a[:actual_a] + sorted_b[:actual_b]

    # Create FollowUpSuggestion records for winners
    created: list[FollowUpSuggestion] = []
    for candidate in top_candidates:
        contact = candidate.contact
        try:
            channel = await _get_best_channel(contact.id, db)
            event_summary = candidate.event.summary if candidate.event else None
            is_revival = candidate.pool == "B"
            message = await compose_followup_message(
                contact_id=contact.id,
                trigger_type=candidate.trigger_type,
                event_summary=event_summary,
                db=db,
                revival_context=is_revival,
                user=user,
            )
            suggestion = FollowUpSuggestion(
                contact_id=contact.id,
                user_id=user_id,
                trigger_type=candidate.trigger_type,
                trigger_event_id=candidate.event.id if candidate.event else None,
                suggested_message=message,
                suggested_channel=channel,
                status="pending",
                pool=candidate.pool,
            )
            db.add(suggestion)
            await db.flush()
            await db.refresh(suggestion)
            created.append(suggestion)
            logger.info(
                "generate_suggestions: %s suggestion created for contact %s (pool=%s, priority=%.1f)",
                candidate.trigger_type, contact.id, candidate.pool, candidate.priority,
            )
        except Exception:
            logger.exception(
                "generate_suggestions: failed to create %s suggestion for contact %s",
                candidate.trigger_type, contact.id,
            )

    logger.info(
        "generate_suggestions: created %d suggestion(s) for user %s (pool_a=%d, pool_b=%d)",
        len(created), user_id,
        sum(1 for s in created if s.pool == "A"),
        sum(1 for s in created if s.pool == "B"),
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
