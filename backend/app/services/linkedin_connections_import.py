from __future__ import annotations

import csv
import io
import logging
import re as _re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import Provider
from app.models.contact import Contact

logger = logging.getLogger(__name__)


async def import_linkedin_connections(
    content_bytes: bytes,
    user_id: object,
    db: AsyncSession,
) -> dict[str, Any]:
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
            async with db.begin_nested():
                first = (row.get("First Name") or "").strip()
                last = (row.get("Last Name") or "").strip()
                email = (row.get("Email Address") or "").strip()
                company = (row.get("Company") or "").strip()
                position = (row.get("Position") or "").strip()
                url = (row.get("URL") or "").strip()

                if not first and not last:
                    continue

                full_name = f"{first} {last}".strip()

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
                    from sqlalchemy import text as _sql_text
                    from app.services.contact_resolver import normalize_email
                    email_norm = normalize_email(email)
                    if email_norm:
                        r = await db.execute(
                            _sql_text(
                                """
                                SELECT id FROM contacts
                                WHERE user_id = :uid
                                  AND EXISTS (
                                    SELECT 1 FROM unnest(emails) e
                                    WHERE lower(trim(e)) = :norm
                                  )
                                LIMIT 1
                                """
                            ),
                            {"uid": user_id, "norm": email_norm},
                        )
                        row = r.first()
                        if row:
                            existing_contact = await db.get(Contact, row[0])

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
                    source=Provider.LINKEDIN,
                )
                db.add(contact)
                await db.flush()

                from app.services.organization_service import auto_create_organization
                await auto_create_organization(contact, user_id, db)

            created += 1
        except Exception as exc:
            logger.warning("import_linkedin_connections: failed to import row %d for user %s", i + 1, user_id, exc_info=True)
            errors.append(f"Row {i + 1}: {exc!s}")

    if created > 0:
        try:
            from app.services.identity_resolution import find_deterministic_matches
            async with db.begin_nested():
                merged = await find_deterministic_matches(user_id, db)
            if merged:
                logger.info(
                    "linkedin import: auto-merged %d duplicate(s) for user %s",
                    len(merged), user_id,
                )
        except Exception:
            logger.warning(
                "linkedin import: auto-merge failed for user %s", user_id, exc_info=True
            )

    return {"created": created, "skipped": skipped, "errors": errors}
