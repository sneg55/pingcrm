"""Twitter OAuth 2.0 PKCE auth endpoints."""
import secrets
import time
import uuid as _uuid_mod

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_current_user
from app.core.database import get_db
from app.integrations.twitter import (
    build_twitter_oauth2_url,
    exchange_twitter_code,
    generate_pkce_pair,
)
from app.models.user import User

router = APIRouter(prefix="/api/v1/auth/twitter", tags=["twitter-auth"])

# In-memory store for PKCE verifiers (production: use Redis)
# Maps state -> (verifier, user_id, created_at)
_PKCE_TTL_SECONDS = 600  # 10 minutes
_pkce_store: dict[str, tuple[str, str, float]] = {}


def _prune_expired_pkce() -> None:
    now = time.time()
    expired = [k for k, (_, _, ts) in _pkce_store.items() if now - ts > _PKCE_TTL_SECONDS]
    for k in expired:
        del _pkce_store[k]


@router.get("/url", response_model=dict)
async def get_twitter_auth_url(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return a Twitter OAuth 2.0 authorization URL."""
    _prune_expired_pkce()
    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce_pair()
    _pkce_store[state] = (verifier, str(current_user.id), time.time())

    url = build_twitter_oauth2_url(state=state, code_challenge=challenge)
    return {"data": {"url": url, "state": state}, "error": None}


class TwitterCallbackRequest(BaseModel):
    code: str
    state: str


@router.post("/callback", response_model=dict)
async def twitter_callback(
    body: TwitterCallbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Exchange Twitter authorization code for tokens and store on user."""
    _prune_expired_pkce()
    entry = _pkce_store.pop(body.state, None)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    verifier, bound_user_id, created_at = entry

    # Verify the state belongs to the authenticated user
    if bound_user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="State does not belong to the authenticated user",
        )

    try:
        tokens = await exchange_twitter_code(body.code, verifier)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange code: {exc}",
        ) from exc

    current_user.twitter_access_token = tokens.get("access_token")
    if "refresh_token" in tokens:
        current_user.twitter_refresh_token = tokens["refresh_token"]

    await db.flush()
    return {"data": {"connected": True}, "error": None}
