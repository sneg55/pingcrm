import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, func, case, distinct, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction


@dataclass
class ScoreBreakdown:
    total: int              # 0-10 composite
    reciprocity: int        # 0-4
    recency: int            # 0-3
    frequency: int          # 0-2
    breadth: int            # 0-1
    tenure: int = 0         # 0-2 (bonus for long-term contacts)
    inbound_365d: int = 0   # raw inbound count
    outbound_365d: int = 0  # raw outbound count
    count_30d: int = 0      # interactions in last 30d
    count_90d: int = 0      # interactions in 30-90d window
    platforms: list[str] = field(default_factory=list)  # distinct platform names
    interaction_count: int = 0  # lifetime total


def _compute_score_from_row(row, now: datetime) -> ScoreBreakdown:
    """Compute a ScoreBreakdown from a single aggregated row.

    Shared by both per-contact and batch scoring paths.
    """
    inbound_count = row.inbound or 0
    outbound_count = row.outbound or 0

    # Extended decay for reciprocity
    effective_inbound = inbound_count + (row.inbound_1_2y or 0) * 0.05 + (row.inbound_2_5y or 0) * 0.02
    effective_outbound = outbound_count + (row.outbound_1_2y or 0) * 0.05 + (row.outbound_2_5y or 0) * 0.02
    effective_total = effective_inbound + effective_outbound

    # Reciprocity (0-4)
    if effective_total == 0 or effective_inbound == 0:
        reciprocity = 0
    else:
        ratio = min(effective_inbound, effective_outbound) / max(effective_inbound, effective_outbound)
        reciprocity = round(ratio * 4)

    # Recency (0-3)
    last_inbound = row.last_inbound
    last_any = row.last_any
    if last_inbound is not None:
        base_date = last_inbound if last_inbound.tzinfo else last_inbound.replace(tzinfo=UTC)
        multiplier = 1.0
    elif last_any is not None:
        base_date = last_any if last_any.tzinfo else last_any.replace(tzinfo=UTC)
        multiplier = 0.5
    else:
        base_date = None
        multiplier = 0.0

    if base_date is not None:
        days_ago = (now - base_date).days
        if days_ago <= 7:
            raw = 3
        elif days_ago <= 30:
            raw = 2
        elif days_ago <= 90:
            raw = 1
        else:
            raw = 0
        recency = round(raw * multiplier)
    else:
        recency = 0

    # Frequency (0-2) with extended decay
    count_30d = row.c30 or 0
    count_90d = row.c90 or 0
    weighted = (
        count_30d * 1.0
        + count_90d * 0.3
        + (row.c365 or 0) * 0.1
        + (row.c1_2y or 0) * 0.05
        + (row.c2_5y or 0) * 0.02
    )
    if weighted >= 8:
        frequency = 2
    elif weighted >= 3:
        frequency = 1
    else:
        frequency = 0

    # Breadth (0-1)
    platforms = [p for p in (row.platforms or []) if p is not None]
    breadth = 1 if len(platforms) >= 2 else 0

    # Tenure bonus (0-2)
    interaction_count = row.lifetime_count or 0
    first_at = row.first_at
    tenure = 0
    if first_at is not None:
        first_date = first_at if first_at.tzinfo else first_at.replace(tzinfo=UTC)
        tenure_years = (now - first_date).days / 365.25
        if interaction_count >= 50 and tenure_years >= 2:
            tenure = 2
        elif interaction_count >= 20 and tenure_years >= 1:
            tenure = 1

    score = min(10, reciprocity + recency + frequency + breadth + tenure)

    return ScoreBreakdown(
        total=score,
        reciprocity=reciprocity,
        recency=recency,
        frequency=frequency,
        breadth=breadth,
        tenure=tenure,
        inbound_365d=inbound_count,
        outbound_365d=outbound_count,
        count_30d=count_30d,
        count_90d=count_90d,
        platforms=platforms,
        interaction_count=interaction_count,
    )


