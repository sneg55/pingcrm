"""Telegram authentication and sync endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telegram"])

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class TelegramConnectRequest(BaseModel):
    phone: str


class TelegramConnectResponse(BaseModel):
    phone_code_hash: str


class TelegramVerifyRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/auth/telegram/connect",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def telegram_connect(
    payload: TelegramConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Initiate Telegram login by sending an OTP to *phone*.

    The returned ``phone_code_hash`` must be passed back to
    ``POST /api/v1/auth/telegram/verify``.
    """
    from app.integrations.telegram import connect_telegram

    if not payload.phone or not payload.phone.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="phone is required",
        )

    try:
        phone_code_hash = await connect_telegram(current_user, payload.phone.strip(), db)
    except Exception as exc:
        logger.exception("telegram_connect failed for user %s.", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send Telegram OTP: {exc}",
        ) from exc

    await db.commit()
    return {"data": {"phone_code_hash": phone_code_hash}, "error": None}


@router.post(
    "/api/v1/auth/telegram/verify",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def telegram_verify(
    payload: TelegramVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Complete Telegram sign-in with the OTP code.

    On success the session is stored and the user is connected to Telegram.
    """
    from app.integrations.telegram import verify_telegram

    if not payload.phone or not payload.code or not payload.phone_code_hash:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="phone, code, and phone_code_hash are required",
        )

    try:
        await verify_telegram(
            current_user,
            payload.phone.strip(),
            payload.code.strip(),
            payload.phone_code_hash,
            db,
        )
    except Exception as exc:
        logger.exception("telegram_verify failed for user %s.", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telegram verification failed: {exc}",
        ) from exc

    await db.commit()
    return {"data": {"connected": True}, "error": None}


# ---------------------------------------------------------------------------
# Sync endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/contacts/sync/telegram",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def sync_telegram(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger a Telegram sync for the authenticated user.

    Fetches recent DM messages, matches counterparts to existing contacts,
    and creates Interaction records.
    """
    from app.integrations.telegram import sync_telegram_chats

    if not current_user.telegram_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram account not connected. Use /api/v1/auth/telegram/connect first.",
        )

    try:
        new_interactions = await sync_telegram_chats(current_user, db)
    except Exception as exc:
        logger.exception("sync_telegram failed for user %s.", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Telegram sync failed: {exc}",
        ) from exc

    await db.commit()
    return {"data": {"new_interactions": new_interactions}, "error": None}
