"""Contact import service — generic CSV, LinkedIn Connections CSV, LinkedIn Messages CSV."""
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

from app.models.contact import Contact
from app.models.interaction import Interaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Name/org parsing helpers
# ---------------------------------------------------------------------------

# Patterns like "Jan | Safe Foundation", "Mickey @ Arcadia", "Alice / ACME Corp"
_NAME_ORG_RE = _re.compile(
    r"^(.+?)\s*(?:\||@|/|—|–|-\s)\s*(.+)$"
)


_SUFFIX_RE = _re.compile(
    r",?\s*\b(?:MBA|PhD|MD|CPA|CFA|PMP|Jr|Sr|II|III|IV|Esq|PE|RN|BSc|MSc)\b\.?",
    _re.IGNORECASE,
)
_NON_ALPHA_SPACE_RE = _re.compile(r"[^\w\s]", _re.UNICODE)
_MULTI_SPACE_RE = _re.compile(r"\s+")


def _normalize_linkedin_name(name: str) -> str:
    """Normalize a LinkedIn display name for fuzzy matching.

    Strips suffixes (MBA, PhD, etc.), special characters (★, emoji),
    collapses whitespace, and lowercases.
    """
    s = _SUFFIX_RE.sub("", name)
    s = "".join(c for c in s if not unicodedata.category(c).startswith(("So", "Sk")))
    s = _NON_ALPHA_SPACE_RE.sub(" ", s)
    s = _MULTI_SPACE_RE.sub(" ", s).strip().lower()
    return s


def parse_name_org(raw_name: str | None) -> tuple[str | None, str | None]:
    """Extract (clean_name, company) from a raw name that may contain an org separator.

    Recognises separators: |  @  /  —  –  and " - " (dash with spaces).
    Returns (name, None) if no separator found.
    """
    if not raw_name:
        return (None, None)
    raw = raw_name.strip()
    if not raw:
        return (None, None)
    m = _NAME_ORG_RE.match(raw)
    if m:
        name = m.group(1).strip()
        org = m.group(2).strip()
        if name and org:
            return (name, org)
    return (raw, None)


# ---------------------------------------------------------------------------
# Generic CSV import
# ---------------------------------------------------------------------------


async def import_csv(
    content_bytes: bytes,
    user_id: object,
    db: AsyncSession,
) -> dict[str, Any]:
    """Parse a generic contacts CSV and create Contact rows.

    Columns recognised (case-sensitive, matching the export format):
        full_name / name, given_name / first_name, family_name / last_name,
        emails (semicolon-separated), phones (semicolon-separated),
        company / organization, title / job_title,
        twitter_handle / twitter / x_handle,
        telegram_username / telegram,
        notes / note, tags (semicolon-separated).

    Returns a dict with keys ``created`` (list of dicts) and ``errors`` (list of str).
    """
    text = content_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    created: list[dict] = []
    errors: list[str] = []

    for i, row in enumerate(reader):
        try:
            raw_name = row.get("full_name") or row.get("name")
            csv_company = row.get("company") or row.get("organization")
            parsed_name, parsed_org = parse_name_org(raw_name)
            # Use parsed org only if no explicit company column value
            effective_company = csv_company or parsed_org

            contact = Contact(
                user_id=user_id,
                full_name=parsed_name,
                given_name=row.get("given_name") or row.get("first_name"),
                family_name=row.get("family_name") or row.get("last_name"),
                emails=[e.strip() for e in row.get("emails", "").split(";") if e.strip()],
                phones=[p.strip() for p in row.get("phones", "").split(";") if p.strip()],
                company=effective_company,
                title=row.get("title") or row.get("job_title"),
                twitter_handle=row.get("twitter_handle") or row.get("twitter") or row.get("x_handle"),
                telegram_username=row.get("telegram_username") or row.get("telegram"),
                notes=row.get("notes") or row.get("note"),
                tags=[t.strip() for t in row.get("tags", "").split(";") if t.strip()] or None,
                source="csv",
            )
            db.add(contact)
            await db.flush()

            from app.services.organization_service import auto_create_organization
            await auto_create_organization(contact, user_id, db)

            created.append({"id": str(contact.id), "full_name": contact.full_name})
        except Exception as exc:
            logger.warning("import_contacts_csv: failed to import row %d for user %s", i + 1, user_id, exc_info=True)
            errors.append(f"Row {i + 1}: {exc!s}")

    return {"created": created, "errors": errors}


# ---------------------------------------------------------------------------
# LinkedIn Connections CSV import
# ---------------------------------------------------------------------------