def _scoring_columns(now: datetime):
    """Return the SELECT columns for the unified scoring query."""
    d30 = now - timedelta(days=30)
    d90 = now - timedelta(days=90)
    d365 = now - timedelta(days=365)
    d2y = now - timedelta(days=730)
    d5y = now - timedelta(days=1825)

    return [
        # Reciprocity: inbound/outbound per time window
        func.count().filter(Interaction.direction == "inbound", Interaction.occurred_at >= d365).label("inbound"),
        func.count().filter(Interaction.direction == "outbound", Interaction.occurred_at >= d365).label("outbound"),
        func.count().filter(Interaction.direction == "inbound", Interaction.occurred_at >= d2y, Interaction.occurred_at < d365).label("inbound_1_2y"),
        func.count().filter(Interaction.direction == "outbound", Interaction.occurred_at >= d2y, Interaction.occurred_at < d365).label("outbound_1_2y"),
        func.count().filter(Interaction.direction == "inbound", Interaction.occurred_at >= d5y, Interaction.occurred_at < d2y).label("inbound_2_5y"),
        func.count().filter(Interaction.direction == "outbound", Interaction.occurred_at >= d5y, Interaction.occurred_at < d2y).label("outbound_2_5y"),
        # Recency: last inbound + last any
        func.max(case((Interaction.direction == "inbound", Interaction.occurred_at))).label("last_inbound"),
        func.max(Interaction.occurred_at).label("last_any"),
        # Frequency: time window counts
        func.count().filter(Interaction.occurred_at >= d30).label("c30"),
        func.count().filter(Interaction.occurred_at >= d90, Interaction.occurred_at < d30).label("c90"),
        func.count().filter(Interaction.occurred_at >= d365, Interaction.occurred_at < d90).label("c365"),
        func.count().filter(Interaction.occurred_at >= d2y, Interaction.occurred_at < d365).label("c1_2y"),
        func.count().filter(Interaction.occurred_at >= d5y, Interaction.occurred_at < d2y).label("c2_5y"),
        # Breadth + tenure
        func.array_agg(distinct(Interaction.platform)).label("platforms"),
        func.count().label("lifetime_count"),
        func.min(Interaction.occurred_at).label("first_at"),
    ]


async def calculate_score_breakdown(contact_id: uuid.UUID, db: AsyncSession) -> ScoreBreakdown:
    """Calculate full score breakdown for a single contact using 1 query.

    Includes tenure bonus and extended decay for long-term contacts.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(*_scoring_columns(now))
        .select_from(Interaction)
        .where(Interaction.contact_id == contact_id)
    )
    row = result.one()
    return _compute_score_from_row(row, now)


async def calculate_score(contact_id: uuid.UUID, db: AsyncSession) -> int:
    """Calculate and persist relationship score (0-10) for a contact."""
    breakdown = await calculate_score_breakdown(contact_id, db)

    contact_result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = contact_result.scalar_one_or_none()
    if contact:
        contact.relationship_score = breakdown.total
        contact.interaction_count = breakdown.interaction_count
        await db.flush()

    return breakdown.total


async def batch_update_scores(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Recalculate scores for ALL contacts of a user in a single query.

    Returns the number of contacts updated.
    """
    now = datetime.now(UTC)

    # Single query: aggregate all interactions grouped by contact_id
    result = await db.execute(
        select(Interaction.contact_id, *_scoring_columns(now))
        .where(
            Interaction.contact_id.in_(
                select(Contact.id).where(Contact.user_id == user_id)
            )
        )
        .group_by(Interaction.contact_id)
    )

    updated = 0
    for row in result.all():
        breakdown = _compute_score_from_row(row, now)
        await db.execute(
            update(Contact)
            .where(Contact.id == row.contact_id)
            .values(
                relationship_score=breakdown.total,
                interaction_count=breakdown.interaction_count,
            )
        )
        updated += 1

    return updated
