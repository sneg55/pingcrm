"""Centralized helper for dismissing pending follow-up suggestions when new
interactions arrive — with a recency filter that prevents backfilled old
messages from killing fresh suggestions.

The invariant: a suggestion is only dismissed when the contact has known
activity (Contact.last_interaction_at) on/after the suggestion's created_at.
Without this filter, a sync that imports a 2-year-old historical message
would dismiss a suggestion created moments earlier — combined with the
followup engine's 30-day post-dismiss cooldown (followup_engine.py:570-578),
this had emptied the prod suggestion queue.
"""
from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def dismiss_outdated_pending_suggestions(
    db: AsyncSession,
    contact_ids: Iterable[uuid.UUID],
    *,
    by: str = "system",
) -> int:
    """Dismiss pending suggestions for the given contacts, but only those
    whose ``created_at`` is on/before the contact's current
    ``last_interaction_at``. Returns the number of rows dismissed.

    The ``by`` parameter audits the dismissal source. Default is ``'system'``
    because every caller of this helper is a sync path; a user-driven
    dismissal goes through the explicit suggestions API endpoints. The
    followup engine's 30-day cooldown only applies to ``dismissed_by='user'``,
    so system dismissals don't lock contacts out.

    Callers must update ``Contact.last_interaction_at`` *before* invoking
    this — the integration code already does so as it inserts each new
    Interaction (taking max with any prior value). A backfilled old message
    can't push ``last_interaction_at`` higher than the existing max, so
    this filter naturally preserves fresh suggestions.
    """
    ids = list(contact_ids)
    if not ids:
        return 0
    result = await db.execute(
        text(
            """
            UPDATE follow_up_suggestions
            SET status = 'dismissed', updated_at = now(), dismissed_by = :by
            FROM contacts c
            WHERE follow_up_suggestions.contact_id = c.id
              AND follow_up_suggestions.contact_id = ANY(:ids)
              AND follow_up_suggestions.status = 'pending'
              AND c.last_interaction_at IS NOT NULL
              AND follow_up_suggestions.created_at <= c.last_interaction_at
            """
        ),
        {"ids": ids, "by": by},
    )
    return result.rowcount or 0
