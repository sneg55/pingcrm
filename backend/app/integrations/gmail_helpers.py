"""Pure helpers for Gmail integration: header parsing, body extraction, BCC.

Kept separate from gmail.py so the main integration module stays focused on
the high-level sync orchestration.
"""
from __future__ import annotations

import base64
import email.utils
import logging
import re
import uuid
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact

logger = logging.getLogger(__name__)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Patterns for stripping quoted email text from snippets
_QUOTE_PATTERNS = [
    re.compile(r"\s*On\s+\w+\s+\d+,\s+\d{4}\s+at\s+\d+:\d+.*wrote:.*", re.DOTALL),
    re.compile(r"\s*On\s+\d{4}-\d{2}-\d{2}.*wrote:.*", re.DOTALL),
    re.compile(r"\s*--\s*\n.*", re.DOTALL),
    re.compile(r"\s*_{3,}.*", re.DOTALL),
    re.compile(r"\s*-{3,}\s*(Original Message|Forwarded).*", re.DOTALL | re.IGNORECASE),
]


def _clean_snippet(snippet: str) -> str:
    """Strip quoted reply text and signatures from an email snippet."""
    if not snippet:
        return ""
    text_out = snippet
    for pat in _QUOTE_PATTERNS:
        text_out = pat.split(text_out, 1)[0]
    return text_out.strip()


def _extract_plain_body(payload: dict) -> str:
    """Extract plain-text body from a Gmail message payload."""
    def _find_text_part(part: dict) -> str | None:
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                try:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                except Exception:
                    logger.warning(
                        "gmail body part decode failed",
                        extra={"provider": "gmail"},
                        exc_info=True,
                    )
                    return None
        for sub in part.get("parts", []):
            result = _find_text_part(sub)
            if result:
                return result
        return None

    body = _find_text_part(payload)
    if body:
        return body[:2000].strip()
    return ""


def _build_gmail_service(refresh_token: str) -> Any:
    """Build authenticated Gmail API service from a user's refresh token."""
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    return service


def _extract_header(headers: list[dict], name: str) -> str:
    """Extract a header value by name (case-insensitive)."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_email_addresses(header_value: str) -> list[str]:
    """Parse a comma-separated list of RFC 2822 email addresses."""
    if not header_value:
        return []
    addresses = []
    for _name, addr in email.utils.getaddresses([header_value]):
        addr = addr.strip().lower()
        if addr:
            addresses.append(addr)
    return addresses


_PLUS_ADDR_RE = re.compile(r"\+([a-f0-9]{7})@")


def _extract_bcc_hashes(addresses: list[str], user_email: str) -> list[str]:
    """Extract BCC hashes from +hash addresses matching the user's email domain."""
    if not user_email:
        return []
    local, _, domain = user_email.partition("@")
    if not domain:
        return []
    hashes = []
    for addr in addresses:
        if not addr.endswith(f"@{domain}"):
            continue
        m = _PLUS_ADDR_RE.search(addr)
        if m and addr.startswith(f"{local}+"):
            hashes.append(m.group(1))
    return hashes


async def _find_contact_by_bcc_hash(
    bcc_hash: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Look up a Contact by its BCC hash."""
    result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.bcc_hash == bcc_hash,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _find_contact_by_email(
    email_addr: str, user_id: uuid.UUID, db: AsyncSession
) -> Contact | None:
    """Look up a Contact whose emails list contains *email_addr*."""
    from app.services.contact_resolver import normalize_email
    norm = normalize_email(email_addr)
    if not norm:
        return None
    result = await db.execute(
        text(
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
        {"uid": user_id, "norm": norm},
    )
    row = result.first()
    if not row:
        return None
    return await db.get(Contact, row[0])
