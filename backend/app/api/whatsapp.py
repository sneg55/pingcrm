"""WhatsApp authentication, sync, and webhook endpoints."""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.integrations.whatsapp_helpers import (
    normalize_phone,
    resolve_contact,
    upsert_whatsapp_interaction,
)
from app.models.contact import Contact
from app.models.notification import Notification
from app.models.user import User
from app.schemas.responses import Envelope, SyncStartedData
from app.services.scoring import calculate_score

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])


# ---------------------------------------------------------------------------
# Local schemas
# ---------------------------------------------------------------------------


class WhatsAppSessionData(BaseModel):
    status: str
    qr: str | None = None


class WhatsAppStatusData(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(
        settings.WHATSAPP_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# User-facing endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/auth/whatsapp/connect",
    response_model=Envelope[WhatsAppSessionData],
    status_code=status.HTTP_200_OK,
)
async def whatsapp_connect(
    current_user: User = Depends(get_current_user),
) -> Envelope[WhatsAppSessionData]:
    """Start a WhatsApp session (or resume one) and return QR code if needed."""
    from app.integrations.whatsapp import start_session

    try:
        result = await start_session(str(current_user.id))
    except Exception:
        logger.exception(
            "whatsapp_connect failed",
            extra={"provider": "whatsapp", "user_id": str(current_user.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to start WhatsApp session. Please try again.",
        )
    return {"data": {"status": result.get("status", ""), "qr": result.get("qr")}, "error": None}


@router.get(
    "/api/v1/auth/whatsapp/qr",
    response_model=Envelope[WhatsAppSessionData],
    status_code=status.HTTP_200_OK,
)
async def whatsapp_get_qr(
    current_user: User = Depends(get_current_user),
) -> Envelope[WhatsAppSessionData]:
    """Return the current QR code for a pending WhatsApp session."""
    from app.integrations.whatsapp import get_qr

    try:
        result = await get_qr(str(current_user.id))
    except Exception:
        logger.exception(
            "whatsapp_get_qr failed",
            extra={"provider": "whatsapp", "user_id": str(current_user.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch WhatsApp QR code. Please try again.",
        )
    return {"data": {"status": result.get("status", ""), "qr": result.get("qr")}, "error": None}


@router.get(
    "/api/v1/auth/whatsapp/status",
    response_model=Envelope[WhatsAppStatusData],
    status_code=status.HTTP_200_OK,
)
async def whatsapp_get_status(
    current_user: User = Depends(get_current_user),
) -> Envelope[WhatsAppStatusData]:
    """Return the current WhatsApp session status."""
    from app.integrations.whatsapp import get_status

    try:
        status_str = await get_status(str(current_user.id))
    except Exception:
        logger.exception(
            "whatsapp_get_status failed",
            extra={"provider": "whatsapp", "user_id": str(current_user.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch WhatsApp status. Please try again.",
        )
    return {"data": {"status": status_str}, "error": None}


@router.post(
    "/api/v1/contacts/sync/whatsapp",
    response_model=Envelope[SyncStartedData],
    status_code=status.HTTP_200_OK,
)
async def sync_whatsapp(
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
    """Dispatch a background WhatsApp backfill sync for the authenticated user."""
    if not current_user.whatsapp_connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WhatsApp account not connected. Use /api/v1/auth/whatsapp/connect first.",
        )

    from app.services.tasks import sync_whatsapp_backfill

    sync_whatsapp_backfill.apply_async(args=[str(current_user.id)])
    return {"data": {"status": "started"}, "error": None}


@router.delete(
    "/api/v1/auth/whatsapp/disconnect",
    response_model=Envelope[dict],
    status_code=status.HTTP_200_OK,
)
async def whatsapp_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[dict]:
    """Disconnect WhatsApp: destroy the sidecar session and clear user fields."""
    from app.integrations.whatsapp import destroy_session

    try:
        await destroy_session(str(current_user.id))
    except Exception:
        logger.warning(
            "whatsapp_disconnect: destroy_session failed (proceeding with local clear)",
            extra={"provider": "whatsapp", "user_id": str(current_user.id)},
            exc_info=True,
        )

    current_user.whatsapp_connected = False
    current_user.whatsapp_phone = None
    current_user.whatsapp_last_synced_at = None
    await db.flush()
    return {"data": {"disconnected": True}, "error": None}


# ---------------------------------------------------------------------------
# Webhook endpoint (no auth — HMAC-verified)
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/webhooks/whatsapp",
    status_code=status.HTTP_200_OK,
    response_model=Envelope[dict],
)
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_whatsapp_signature: str | None = Header(default=None, alias="x-whatsapp-signature"),
) -> Envelope[dict]:
    """Receive events from the whatsapp-sidecar service."""
    body = await request.body()

    # Verify HMAC signature when secret is configured
    if settings.WHATSAPP_WEBHOOK_SECRET:
        if not x_whatsapp_signature or not _verify_signature(body, x_whatsapp_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_type = payload.get("type")
    user_id_str = payload.get("user_id")

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing user_id in payload",
        )

    # Fetch the user
    result = await db.execute(select(User).where(User.id == user_id_str))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(
            "whatsapp_webhook: unknown user_id %s for event %s",
            user_id_str,
            event_type,
            extra={"provider": "whatsapp", "user_id": user_id_str},
        )
        return {"data": {"received": True}, "error": None}

    if event_type == "session_connected":
        user.whatsapp_connected = True
        db.add(Notification(
            user_id=user.id,
            notification_type="sync",
            title="WhatsApp connected",
            body="Your WhatsApp account has been connected successfully.",
            link="/settings",
        ))
        await db.flush()

    elif event_type == "session_disconnected":
        user.whatsapp_connected = False
        db.add(Notification(
            user_id=user.id,
            notification_type="sync",
            title="WhatsApp disconnected",
            body="Your WhatsApp session has ended. Reconnect in Settings.",
            link="/settings",
        ))
        await db.flush()

    elif event_type == "message_received":
        await _handle_message(payload, user, db)

    elif event_type == "backfill_batch":
        messages = payload.get("messages", [])
        for msg in messages:
            await _handle_message(msg, user, db, batch_context=True)

    elif event_type == "backfill_complete":
        user.whatsapp_last_synced_at = datetime.now(UTC)
        await db.flush()

        # Recalculate scores for all WhatsApp contacts
        wa_result = await db.execute(
            select(Contact).where(
                Contact.user_id == user.id,
                Contact.whatsapp_phone.isnot(None),
            )
        )
        wa_contacts = wa_result.scalars().all()
        for contact in wa_contacts:
            try:
                await calculate_score(contact.id, db)
            except Exception:
                logger.exception(
                    "whatsapp_webhook: score recalc failed",
                    extra={"provider": "whatsapp", "contact_id": str(contact.id)},
                )

    else:
        logger.warning(
            "whatsapp_webhook: unknown event type %s",
            event_type,
            extra={"provider": "whatsapp", "user_id": user_id_str},
        )

    return {"data": {"received": True}, "error": None}


async def _handle_message(
    msg: dict,
    user: User,
    db: AsyncSession,
    *,
    batch_context: bool = False,
) -> None:
    """Process a single WhatsApp message event."""
    msg_type = msg.get("type")
    if msg_type != "chat":
        return

    raw_phone = msg.get("from") or msg.get("phone") or ""
    if not raw_phone:
        logger.warning(
            "whatsapp_webhook: message missing sender phone",
            extra={"provider": "whatsapp", "user_id": str(user.id)},
        )
        return

    try:
        phone = normalize_phone(raw_phone)
    except Exception:
        logger.warning(
            "whatsapp_webhook: could not normalize phone %r",
            raw_phone,
            extra={"provider": "whatsapp", "user_id": str(user.id)},
            exc_info=True,
        )
        return

    name = msg.get("sender_name") or msg.get("name")
    contact, _is_new = await resolve_contact(phone, user.id, db, name=name)

    message_id = msg.get("id") or msg.get("message_id") or ""
    direction = msg.get("direction", "inbound")
    content_preview = msg.get("body") or msg.get("content")
    timestamp = msg.get("timestamp")
    if timestamp:
        try:
            occurred_at = datetime.fromtimestamp(int(timestamp), tz=UTC)
        except (ValueError, TypeError, OSError):
            occurred_at = datetime.now(UTC)
    else:
        occurred_at = datetime.now(UTC)

    _interaction, is_new_interaction = await upsert_whatsapp_interaction(
        contact=contact,
        user_id=user.id,
        message_id=message_id,
        direction=direction,
        content_preview=content_preview,
        occurred_at=occurred_at,
        db=db,
    )

    if is_new_interaction and not batch_context:
        try:
            await calculate_score(contact.id, db)
        except Exception:
            logger.exception(
                "whatsapp_webhook: score calc failed",
                extra={"provider": "whatsapp", "contact_id": str(contact.id)},
            )
