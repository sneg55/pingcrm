"""Organization auto-creation and domain matching service."""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization

AVATARS_DIR = Path(os.environ.get(
    "AVATARS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "static" / "avatars"),
))

logger = logging.getLogger(__name__)


async def download_org_logo(website_or_domain: str, org_id: uuid.UUID) -> str | None:
    """Download an organization's favicon/logo and save to static/avatars/.

    Tries favicon.ico directly first; falls back to parsing <link rel="icon">
    from the homepage HTML.

    Args:
        website_or_domain: A full URL (e.g. https://example.com) or bare domain
                           (e.g. example.com).
        org_id: The Organization UUID, used to name the saved file.

    Returns:
        The local URL path ``/static/avatars/org_{org_id}.png`` on success,
        or ``None`` on any failure.
    """
    # Normalise input to a full URL with http/https scheme only
    raw = website_or_domain.strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https"):
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        domain = parsed.netloc
    elif parsed.scheme == "":
        # Bare domain or path-only string — prepend https
        base_url = f"https://{raw.lstrip('/')}"
        domain = raw.split("/")[0]
    else:
        logger.warning("download_org_logo: rejected non-http/https scheme %r", parsed.scheme)
        return None

    if not domain:
        return None

    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"org_{org_id}.png"
    filepath = AVATARS_DIR / filename

    async def _save_bytes(content: bytes) -> str:
        filepath.write_bytes(content)
        return f"/static/avatars/{filename}"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # --- Attempt 1: direct favicon.ico ---
            favicon_url = f"{base_url}/favicon.ico"
            try:
                resp = await client.get(favicon_url)
                if resp.status_code == 200 and resp.content:
                    return await _save_bytes(resp.content)
            except Exception:
                logger.exception("Failed to download favicon.ico for org %s from %s", org_id, favicon_url)

            # --- Attempt 2: parse <link rel="icon"> from homepage HTML ---
            try:
                home_resp = await client.get(base_url)
                if home_resp.status_code == 200:
                    html = home_resp.text
                    # Simple regex-free scan for <link rel="icon"/"shortcut icon">
                    icon_href: str | None = None
                    import re
                    for pattern in [
                        r'<link[^>]+rel=["\'](?:shortcut icon|icon)["\'][^>]+href=["\']([^"\']+)["\']',
                        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'](?:shortcut icon|icon)["\']',
                    ]:
                        match = re.search(pattern, html, re.IGNORECASE)
                        if match:
                            icon_href = match.group(1).strip()
                            break

                    if icon_href:
                        # Resolve relative URLs
                        icon_url = urljoin(base_url, icon_href)
                        icon_parsed = urlparse(icon_url)
                        if icon_parsed.scheme not in ("http", "https"):
                            return None
                        icon_resp = await client.get(icon_url)
                        if icon_resp.status_code == 200 and icon_resp.content:
                            return await _save_bytes(icon_resp.content)
            except Exception:
                logger.exception("Failed to parse homepage icon for org %s from %s", org_id, base_url)

    except Exception:
        logger.debug("download_org_logo: failed for org %s / %s", org_id, website_or_domain)

    return None


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

    # Find existing org by name (case-insensitive) — use first() to handle duplicates
    result = await db.execute(
        select(Organization).where(
            Organization.user_id == user_id,
            Organization.name.ilike(company),
        ).limit(1)
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

        # Download logo for the newly created org
        if domain:
            logo_url = await download_org_logo(domain, org.id)
            if logo_url:
                org.logo_url = logo_url

    contact.organization_id = org.id

    # If org has no domain yet but contact has one, backfill it
    if not org.domain:
        domain = extract_domain_from_emails(contact.emails)
        if domain:
            org.domain = domain
            # Also try to fetch logo now that we have a domain
            if not org.logo_url:
                logo_url = await download_org_logo(domain, org.id)
                if logo_url:
                    org.logo_url = logo_url

    return org


async def backfill_org_logos(db: AsyncSession) -> int:
    """Backfill logos for all organizations missing one.

    Queries all orgs where logo_url IS NULL and domain or website is set,
    then calls download_org_logo for each.

    Args:
        db: An async SQLAlchemy session.

    Returns:
        The count of organizations whose logo_url was updated.
    """
    from sqlalchemy import or_

    result = await db.execute(
        select(Organization).where(
            Organization.logo_url.is_(None),
            or_(
                Organization.domain.isnot(None),
                Organization.website.isnot(None),
            ),
        )
    )
    orgs = list(result.scalars().all())

    updated = 0
    for org in orgs:
        logo_source = org.website or org.domain
        if not logo_source:
            continue
        logo_url = await download_org_logo(logo_source, org.id)
        if logo_url:
            org.logo_url = logo_url
            updated += 1

    if updated:
        logger.info("backfill_org_logos: updated %d organizations", updated)

    return updated


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