async def import_linkedin_connections(
    content_bytes: bytes,
    user_id: object,
    db: AsyncSession,
) -> dict[str, Any]:
    """Import a LinkedIn *Connections.csv* export.

    LinkedIn's CSV has notes/header lines before the real column header row
    that starts with "First Name,".  This function skips those preamble lines.

    Returns a dict with keys ``created`` (int), ``skipped`` (int), and
    ``errors`` (list of str).
    """
    text = content_bytes.decode("utf-8-sig")

    lines = text.split("\n")
    header_idx = 0
    for idx, line in enumerate(lines):
        if line.strip().startswith("First Name,"):
            header_idx = idx
            break

    csv_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(csv_text))

    created = 0
    skipped = 0
    errors: list[str] = []

    from app.services.sync_utils import sync_set_field

    for i, row in enumerate(reader):
        try:
            first = (row.get("First Name") or "").strip()
            last = (row.get("Last Name") or "").strip()
            email = (row.get("Email Address") or "").strip()
            company = (row.get("Company") or "").strip()
            position = (row.get("Position") or "").strip()
            url = (row.get("URL") or "").strip()

            if not first and not last:
                continue

            full_name = f"{first} {last}".strip()

            # Stable identifiers take precedence over (name, company), which drifts
            # whenever the contact changes jobs or another sync updates `company`.
            url_normalized = url.rstrip("/") if url else None
            slug = None
            if url_normalized:
                m = _re.search(r"/in/([^/?]+)", url_normalized)
                if m:
                    slug = m.group(1)

            existing_contact: Contact | None = None

            if slug:
                r = await db.execute(
                    select(Contact).where(
                        Contact.user_id == user_id,
                        Contact.linkedin_profile_id == slug,
                    )
                )
                existing_contact = r.scalars().first()

            if not existing_contact and url_normalized:
                r = await db.execute(
                    select(Contact).where(
                        Contact.user_id == user_id,
                        Contact.linkedin_url == url_normalized,
                    )
                )
                existing_contact = r.scalars().first()

            if not existing_contact and email:
                r = await db.execute(
                    select(Contact).where(
                        Contact.user_id == user_id,
                        Contact.emails.any(email),
                    )
                )
                existing_contact = r.scalars().first()

            # Last-resort name match — only when the row has no stable identifier.
            if not existing_contact and not url_normalized and not email:
                r = await db.execute(
                    select(Contact).where(
                        Contact.user_id == user_id,
                        Contact.full_name == full_name,
                        Contact.company == (company or None),
                    )
                )
                existing_contact = r.scalars().first()

            if existing_contact:
                if slug and not existing_contact.linkedin_profile_id:
                    existing_contact.linkedin_profile_id = slug
                if url_normalized and not existing_contact.linkedin_url:
                    existing_contact.linkedin_url = url_normalized
                if email and email not in (existing_contact.emails or []):
                    existing_contact.emails = [*(existing_contact.emails or []), email]
                if company:
                    sync_set_field(existing_contact, "company", company)
                if position:
                    sync_set_field(existing_contact, "title", position)
                skipped += 1
                continue

            contact = Contact(
                user_id=user_id,
                full_name=full_name,
                given_name=first or None,
                family_name=last or None,
                emails=[email] if email else [],
                company=company or None,
                title=position or None,
                linkedin_url=url_normalized,
                linkedin_profile_id=slug,
                source="linkedin",
            )
            db.add(contact)
            await db.flush()

            from app.services.organization_service import auto_create_organization
            await auto_create_organization(contact, user_id, db)

            created += 1
        except Exception as exc:
            logger.warning("import_linkedin_connections: failed to import row %d for user %s", i + 1, user_id, exc_info=True)
            errors.append(f"Row {i + 1}: {exc!s}")

    return {"created": created, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# LinkedIn Messages CSV import
# ---------------------------------------------------------------------------


async def import_linkedin_messages(
    content_bytes: bytes,
    user_id: object,
    user_name: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Import a LinkedIn *messages.csv* export, creating Interaction rows.

    Messages are matched to existing contacts by full_name (case-insensitive).
    Duplicate detection is done via the ``raw_reference_id`` field.

    Args:
        content_bytes: Raw bytes of the uploaded CSV file.
        user_id: Authenticated user's UUID.
        user_name: Lowercased display name / email of the current user,
                   used to identify which side of each message the user is on.
        db: Database session.

    Returns a dict with keys ``new_interactions`` (int), ``skipped`` (int),
    ``unmatched`` (int), and ``unmatched_names`` (list of str).
    """
    text = content_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # Load all contacts keyed by full_name (lowercased) + normalized name index
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

        # Determine the other party and direction
        if from_name.lower() == user_name:
            other_name = to_name
            direction = "outbound"
        elif to_name.lower() == user_name:
            other_name = from_name
            direction = "inbound"
        else:
            # Neither side matches the user — skip
            continue

        contact = contacts_by_name.get(other_name.lower())
        if not contact:
            contact = contacts_by_normalized.get(_normalize_linkedin_name(other_name))
        if not contact:
            unmatched_names.add(other_name)
            continue

        # Parse date
        try:
            occurred_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %Z").replace(tzinfo=UTC)
        except ValueError:
            try:
                occurred_at = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except ValueError:
                continue

        # Idempotent: check by reference id
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
            platform="linkedin",
            direction=direction,
            content_preview=content_preview[:500],
            raw_reference_id=ref_id,
            occurred_at=occurred_at,
        )
        db.add(interaction)
        new_interactions += 1

        # Update last_interaction_at
        if contact.last_interaction_at is None or contact.last_interaction_at < occurred_at:
            contact.last_interaction_at = occurred_at

    await db.flush()
    return {
        "new_interactions": new_interactions,
        "skipped": skipped,
        "unmatched": len(unmatched_names),
        "unmatched_names": sorted(unmatched_names)[:20],
    }
