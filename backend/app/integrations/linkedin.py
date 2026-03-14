"""LinkedIn integration helpers for Ping CRM."""
from __future__ import annotations

import logging
import os
import urllib.parse
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

AVATARS_DIR = Path(os.environ.get(
    "AVATARS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "static" / "avatars"),
))

ALLOWED_AVATAR_DOMAINS = {
    "media.licdn.com",
    "static.licdn.com",
    "media-exp1.licdn.com",
    "media-exp2.licdn.com",
}


async def download_linkedin_avatar(
    profile_image_url: str, contact_id: str, db: object = None
) -> str | None:
    """Download a LinkedIn profile image and save to static/avatars/.

    Only fetches from known LinkedIn CDN domains to prevent SSRF.
    Returns the local URL path (e.g. ``/static/avatars/{contact_id}.jpg``),
    or ``None`` on failure.

    Args:
        profile_image_url: The LinkedIn CDN URL for the profile image.
        contact_id: The contact's UUID string (used as the filename).
        db: Unused; accepted for API symmetry with other avatar helpers.
    """
    parsed = urllib.parse.urlparse(profile_image_url)
    if parsed.hostname not in ALLOWED_AVATAR_DOMAINS:
        logger.warning(
            "download_linkedin_avatar: rejected URL with disallowed domain %r for contact %s",
            parsed.hostname,
            contact_id,
        )
        return None
    try:
        AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{contact_id}.jpg"
        filepath = AVATARS_DIR / filename
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(profile_image_url)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
        logger.debug(
            "download_linkedin_avatar: saved avatar for contact %s to %s",
            contact_id,
            filepath,
        )
        return f"/static/avatars/{filename}"
    except Exception:
        logger.debug(
            "download_linkedin_avatar: failed to download LinkedIn avatar for contact %s",
            contact_id,
        )
    return None
