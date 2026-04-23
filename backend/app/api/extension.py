"""LinkedIn Chrome Extension pairing endpoints."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.models.extension_pairing import ExtensionPairing
from app.models.user import User
from app.schemas.responses import Envelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/extension", tags=["extension"])

_PAIRING_TTL_MINUTES = 10
_EXTENSION_TOKEN_EXPIRE_DAYS = 30
_MAX_POLL_ATTEMPTS = 20
# Grace window for silent refresh: a token may be refreshed up to this long
# past its `exp` claim. Caps exposure from leaked tokens while still letting
# normal users who opened their laptop after a few weeks stay paired.
_REFRESH_GRACE_DAYS = 90


def _create_extension_token(user_id: str) -> str:
    """Create a scoped JWT for the extension (aud: pingcrm-extension, 30-day expiry)."""
    from jose import jwt

    payload = {
        "sub": user_id,
        "aud": "pingcrm-extension",
        "exp": datetime.now(UTC) + timedelta(days=_EXTENSION_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


class PairRequest(BaseModel):
    code: str


class PairTokenResponse(BaseModel):
    token: str
    api_url: str


@router.post("/pair", response_model=Envelope[dict])
async def create_pairing(
    body: PairRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Authenticated user submits a pairing code from the extension popup.

    Creates an ExtensionPairing record with a scoped JWT, and marks
    the user's linkedin_extension_paired_at timestamp.
    """
    code = body.code.strip().upper()

    # Check for existing pairing with this code
    result = await db.execute(
        select(ExtensionPairing).where(ExtensionPairing.code == code)
    )
    existing = result.scalar_one_or_none()

    now = datetime.now(UTC)

    if existing is not None:
        # Reject if already claimed or expired
        if existing.claimed_at is not None:
            raise HTTPException(status_code=409, detail="Pairing code already claimed")
        if existing.expires_at <= now:
            raise HTTPException(status_code=410, detail="Pairing code expired")
        if existing.user_id != current_user.id:
            raise HTTPException(status_code=409, detail="Pairing code in use by another user")
        # Same user re-submitted the same code — idempotent, update token
        existing.token = _create_extension_token(str(current_user.id))
        existing.expires_at = now + timedelta(minutes=_PAIRING_TTL_MINUTES)
    else:
        token = _create_extension_token(str(current_user.id))
        pairing = ExtensionPairing(
            code=code,
            user_id=current_user.id,
            token=token,
            expires_at=now + timedelta(minutes=_PAIRING_TTL_MINUTES),
        )
        db.add(pairing)

    current_user.linkedin_extension_paired_at = now
    await db.flush()

    return {"data": {"status": "ok"}, "error": None, "meta": None}


@router.get("/pair", response_model=Envelope[PairTokenResponse])
async def poll_pairing(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Unauthenticated endpoint polled by the extension after the user enters their code.

    Returns the scoped JWT when the pairing is ready.
    Increments attempt counter to prevent brute-force enumeration.
    """
    code = code.strip().upper()

    result = await db.execute(
        select(ExtensionPairing).where(ExtensionPairing.code == code)
    )
    pairing = result.scalar_one_or_none()

    if pairing is None:
        raise HTTPException(status_code=404, detail="Pairing code not found")

    now = datetime.now(UTC)

    if pairing.expires_at <= now and pairing.claimed_at is None:
        raise HTTPException(status_code=410, detail="Pairing code expired")

    # Increment on every poll of an existing code (before limit check)
    pairing.attempts += 1

    if pairing.attempts > _MAX_POLL_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts")

    # First successful poll: mark claimed
    if pairing.claimed_at is None:
        pairing.claimed_at = now

    await db.flush()

    # Use the request's own base URL (the backend the extension is polling)
    # Force HTTPS — behind a reverse proxy, base_url reports http://
    api_url = str(request.base_url).rstrip("/").replace("http://", "https://")

    return {
        "data": PairTokenResponse(token=pairing.token, api_url=api_url),
        "error": None,
        "meta": None,
    }


class RefreshRequest(BaseModel):
    token: str


@router.post("/refresh", response_model=Envelope[PairTokenResponse])
async def refresh_extension_token(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Exchange a (possibly expired) extension JWT for a fresh one.

    Accepts tokens whose `exp` is within the past `_REFRESH_GRACE_DAYS`. Rejects
    tokens without the extension audience, tokens older than the grace window,
    and users who have disconnected the extension (linkedin_extension_paired_at
    is NULL). On permanent rejection with a resolvable user, also clears
    `linkedin_extension_paired_at` so the web UI reverts to a "Connect" state
    without requiring a manual disconnect.
    """
    credentials_exception = HTTPException(status_code=401, detail="Invalid refresh token")

    try:
        payload = jwt.decode(
            body.token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience="pingcrm-extension",
            options={"verify_exp": False},
        )
    except JWTError:
        raise credentials_exception

    exp = payload.get("exp")
    user_id = payload.get("sub")
    if exp is None or user_id is None:
        raise credentials_exception

    now = datetime.now(UTC)
    cutoff = now - timedelta(days=_REFRESH_GRACE_DAYS)
    if exp < cutoff.timestamp():
        # Token is too old to refresh — treat as permanently disconnected.
        # Commit the cleanup in an isolated session so it survives the 401.
        await _mark_user_disconnected(user_id)
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.linkedin_extension_paired_at is None:
        raise credentials_exception

    new_token = _create_extension_token(str(user.id))
    user.linkedin_extension_paired_at = now
    await db.flush()

    api_url = str(request.base_url).rstrip("/").replace("http://", "https://")
    return {
        "data": PairTokenResponse(token=new_token, api_url=api_url),
        "error": None,
        "meta": None,
    }


async def _mark_user_disconnected(user_id: str) -> None:
    """Best-effort clear of `linkedin_extension_paired_at` for a dead token.

    Runs in its own session so the write commits even when the caller raises
    HTTPException (which would rollback the request-scoped session).
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is not None and user.linkedin_extension_paired_at is not None:
                user.linkedin_extension_paired_at = None
                await session.commit()
    except Exception:
        logger.warning(
            "refresh cleanup failed",
            extra={"provider": "extension", "user_id": user_id},
            exc_info=True,
        )


@router.delete("/pair", response_model=Envelope[dict])
async def disconnect_extension(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Authenticated endpoint to disconnect the extension.

    Deletes all pairing records for the user and clears linkedin_extension_paired_at.
    """
    await db.execute(
        delete(ExtensionPairing).where(ExtensionPairing.user_id == current_user.id)
    )
    current_user.linkedin_extension_paired_at = None
    await db.flush()

    return {"data": {"status": "ok"}, "error": None, "meta": None}
