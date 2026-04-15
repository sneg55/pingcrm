"""Per-user bird CLI cookie management."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_extension_or_web_user
from app.core.database import get_db
from app.integrations.bird import verify_cookies
from app.models.user import User
from app.schemas.responses import Envelope, TwitterBirdStatusData

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/integrations/twitter/cookies",
    tags=["twitter-bird-cookies"],
)


class CookiesInput(BaseModel):
    auth_token: str = Field(min_length=1, max_length=512)
    ct0: str = Field(min_length=1, max_length=512)


@router.post("", response_model=Envelope[TwitterBirdStatusData])
async def push_cookies(
    body: CookiesInput,
    current_user: User = Depends(get_extension_or_web_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TwitterBirdStatusData]:
    current_user.twitter_bird_auth_token = body.auth_token
    current_user.twitter_bird_ct0 = body.ct0
    ok = await verify_cookies(body.auth_token, body.ct0)
    current_user.twitter_bird_status = "connected" if ok else "expired"
    current_user.twitter_bird_checked_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info(
        "bird cookies updated for user %s (status=%s)",
        current_user.id, current_user.twitter_bird_status,
    )
    return {
        "data": TwitterBirdStatusData(
            status=current_user.twitter_bird_status,
            checked_at=current_user.twitter_bird_checked_at,
        ),
        "error": None,
    }


@router.delete("", response_model=Envelope[TwitterBirdStatusData])
async def clear_cookies(
    current_user: User = Depends(get_extension_or_web_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TwitterBirdStatusData]:
    current_user.twitter_bird_auth_token = None
    current_user.twitter_bird_ct0 = None
    current_user.twitter_bird_status = "disconnected"
    current_user.twitter_bird_checked_at = None
    await db.flush()
    return {
        "data": TwitterBirdStatusData(status="disconnected", checked_at=None),
        "error": None,
    }


@router.get("", response_model=Envelope[TwitterBirdStatusData])
async def get_status(
    current_user: User = Depends(get_extension_or_web_user),
) -> Envelope[TwitterBirdStatusData]:
    return {
        "data": TwitterBirdStatusData(
            status=current_user.twitter_bird_status,
            checked_at=current_user.twitter_bird_checked_at,
        ),
        "error": None,
    }
