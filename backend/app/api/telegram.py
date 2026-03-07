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


class Telegram2FARequest(BaseModel):
    password: str


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
        exc_name = type(exc).__name__
        if "PhoneNumberInvalid" in exc_name:
            detail = "Invalid phone number. Use international format, e.g. +14155552671"
        elif "FloodWait" in exc_name:
            detail = f"Too many attempts. Please wait before trying again. ({exc})"
        elif "ApiIdInvalid" in exc_name:
            detail = "Telegram API credentials are invalid. Check TELEGRAM_API_ID and TELEGRAM_API_HASH."
        else:
            detail = f"Failed to send Telegram OTP: {exc}"
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
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
        from telethon.errors import SessionPasswordNeededError

        if isinstance(exc, SessionPasswordNeededError):
            await db.commit()
            return {"data": {"connected": False, "requires_2fa": True}, "error": None}
        logger.exception("telegram_verify failed for user %s.", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telegram verification failed: {exc}",
        ) from exc

    from app.models.notification import Notification as TgNotif
    db.add(TgNotif(
        user_id=current_user.id,
        notification_type="sync",
        title="Telegram account connected",
        body=f"Connected as @{current_user.telegram_username}" if current_user.telegram_username else "Account connected successfully",
        link="/settings",
    ))

    await db.commit()
    return {"data": {"connected": True, "username": current_user.telegram_username}, "error": None}


@router.post(
    "/api/v1/auth/telegram/verify-2fa",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def telegram_verify_2fa(
    payload: Telegram2FARequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
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
            detail = f"Telegram 2FA verification failed: {exc}"
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

    await db.commit()
    return {"data": {"connected": True, "username": current_user.telegram_username}, "error": None}


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
) -> dict:
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

    from app.services.tasks import sync_telegram_for_user
    sync_telegram_for_user.delay(str(current_user.id))

    return {"data": {"status": "started"}, "error": None}


# ---------------------------------------------------------------------------
# Common groups endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/contacts/{contact_id}/telegram/common-groups",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def get_common_groups(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return Telegram groups in common with a contact.

    Results are cached on the contact for 24 hours to avoid repeated Telegram API calls.
    """
    if not current_user.telegram_session:
        return {"data": [], "error": None}

    from datetime import UTC, datetime, timedelta
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

    username = contact.telegram_username
    user_id = contact.telegram_user_id
    if not username and not user_id:
        return {"data": [], "error": None}

    # Return cached data if fresh (< 24 hours)
    now = datetime.now(UTC)
    if (
        contact.telegram_common_groups is not None
        and contact.telegram_groups_fetched_at is not None
        and (now - contact.telegram_groups_fetched_at) < timedelta(hours=24)
    ):
        return {"data": contact.telegram_common_groups, "error": None}

    # Fetch fresh data from Telegram
    from app.integrations.telegram import fetch_common_groups

    groups = await fetch_common_groups(
        current_user,
        telegram_username=username,
        telegram_user_id=user_id,
    )

    # Cache the result
    contact.telegram_common_groups = groups
    contact.telegram_groups_fetched_at = now
    await db.flush()
    await db.commit()

    return {"data": groups, "error": None}
