import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, func, case, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction


async def calculate_score(contact_id: uuid.UUID, db: AsyncSession) -> int:
    """
    Calculate relationship score for a contact (0-10 scale).

    4 dimensions:
    - Reciprocity (0-4): inbound/outbound balance in last 365 days
    - Recency (0-3): time since last interaction, inbound-weighted
    - Frequency (0-2): weighted interaction count across time windows
    - Breadth (0-1): multi-platform communication
    """
    now = datetime.now(UTC)
    d30 = now - timedelta(days=30)
    d90 = now - timedelta(days=90)
    d365 = now - timedelta(days=365)

    # Query 1: inbound/outbound counts in last 365 days
    counts_result = await db.execute(
        select(
            func.count().filter(Interaction.direction == "inbound").label("inbound"),
            func.count().filter(Interaction.direction == "outbound").label("outbound"),
        )
        .select_from(Interaction)
        .where(
            Interaction.contact_id == contact_id,
            Interaction.occurred_at >= d365,
        )
    )
    row = counts_result.one()
    inbound_count = row.inbound
    outbound_count = row.outbound
    total = inbound_count + outbound_count

    # Reciprocity (0-4)
    if total == 0 or inbound_count == 0:
        reciprocity = 0
    else:
        ratio = min(inbound_count, outbound_count) / max(inbound_count, outbound_count)
        reciprocity = round(ratio * 4)

    # Query 2: last inbound date + last any date
    dates_result = await db.execute(
        select(
            func.max(
                case(
                    (Interaction.direction == "inbound", Interaction.occurred_at),
                )
            ).label("last_inbound"),
            func.max(Interaction.occurred_at).label("last_any"),
        )
        .select_from(Interaction)
        .where(Interaction.contact_id == contact_id)
    )
    dates_row = dates_result.one()
    last_inbound = dates_row.last_inbound
    last_any = dates_row.last_any

    # Recency (0-3)
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

    # Query 3: interaction counts per time window
    freq_result = await db.execute(
        select(
            func.count().filter(Interaction.occurred_at >= d30).label("c30"),
            func.count().filter(
                Interaction.occurred_at >= d90,
                Interaction.occurred_at < d30,
            ).label("c90"),
            func.count().filter(
                Interaction.occurred_at >= d365,
                Interaction.occurred_at < d90,
            ).label("c365"),
        )
        .select_from(Interaction)
        .where(
            Interaction.contact_id == contact_id,
            Interaction.occurred_at >= d365,
        )
    )
    freq_row = freq_result.one()
    weighted = freq_row.c30 * 1.0 + freq_row.c90 * 0.3 + freq_row.c365 * 0.1
    if weighted >= 8:
        frequency = 2
    elif weighted >= 3:
        frequency = 1
    else:
        frequency = 0

    # Query 4: distinct platform count
    platform_result = await db.execute(
        select(func.count(distinct(Interaction.platform)))
        .select_from(Interaction)
        .where(Interaction.contact_id == contact_id)
    )
    platform_count = platform_result.scalar_one()
    breadth = 1 if platform_count >= 2 else 0

    score = min(10, reciprocity + recency + frequency + breadth)

    # Total interaction count for persistence
    total_result = await db.execute(
        select(func.count())
        .select_from(Interaction)
        .where(Interaction.contact_id == contact_id)
    )
    interaction_count = total_result.scalar_one()

    # Persist updated score
    contact_result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = contact_result.scalar_one_or_none()
    if contact:
        contact.relationship_score = score
        contact.interaction_count = interaction_count
        await db.flush()

    return score
