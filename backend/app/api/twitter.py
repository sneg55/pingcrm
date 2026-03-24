"""Twitter OAuth 2.0 PKCE auth endpoints."""
import json
import logging
import secrets
import uuid as _uuid_mod

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_current_user
from app.core.database import get_db
from app.core.redis import get_redis
from app.integrations.twitter import (
    build_twitter_oauth2_url,
    exchange_twitter_code,
    generate_pkce_pair,
)
from app.models.user import User
from app.schemas.responses import Envelope, TwitterAuthUrlData, TwitterConnectedData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth/twitter", tags=["twitter-auth"])

_PKCE_TTL_SECONDS = 600  # 10 minutes


async def _store_pkce(state: str, verifier: str, user_id: str) -> None:
    r = get_redis()
    await r.setex(f"pkce:{state}", _PKCE_TTL_SECONDS, json.dumps({"verifier": verifier, "user_id": user_id}))


async def _pop_pkce(state: str) -> tuple[str, str] | None:
    r = get_redis()
    raw = await r.getdel(f"pkce:{state}")
    if raw is None:
        return None
    data = json.loads(raw)
    return data["verifier"], data["user_id"]


@router.get("/url", response_model=Envelope[TwitterAuthUrlData])
async def get_twitter_auth_url(
    current_user: User = Depends(get_current_user),
) -> Envelope[TwitterAuthUrlData]:
    """Return a Twitter OAuth 2.0 authorization URL."""
    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce_pair()
    await _store_pkce(state, verifier, str(current_user.id))

    url = build_twitter_oauth2_url(state=state, code_challenge=challenge)
    return {"data": {"url": url, "state": state}, "error": None}


class TwitterCallbackRequest(BaseModel):
    code: str
    state: str


@router.post("/callback", response_model=Envelope[TwitterConnectedData])
async def twitter_callback(
    body: TwitterCallbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[TwitterConnectedData]:
    """Exchange Twitter authorization code for tokens and store on user."""
    entry = await _pop_pkce(body.state)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    verifier, bound_user_id = entry

    # Verify the state belongs to the authenticated user
    if bound_user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="State does not belong to the authenticated user",
        )

    try:
        tokens = await exchange_twitter_code(body.code, verifier)
    except Exception as exc:
        logger.error("Twitter code exchange failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange Twitter authorization code",
        ) from exc

    from app.integrations.twitter import store_tokens
    store_tokens(current_user, tokens)

    # Fetch Twitter username
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            if resp.status_code == 200:
                user_data = resp.json().get("data", {})
                current_user.twitter_user_id = user_data.get("id") or current_user.twitter_user_id
                current_user.twitter_username = user_data.get("username")
    except Exception:
        logger.exception("Failed to fetch Twitter username for user %s", current_user.id)

    await db.flush()
    return {"data": {"connected": True, "username": current_user.twitter_username}, "error": None}


@router.delete("/disconnect", status_code=status.HTTP_200_OK)
async def disconnect_twitter(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Clear Twitter OAuth tokens and related data for the authenticated user."""
    current_user.twitter_access_token = None
    current_user.twitter_refresh_token = None
    current_user.twitter_username = None
    current_user.twitter_user_id = None
    current_user.twitter_dm_cursor = None
    current_user.twitter_token_expires_at = None
    await db.flush()
    return {"data": {"disconnected": True}, "error": None}
