"""Organization auto-creation and domain matching service."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization

logger = logging.getLogger(__name__)

GENERIC_EMAIL_DOMAINS: set[str] = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "yahoo.co.jp",
    "hotmail.com", "outlook.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me",
    "mail.ru", "yandex.ru", "yandex.com",
    "fastmail.com", "hey.com", "tutanota.com", "tutamail.com",
    "zoho.com", "gmx.com", "gmx.net", "inbox.com", "mail.com",
    "qq.com", "163.com", "126.com", "sina.com",
}


def is_generic_email_domain(domain: str) -> bool:
    """Return True if the domain belongs to a generic email provider."""
    return domain.lower().strip() in GENERIC_EMAIL_DOMAINS


def extract_domain_from_emails(emails: list[str] | None) -> str | None:
    """Extract the first non-generic email domain from a list of emails."""
    if not emails:
        return None
    for email in emails:
        if "@" in email:
            domain = email.rsplit("@", 1)[1].lower().strip()
            if domain and not is_generic_email_domain(domain):
                return domain
    return None


async def auto_create_organization(
    contact: Contact, user_id: uuid.UUID, db: AsyncSession
) -> Organization | None:
    """Find or create an Organization for a contact based on its company name.

    If the contact has a company name but no organization_id, find an existing
    org by name (case-insensitive) or create a new one.  Sets contact.organization_id.

    Returns the Organization or None if contact has no company.
    """
    company = (contact.company or "").strip()
    if not company:
        return None

    if contact.organization_id:
        # Already assigned
        result = await db.execute(
            select(Organization).where(Organization.id == contact.organization_id)
        )
        return result.scalar_one_or_none()

    # Find existing org by name (case-insensitive)
    result = await db.execute(
        select(Organization).where(
            Organization.user_id == user_id,
            Organization.name.ilike(company),
        )
    )
    org = result.scalar_one_or_none()

    if not org:
        domain = extract_domain_from_emails(contact.emails)
        org = Organization(
            user_id=user_id,
            name=company,
            domain=domain,
        )
        db.add(org)
        await db.flush()
        logger.info("Auto-created organization '%s' (id=%s) for user %s", company, org.id, user_id)

    contact.organization_id = org.id

    # If org has no domain yet but contact has one, backfill it
    if not org.domain:
        domain = extract_domain_from_emails(contact.emails)
        if domain:
            org.domain = domain

    return org


async def auto_assign_by_domain(
    organization: Organization, db: AsyncSession
) -> int:
    """Assign unlinked contacts to this organization by matching email domain.

    Finds all contacts belonging to the same user that:
    - Have no organization_id set
    - Have an email matching the organization's domain

    Returns the number of contacts assigned.
    """
    if not organization.domain:
        return 0

    domain_pattern = f"%@{organization.domain}"

    # Find contacts with matching email domain and no org
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == organization.user_id,
            Contact.organization_id.is_(None),
            Contact.emails.any(domain_pattern),
        )
    )
    contacts = list(result.scalars().all())

    count = 0
    for contact in contacts:
        # Verify at least one email actually matches (array ANY is broad)
        if contact.emails:
            for email in contact.emails:
                if "@" in email and email.rsplit("@", 1)[1].lower().strip() == organization.domain:
                    contact.organization_id = organization.id
                    # Also set company name if missing
                    if not contact.company:
                        contact.company = organization.name
                    count += 1
                    break

    if count:
        logger.info(
            "Auto-assigned %d contacts to organization '%s' (domain=%s)",
            count, organization.name, organization.domain,
        )

    return count
