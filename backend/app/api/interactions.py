import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.interaction import InteractionCreate, InteractionResponse

router = APIRouter(prefix="/api/v1/contacts", tags=["interactions"])


def envelope(data: object, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


@router.get("/{contact_id}/interactions", response_model=dict)
async def list_interactions(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    if not contact_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    result = await db.execute(
        select(Interaction)
        .where(Interaction.contact_id == contact_id)
        .order_by(Interaction.occurred_at.desc())
    )
    interactions = result.scalars().all()
    return envelope([InteractionResponse.model_validate(i).model_dump() for i in interactions])


@router.post("/{contact_id}/interactions", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_interaction(
    contact_id: uuid.UUID,
    interaction_in: InteractionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    interaction = Interaction(
        **interaction_in.model_dump(),
        contact_id=contact_id,
        user_id=current_user.id,
    )
    db.add(interaction)

    contact.last_interaction_at = interaction_in.occurred_at
    await db.flush()
    await db.refresh(interaction)
    return envelope(InteractionResponse.model_validate(interaction).model_dump())
