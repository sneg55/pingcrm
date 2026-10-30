import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_current_user, get_current_user_optional
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.integrations.google_auth import build_oauth_url, exchange_code
from app.models.google_account import GoogleAccount
from app.models.notification import Notification
from app.models.user import User
from app.schemas.responses import (
    DeletedData,
    Envelope,
    GoogleAccountData,
    OAuthUrlData,
    TokenData,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_GOOGLE_STATE_TTL_SECONDS = 600
_ANONYMOUS_STATE = "__anonymous__"


async def _store_google_state(state: str, user_id: str | None) -> None:
    r = get_redis()
    await r.setex(f"oauth_state:{state}", _GOOGLE_STATE_TTL_SECONDS, user_id or _ANONYMOUS_STATE)


async def _pop_google_state(state: str) -> str | None:
    r = get_redis()
    return await r.getdel(f"oauth_state:{state}")


@router.get("/google/accounts", response_model=Envelope[list[GoogleAccountData]])
async def list_google_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[list[GoogleAccountData]]:
    result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    accounts = [
        {"id": str(ga.id), "email": ga.email, "created_at": ga.created_at.isoformat()}
        for ga in result.scalars().all()
    ]
    return {"data": accounts, "error": None}


@router.delete("/google/accounts/{account_id}", response_model=Envelope[DeletedData])
async def remove_google_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[DeletedData]:
    try:
        aid = uuid.UUID(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account ID")

    result = await db.execute(
        select(GoogleAccount).where(
            GoogleAccount.id == aid,
            GoogleAccount.user_id == current_user.id,
        )
    )
    ga = result.scalar_one_or_none()
    if not ga:
        raise HTTPException(status_code=404, detail="Google account not found")

    await db.delete(ga)
    await db.flush()
    remaining = await db.execute(
        select(GoogleAccount.refresh_token)
        .where(GoogleAccount.user_id == current_user.id, GoogleAccount.id != ga.id)
        .order_by(GoogleAccount.created_at.desc())
        .limit(1)
    )
    current_user.google_refresh_token = remaining.scalar_one_or_none()
    return {"data": {"id": account_id, "deleted": True}, "error": None}


@router.get("/google/url", response_model=Envelope[OAuthUrlData])
async def google_oauth_url(
    current_user: User = Depends(get_current_user),
) -> Envelope[OAuthUrlData]:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env",
        )
    url, state = build_oauth_url(redirect_uri=settings.GOOGLE_REDIRECT_URI)
    await _store_google_state(state, str(current_user.id))
    return {"data": {"url": url, "state": state}, "error": None}


async def _keep_legacy_mailbox(caller: User, google_email: str, db: AsyncSession) -> None:
    if not caller.google_refresh_token or google_email.lower() == caller.email.lower():
        return
    existing = await db.execute(
        select(GoogleAccount.id).where(GoogleAccount.user_id == caller.id).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return
    db.add(GoogleAccount(
        user_id=caller.id,
        email=caller.email,
        refresh_token=caller.google_refresh_token,
    ))


class GoogleCallbackRequest(BaseModel):
    code: str
    state: str | None = None


@router.post("/google/callback", response_model=Envelope[TokenData])
async def google_callback(
    payload: GoogleCallbackRequest,
    db: AsyncSession = Depends(get_db),
    caller: User | None = Depends(get_current_user_optional),
) -> Envelope[TokenData]:
    if not payload.state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state parameter",
        )
    popped = await _pop_google_state(payload.state)
    if popped is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state parameter",
        )

    if popped == _ANONYMOUS_STATE or caller is None or str(caller.id) != popped:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user does not match the OAuth state",
        )

    try:
        tokens = exchange_code(payload.code)
    except Exception as exc:
        logger.error("Google code exchange failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange Google authorization code",
        )

    try:
        id_info = google_id_token.verify_oauth2_token(
            tokens["id_token"],
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        logger.error("Google ID token verification failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Google ID token",
        )

    google_email: str = id_info.get("email", "")
    if not google_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account does not provide an email address",
        )

    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        await _keep_legacy_mailbox(caller, google_email, db)
        caller.google_refresh_token = refresh_token
        ga_result = await db.execute(
            select(GoogleAccount).where(
                GoogleAccount.user_id == caller.id,
                GoogleAccount.email == google_email,
            )
        )
        ga = ga_result.scalar_one_or_none()
        if ga:
            ga.refresh_token = refresh_token
        else:
            db.add(GoogleAccount(
                user_id=caller.id,
                email=google_email,
                refresh_token=refresh_token,
            ))

    db.add(Notification(
        user_id=caller.id,
        notification_type="sync",
        title="Google account connected",
        body=f"Connected {google_email}",
        link="/settings",
    ))

    await db.flush()
    await db.refresh(caller)

    access_token = create_access_token(
        data={"sub": str(caller.id), "tv": caller.token_version},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"data": {"access_token": access_token, "token_type": "bearer"}, "error": None}
