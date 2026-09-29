from __future__ import annotations

import csv
import io
import logging
import re as _re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import Provider
from app.models.contact import Contact
from app.models.interaction import Interaction

logger = logging.getLogger(__name__)

_SUFFIX_RE = _re.compile(
    r",?\s*\b(?:MBA|PhD|MD|CPA|CFA|PMP|Jr|Sr|II|III|IV|Esq|PE|RN|BSc|MSc)\b\.?",
    _re.IGNORECASE,
)
_NON_ALPHA_SPACE_RE = _re.compile(r"[^\w\s]", _re.UNICODE)
_MULTI_SPACE_RE = _re.compile(r"\s+")


def _normalize_linkedin_name(name: str) -> str:
    s = _SUFFIX_RE.sub("", name)
    s = "".join(c for c in s if not unicodedata.category(c).startswith(("So", "Sk")))
    s = _NON_ALPHA_SPACE_RE.sub(" ", s)
    s = _MULTI_SPACE_RE.sub(" ", s).strip().lower()
    return s


async def import_linkedin_messages(
    content_bytes: bytes,
    user_id: object,
    user_name: str,
    db: AsyncSession,
) -> dict[str, Any]:
    text = content_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    all_contacts_result = await db.execute(
        select(Contact).where(Contact.user_id == user_id)
    )
    contacts_by_name: dict[str, Contact] = {}
    contacts_by_normalized: dict[str, Contact] = {}
    for c in all_contacts_result.scalars().all():
        if c.full_name:
            contacts_by_name[c.full_name.lower()] = c
            normalized = _normalize_linkedin_name(c.full_name)
            if normalized:
                contacts_by_normalized[normalized] = c

    new_interactions = 0
    skipped = 0
    unmatched_names: set[str] = set()

    for row in reader:
        from_name = (row.get("FROM") or "").strip()
        to_name = (row.get("TO") or "").strip()
        content_preview = (row.get("CONTENT") or "").strip()
        date_str = (row.get("DATE") or "").strip()
        conv_id = (row.get("CONVERSATION ID") or "").strip()

        if not content_preview or not date_str:
            continue

        if from_name.lower() == user_name:
            other_name = to_name
            direction = "outbound"
        elif to_name.lower() == user_name:
            other_name = from_name
            direction = "inbound"
        else:
            continue

        contact = contacts_by_name.get(other_name.lower())
        if not contact:
            contact = contacts_by_normalized.get(_normalize_linkedin_name(other_name))
        if not contact:
            unmatched_names.add(other_name)
            continue

        try:
            occurred_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %Z").replace(tzinfo=UTC)
        except ValueError:
            try:
                occurred_at = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except ValueError:
                logger.warning(
                    "import_linkedin_messages: skipping row with unparseable date %r for user %s",
                    date_str, user_id,
                )
                continue

        ref_id = f"linkedin:{conv_id}:{date_str}"
        existing = await db.execute(
            select(Interaction).where(
                Interaction.raw_reference_id == ref_id,
                Interaction.user_id == user_id,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        interaction = Interaction(
            contact_id=contact.id,
            user_id=user_id,
            platform=Provider.LINKEDIN,
            direction=direction,
            content_preview=content_preview[:500],
            raw_reference_id=ref_id,
            occurred_at=occurred_at,
        )
        db.add(interaction)
        new_interactions += 1

        if contact.last_interaction_at is None or contact.last_interaction_at < occurred_at:
            contact.last_interaction_at = occurred_at

    await db.flush()
    return {
        "new_interactions": new_interactions,
        "skipped": skipped,
        "unmatched": len(unmatched_names),
        "unmatched_names": sorted(unmatched_names)[:20],
    }
