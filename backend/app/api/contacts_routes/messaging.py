from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.contacts_routes.shared import (
    Contact,
    datetime,
    Depends,
    Envelope,
    HTTPException,
    AsyncSession,
    User,
    envelope,
    get_current_user,
    get_db,
    select,
    status,
)
from app.schemas.responses import SendMessageData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


class SendMessageBody(BaseModel):
    message: str
    channel: str  # "telegram" | "twitter" | "email"
    scheduled_for: datetime | None = None  # ISO datetime for scheduled send (Telegram only)


@router.post(
    "/{contact_id}/send-message",
    response_model=Envelope[SendMessageData],
    status_code=status.HTTP_200_OK,
)
async def send_message(
    contact_id: uuid.UUID,
    body: SendMessageBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SendMessageData]:
    """Send a message to a contact via the specified channel.

    Currently supports Telegram. Creates an Interaction record on success.
    """
    from datetime import UTC, datetime

    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.user_id == current_user.id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not body.message.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message cannot be empty")

    if body.channel == "telegram":
        username = contact.telegram_username
        if not username:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Contact has no Telegram username",
            )
        from app.integrations.telegram import send_telegram_message

        try:
            send_result = await send_telegram_message(
                current_user, username, body.message.strip(),
                telegram_user_id=contact.telegram_user_id,
                scheduled_for=body.scheduled_for,
            )
            # Backfill telegram_user_id to avoid future username lookups
            resolved_id = send_result.get("resolved_user_id")
            if resolved_id and not contact.telegram_user_id:
                contact.telegram_user_id = str(resolved_id)
        except RuntimeError as exc:
            # Create a system notification so the rate limit is visible in /notifications
            if "rate limit" in str(exc).lower():
                from app.models.notification import Notification
                db.add(Notification(
                    user_id=current_user.id,
                    notification_type="system",
                    title="Telegram rate limit",
                    body=str(exc),
                    link="/settings",
                ))
                await db.flush()
                # Return 429 with Retry-After header
                retry_after = exc.args[1] if len(exc.args) > 1 else 3600
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={"data": None, "error": str(exc), "meta": {"retry_after": retry_after}},
                )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to send Telegram message to %s", username)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to send Telegram message. Please try again.",
            ) from exc
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sending via '{body.channel}' is not yet supported. Only 'telegram' is available.",
        )

    # Record the interaction
    from app.models.interaction import Interaction

    interaction = Interaction(
        contact_id=contact.id,
        user_id=current_user.id,
        platform=body.channel,
        direction="outbound",
        content_preview=body.message.strip()[:500],
        occurred_at=datetime.now(UTC),
        raw_reference_id=f"sent:{send_result.get('message_id', '')}",
    )
    db.add(interaction)

    # Update last_interaction_at and last_followup_at
    contact.last_interaction_at = datetime.now(UTC)
    contact.last_followup_at = datetime.now(UTC)
    await db.flush()

    return envelope({
        "sent": True,
        "channel": body.channel,
        "interaction_id": str(interaction.id),
    })


class ComposeBody(BaseModel):
    channel: str = "email"


@router.post("/{contact_id}/compose")
async def compose_message(
    contact_id: uuid.UUID,
    body: ComposeBody | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an AI-drafted reach-out message for a contact (no suggestion required)."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    from app.services.message_composer import compose_followup_message

    channel = body.channel if body else "email"
    message = await compose_followup_message(
        contact_id=contact_id,
        trigger_type="manual",
        event_summary=None,
        db=db,
    )

    return envelope({"suggested_message": message, "suggested_channel": channel})
