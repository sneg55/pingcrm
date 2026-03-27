"""Twitter / X OAuth 2.0 PKCE token management for PingCRM."""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

_TOKEN_REFRESH_BUFFER_SECONDS = 300  # refresh 5 minutes before expiry


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for OAuth 2.0 PKCE."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_twitter_oauth2_url(state: str, code_challenge: str) -> str:
    """Build the Twitter OAuth 2.0 authorization URL (PKCE flow)."""
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": settings.TWITTER_CLIENT_ID,
        "redirect_uri": settings.TWITTER_REDIRECT_URI,
        "scope": "tweet.read users.read dm.read offline.access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"https://twitter.com/i/oauth2/authorize?{urlencode(params)}"


async def exchange_twitter_code(code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange an authorization code for OAuth 2.0 tokens."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.twitter.com/2/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.TWITTER_REDIRECT_URI,
                "code_verifier": code_verifier,
                "client_id": settings.TWITTER_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(settings.TWITTER_CLIENT_ID, settings.TWITTER_CLIENT_SECRET)
            if settings.TWITTER_CLIENT_SECRET
            else None,
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_twitter_token(refresh_token: str) -> dict[str, Any]:
    """Refresh an expired OAuth 2.0 access token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.twitter.com/2/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.TWITTER_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(settings.TWITTER_CLIENT_ID, settings.TWITTER_CLIENT_SECRET)
            if settings.TWITTER_CLIENT_SECRET
            else None,
        )
        resp.raise_for_status()
        return resp.json()


def store_tokens(user: User, tokens: dict[str, Any]) -> None:
    """Store OAuth tokens and compute expires_at from the response."""
    user.twitter_access_token = tokens["access_token"]
    if "refresh_token" in tokens:
        user.twitter_refresh_token = tokens["refresh_token"]
    expires_in = tokens.get("expires_in")
    if expires_in:
        user.twitter_token_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))


async def _user_bearer_headers(user: User, db: AsyncSession) -> dict[str, str] | None:
    """Get Bearer headers, proactively refreshing if the token is expired or about to expire.

    Checks twitter_token_expires_at and refreshes if within 5 minutes of expiry.
    Falls back to returning the stored token if no expiry is tracked.
    """
    if not user.twitter_access_token:
        return None

    # Proactive refresh: if we know the token is expired or about to expire, refresh now
    if user.twitter_token_expires_at is not None:
        if datetime.now(UTC) >= user.twitter_token_expires_at - timedelta(seconds=_TOKEN_REFRESH_BUFFER_SECONDS):
            logger.info("Twitter token expiring soon for user %s, proactively refreshing", user.id)
            refreshed = await _refresh_and_retry(user, db)
            if refreshed:
                return refreshed
            # If refresh failed, try the existing token anyway (might still work)

    return {"Authorization": f"Bearer {user.twitter_access_token}"}


async def _refresh_and_retry(user: User, db: AsyncSession) -> dict[str, str] | None:
    """Attempt to refresh an expired OAuth 2.0 token.

    Called when an API call returns 401. Creates a notification only if
    the refresh itself fails (not on transient network errors).
    """
    if not user.twitter_refresh_token:
        from app.models.notification import Notification
        db.add(Notification(
            user_id=user.id,
            notification_type="system",
            title="Twitter connection expired",
            body="Your Twitter access token has expired and no refresh token is available. Please reconnect in Settings.",
            link="/settings",
        ))
        await db.commit()
        return None

    # Lock to prevent concurrent refresh race condition:
    # Two Celery tasks (DM sync + activity poll) dispatch simultaneously.
    # The first rotates the refresh token; the second would use the old
    # (now-dead) token and get 400. Lock ensures only one refreshes.
    import redis as _redis
    from app.core.config import settings as _cfg
    _r = _redis.from_url(_cfg.REDIS_URL)
    lock_key = f"tw_refresh_lock:{user.id}"

    if not _r.set(lock_key, "1", nx=True, ex=30):
        # Another task is already refreshing — wait and re-read the user's token
        import asyncio
        await asyncio.sleep(2)
        await db.refresh(user)
        if user.twitter_access_token:
            return {"Authorization": f"Bearer {user.twitter_access_token}"}
        return None

    try:
        tokens = await refresh_twitter_token(user.twitter_refresh_token)
        store_tokens(user, tokens)
        # CRITICAL: commit immediately — Twitter rotates refresh tokens on each
        # use. If we only flush and the caller's transaction later rolls back,
        # the new refresh token is lost and the old one is already dead.
        await db.commit()
        _r.delete(lock_key)
        return {"Authorization": f"Bearer {tokens['access_token']}"}
    except httpx.HTTPStatusError as e:
        logger.error(
            "Twitter token refresh failed for user %s: %s %s",
            user.id,
            e.response.status_code,
            e.response.text[:200],
        )
        # Definitive auth failure (400/401): clear tokens to stop daily retry spam
        if e.response.status_code in (400, 401):
            user.twitter_access_token = None
            user.twitter_refresh_token = None
            user.twitter_token_expires_at = None
            logger.warning("Twitter tokens cleared for user %s (refresh permanently failed)", user.id)

            # Deduplicate: only create notification if none in last 24h
            from app.models.notification import Notification
            from datetime import UTC, datetime, timedelta
            from sqlalchemy import select, func
            recent = await db.execute(
                select(func.count()).where(
                    Notification.user_id == user.id,
                    Notification.title == "Twitter connection expired",
                    Notification.created_at >= datetime.now(UTC) - timedelta(hours=24),
                )
            )
            if recent.scalar_one() == 0:
                db.add(Notification(
                    user_id=user.id,
                    notification_type="system",
                    title="Twitter connection expired",
                    body="Failed to refresh your Twitter token. Please reconnect in Settings to restore Twitter sync.",
                    link="/settings",
                ))
            await db.commit()
        _r.delete(lock_key)
        return None
    except Exception:
        logger.exception("Twitter token refresh failed for user %s (network error)", user.id)
        _r.delete(lock_key)
        return None
