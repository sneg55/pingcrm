"""DB lookup/write helpers for the WhatsApp integration."""
from __future__ import annotations

import re as _re
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction

# Match @c.us and @s.whatsapp.net suffixes used by WhatsApp protocol IDs
_WA_SUFFIX_RE = _re.compile(r"@(?:c\.us|s\.whatsapp\.net)$")

# Characters to strip when normalising: spaces, dashes, parentheses, dots
_WA_NON_DIGIT_RE = _re.compile(r"[\s\-\(\)\.]")


def normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format.

    Strips @c.us / @s.whatsapp.net suffix, removes formatting characters
    (spaces, dashes, parentheses, dots), and ensures a leading '+'.
    """
    # Strip WhatsApp protocol suffixes
    phone = _WA_SUFFIX_RE.sub("", phone)
    # Remove formatting characters
    phone = _WA_NON_DIGIT_RE.sub("", phone)
    # Ensure leading '+'
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


async def find_contact_by_whatsapp_phone(
    phone: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Find a contact by the whatsapp_phone field (exact E.164 match)."""
    result = await db.execute(
        select(Contact)
        .where(
            Contact.user_id == user_id,
            Contact.whatsapp_phone == phone,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def find_contact_by_phone_list(
    phone: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Find a contact whose phones array contains the given number."""
    result = await db.execute(
        select(Contact)
        .where(
            Contact.user_id == user_id,
            Contact.phones.contains([phone]),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resolve_contact(
    phone: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    name: str | None = None,
) -> tuple[Contact, bool]:
    """Find or create a contact for the given WhatsApp phone number.

    Lookup order:
      1. whatsapp_phone field (exact match)
      2. phones array (contains match)
      3. Create a new contact

    Returns ``(contact, is_new)`` where *is_new* is True when a new contact
    was created.
    """
    # 1. Lookup by whatsapp_phone field
    contact = await find_contact_by_whatsapp_phone(phone, user_id, db)
    if contact:
        return contact, False

    # 2. Lookup by phones array
    contact = await find_contact_by_phone_list(phone, user_id, db)
    if contact:
        return contact, False

    # 3. Create new contact
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=name,
        whatsapp_phone=phone,
        whatsapp_name=name,
        phones=[phone],
        source="whatsapp",
    )
    db.add(contact)
    return contact, True


async def upsert_whatsapp_interaction(
    *,
    contact: Contact,
    user_id: uuid.UUID,
    message_id: str,
    direction: str,
    content_preview: str | None,
    occurred_at: datetime,
    db: AsyncSession,
) -> tuple[Interaction, bool]:
    """Create a WhatsApp interaction if it does not already exist.

    Deduplication is by ``raw_reference_id`` (= *message_id*) scoped to the
    contact and user.  The preview is truncated to 500 characters.

    Returns ``(interaction, is_new)``.
    """
    result = await db.execute(
        select(Interaction)
        .where(
            Interaction.raw_reference_id == message_id,
            Interaction.contact_id == contact.id,
            Interaction.user_id == user_id,
        )
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=user_id,
        platform="whatsapp",
        direction=direction,
        content_preview=content_preview[:500] if content_preview else None,
        raw_reference_id=message_id,
        occurred_at=occurred_at,
    )
    db.add(interaction)
    return interaction, True
