from __future__ import annotations

import csv
import io
import logging
import re as _re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.services.linkedin_connections_import import import_linkedin_connections
from app.services.linkedin_messages_import import (
    _normalize_linkedin_name,
    import_linkedin_messages,
)

__all__ = [
    "_normalize_linkedin_name",
    "import_csv",
    "import_linkedin_connections",
    "import_linkedin_messages",
    "parse_name_org",
]

logger = logging.getLogger(__name__)

_NAME_ORG_RE = _re.compile(
    r"^(.+?)\s*(?:\||@|/|—|–|-\s)\s*(.+)$"
)


def parse_name_org(raw_name: str | None) -> tuple[str | None, str | None]:
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


async def import_csv(
    content_bytes: bytes,
    user_id: object,
    db: AsyncSession,
) -> dict[str, Any]:
    text = content_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    created: list[dict] = []
    errors: list[str] = []

    from app.services.contact_resolver import (
        find_or_create_contact_by_email,
        find_or_create_contact_by_telegram_username,
        find_or_create_contact_by_twitter_handle,
    )

    for i, row in enumerate(reader):
        try:
            async with db.begin_nested():
                raw_name = row.get("full_name") or row.get("name")
                csv_company = row.get("company") or row.get("organization")
                parsed_name, parsed_org = parse_name_org(raw_name)
                effective_company = csv_company or parsed_org

                row_emails = [e.strip() for e in row.get("emails", "").split(";") if e.strip()]
                row_phones = [p.strip() for p in row.get("phones", "").split(";") if p.strip()]
                row_tags = [t.strip() for t in row.get("tags", "").split(";") if t.strip()] or None
                twitter_handle = row.get("twitter_handle") or row.get("twitter") or row.get("x_handle")
                telegram_username = row.get("telegram_username") or row.get("telegram")

                base_defaults = dict(
                    full_name=parsed_name,
                    given_name=row.get("given_name") or row.get("first_name"),
                    family_name=row.get("family_name") or row.get("last_name"),
                    emails=row_emails,
                    phones=row_phones,
                    company=effective_company,
                    title=row.get("title") or row.get("job_title"),
                    twitter_handle=twitter_handle or None,
                    telegram_username=telegram_username or None,
                    notes=row.get("notes") or row.get("note"),
                    tags=row_tags,
                    source="csv",
                )

                contact = None
                if row_emails:
                    contact, _ = await find_or_create_contact_by_email(
                        db, user_id, row_emails[0], defaults=base_defaults,
                    )
                elif twitter_handle:
                    contact, _ = await find_or_create_contact_by_twitter_handle(
                        db, user_id, twitter_handle, defaults=base_defaults,
                    )
                elif telegram_username:
                    contact, _ = await find_or_create_contact_by_telegram_username(
                        db, user_id, telegram_username, defaults=base_defaults,
                    )
                else:
                    contact = Contact(user_id=user_id, **base_defaults)
                    db.add(contact)
                    await db.flush()

                from app.services.organization_service import auto_create_organization
                await auto_create_organization(contact, user_id, db)

            created.append({"id": str(contact.id), "full_name": contact.full_name})
        except Exception as exc:
            logger.warning("import_contacts_csv: failed to import row %d for user %s", i + 1, user_id, exc_info=True)
            errors.append(f"Row {i + 1}: {exc!s}")

    return {"created": created, "errors": errors}
