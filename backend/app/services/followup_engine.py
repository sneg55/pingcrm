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

# Ghost detection only applies when the silence is fresh: 3 consecutive
# outbound messages 6 months ago aren't ghosting — that's exactly when a
# follow-up reminder is most useful. Apply the rule only if the contact's
# most recent interaction is within this window.
GHOST_RECENCY_DAYS = 30

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

    # Skip contacts whose suggestion was recently *user*-dismissed (30-day cooldown).
    # System dismissals (sync paths auto-clearing pending suggestions on new
    # activity) are NOT a user-rejection signal and must not lock contacts out.
    dismiss_cutoff = now - timedelta(days=30)
    dismissed_result = await db.execute(
        select(FollowUpSuggestion.contact_id).where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "dismissed",
            FollowUpSuggestion.updated_at >= dismiss_cutoff,
            FollowUpSuggestion.dismissed_by == "user",
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

    # Collect candidates from both pools. The user's configured dormancy
    # threshold defines the boundary: <= threshold = Pool A, > threshold = Pool B.
    # Lazy import to avoid circular dep — followup_pools imports from us.
    from app.services.followup_pools import (
        _collect_pool_a_candidates,
        _collect_pool_b_candidates,
    )

    _prefs = settings.get("suggestion_prefs", {})
    dormancy_days = int(_prefs.get("dormancy_threshold_days", DORMANCY_THRESHOLD_DAYS))
    pool_a = await _collect_pool_a_candidates(
        user_id, db, now, queued_contact_ids, priority_settings, dormancy_days=dormancy_days,
    )
    if _prefs.get("include_dormant", True):
        pool_b = await _collect_pool_b_candidates(
            user_id, db, now, queued_contact_ids, dormancy_days=dormancy_days,
        )
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

    # Ghost detection: suppress contacts where last N interactions are all outbound (no reply).
    # Only applies when the silence is fresh — see GHOST_RECENCY_DAYS. For older
    # outbound chains the contact is dormant, not ghosting, and a follow-up
    # reminder is exactly what the user wants.
    all_candidate_ids = set(pool_a.keys()) | set(pool_b.keys())
    if all_candidate_ids:
        from app.models.interaction import Interaction as _Interaction
        rn = func.row_number().over(
            partition_by=_Interaction.contact_id,
            order_by=_Interaction.occurred_at.desc(),
        ).label("rn")
        subq = (
            select(
                _Interaction.contact_id,
                _Interaction.direction,
                _Interaction.occurred_at,
                rn,
            )
            .where(
                _Interaction.contact_id.in_(all_candidate_ids),
                _Interaction.direction.in_(["inbound", "outbound"]),
            )
            .subquery()
        )
        ghost_result = await db.execute(
            select(subq.c.contact_id, subq.c.direction, subq.c.occurred_at)
            .where(subq.c.rn <= 3)
            .order_by(subq.c.contact_id, subq.c.rn)
        )
        # Group by contact_id; preserve order so position 0 is most recent.
        from collections import defaultdict
        recent: dict[uuid.UUID, list[tuple[str, datetime]]] = defaultdict(list)
        for row in ghost_result.all():
            recent[row[0]].append((row[1], row[2]))

        ghost_cutoff = now - timedelta(days=GHOST_RECENCY_DAYS)
        for cid, entries in recent.items():
            most_recent_at = entries[0][1]
            if most_recent_at and most_recent_at.tzinfo is None:
                most_recent_at = most_recent_at.replace(tzinfo=UTC)
            # Skip ghost rule entirely when the silence is old — the contact
            # is dormant, not ghosting, and follow-up is the right move.
            if not most_recent_at or most_recent_at < ghost_cutoff:
                continue
            consecutive_outbound = 0
            for direction, _occurred_at in entries:
                if direction == "outbound":
                    consecutive_outbound += 1
                else:
                    break
            if consecutive_outbound >= 3:
                pool_a.pop(cid, None)
                pool_b.pop(cid, None)
                logger.debug(
                    "generate_suggestions: skipping contact %s (ghosting — %d consecutive outbound, last %s)",
                    cid, consecutive_outbound, most_recent_at,
                )
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


# Re-export for backwards compatibility — get_weekly_digest moved to followup_digest.py
from app.services.followup_digest import get_weekly_digest  # noqa: E402,F401
