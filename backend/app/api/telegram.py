"""Telegram authentication and sync endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.responses import (
    Envelope,
    SyncStartedData,
    TelegramConnectData,
    TelegramConnectedData,
    TelegramVerifyData,
)

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


class Telegram2FARequest(BaseModel):
    password: str


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/auth/telegram/connect",
    response_model=Envelope[TelegramConnectData],
    status_code=status.HTTP_200_OK,
)
async def telegram_connect(
    payload: TelegramConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TelegramConnectData]:
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
        exc_name = type(exc).__name__
        if "PhoneNumberInvalid" in exc_name:
            detail = "Invalid phone number. Use international format, e.g. +14155552671"
        elif "FloodWait" in exc_name:
            detail = "Too many attempts. Please wait before trying again."
        elif "ApiIdInvalid" in exc_name:
            detail = "Telegram API credentials are invalid. Check TELEGRAM_API_ID and TELEGRAM_API_HASH."
        else:
            detail = "Failed to send Telegram OTP. Please try again."
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc

    await db.flush()
    return {"data": {"phone_code_hash": phone_code_hash}, "error": None}


@router.post(
    "/api/v1/auth/telegram/verify",
    response_model=Envelope[TelegramVerifyData],
    status_code=status.HTTP_200_OK,
)
async def telegram_verify(
    payload: TelegramVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TelegramVerifyData]:
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
        from telethon.errors import SessionPasswordNeededError

        if isinstance(exc, SessionPasswordNeededError):
            await db.flush()
            return {"data": {"connected": False, "requires_2fa": True}, "error": None}
        logger.exception("telegram_verify failed for user %s.", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram verification failed. Please check your code and try again.",
        ) from exc

    from app.models.notification import Notification as TgNotif
    db.add(TgNotif(
        user_id=current_user.id,
        notification_type="sync",
        title="Telegram account connected",
        body=f"Connected as @{current_user.telegram_username}" if current_user.telegram_username else "Account connected successfully",
        link="/settings",
    ))

    await db.flush()
    return {"data": {"connected": True, "username": current_user.telegram_username}, "error": None}


@router.post(
    "/api/v1/auth/telegram/verify-2fa",
    response_model=Envelope[TelegramConnectedData],
    status_code=status.HTTP_200_OK,
)
async def telegram_verify_2fa(
    payload: Telegram2FARequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TelegramConnectedData]:
    """
    Complete Telegram sign-in for accounts with two-step verification enabled.

    Must be called after ``/verify`` returns ``requires_2fa: true``.
    """
    from app.integrations.telegram import verify_telegram_2fa

    if not payload.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="password is required",
        )

    if not current_user.telegram_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active Telegram session. Start the connect flow first.",
        )

    try:
        await verify_telegram_2fa(current_user, payload.password, db)
    except Exception as exc:
        logger.exception("telegram_verify_2fa failed for user %s.", current_user.id)
        exc_name = type(exc).__name__
        if "PasswordHashInvalid" in exc_name:
            detail = "Incorrect 2FA password. Please try again."
        else:
            detail = "Telegram 2FA verification failed. Please try again."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc

    from app.models.notification import Notification as TgNotif2
    db.add(TgNotif2(
        user_id=current_user.id,
        notification_type="sync",
        title="Telegram account connected",
        body=f"Connected as @{current_user.telegram_username}" if current_user.telegram_username else "Account connected successfully",
        link="/settings",
    ))

    await db.flush()
    return {"data": {"connected": True, "username": current_user.telegram_username}, "error": None}


# ---------------------------------------------------------------------------
# Sync endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/contacts/sync/telegram",
    response_model=Envelope[SyncStartedData],
    status_code=status.HTTP_200_OK,
)
async def sync_telegram(
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
    """
    Dispatch a background Telegram sync for the authenticated user.

    Returns immediately with status "started". A notification is created
    when the sync completes.
    """
    if not current_user.telegram_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram account not connected. Use /api/v1/auth/telegram/connect first.",
        )

    from app.services.tasks import sync_telegram_chats_for_user, sync_telegram_notify
    from celery import chain
    user_id_str = str(current_user.id)
    chain(
        sync_telegram_chats_for_user.si(user_id_str, 100, ""),
        sync_telegram_notify.si(user_id_str, ""),
    ).apply_async()

    return {"data": {"status": "started"}, "error": None}


# ---------------------------------------------------------------------------
# Disconnect endpoint
# ---------------------------------------------------------------------------


@router.delete(
    "/api/v1/auth/telegram/disconnect",
    status_code=status.HTTP_200_OK,
)
async def disconnect_telegram(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Clear Telegram session and related data for the authenticated user."""
    current_user.telegram_session = None
    current_user.telegram_username = None
    current_user.telegram_last_synced_at = None
    await db.flush()
    return {"data": {"disconnected": True}, "error": None}


@router.post(
    "/api/v1/auth/telegram/reset-session",
    status_code=status.HTTP_200_OK,
)
async def reset_telegram_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Clear only the Telegram session (keeps username for re-connect)."""
    current_user.telegram_session = None
    current_user.telegram_last_synced_at = None
    await db.flush()
    return {"data": {"reset": True}, "error": None}


# ---------------------------------------------------------------------------
# Sync progress endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/telegram/sync-progress",
    status_code=status.HTTP_200_OK,
)
async def get_sync_progress(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return current Telegram sync progress for the authenticated user.

    Returns ``active: false`` when no sync is running or recently completed.
    """
    from app.services.sync_progress import get_progress

    progress = await get_progress(str(current_user.id))
    if not progress:
        return {"data": {"active": False}, "error": None}
    return {"data": {**progress, "active": progress.get("phase") != "done"}, "error": None}


# ---------------------------------------------------------------------------
# Common groups endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/contacts/{contact_id}/telegram/common-groups",
    response_model=Envelope[list[dict]],
    status_code=status.HTTP_200_OK,
)
async def get_common_groups(
    contact_id: str,
    force: bool = Query(False, description="Bypass cache and re-fetch from Telegram"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[list[dict]]:
    """Return Telegram groups in common with a contact.

    Results are cached on the contact. Auto-refreshes on contact detail visit
    if not already cached. Use force=true for manual refresh.
    """
    if not current_user.telegram_session:
        return {"data": [], "error": None}

    from sqlalchemy import select as sa_select
    from app.models.contact import Contact

    result = await db.execute(
        sa_select(Contact).where(
            Contact.id == contact_id,
            Contact.user_id == current_user.id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.telegram_username and not contact.telegram_user_id:
        return {"data": [], "error": None}

    from app.core.redis import get_redis
    r = get_redis()
    cache_key = f"tg_groups_check:{contact_id}"

    if not force and await r.exists(cache_key):
        return {"data": contact.telegram_common_groups or [], "error": None}

    from app.services.telegram_service import get_common_groups_cached

    groups = await get_common_groups_cached(contact, current_user, db, force=force)
    await r.setex(cache_key, 86400, "1")  # 24h
    return {"data": groups, "error": None}
