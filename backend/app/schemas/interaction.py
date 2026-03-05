import uuid
from datetime import datetime

from pydantic import BaseModel


class InteractionCreate(BaseModel):
    platform: str = "manual"
    direction: str = "outbound"
    content_preview: str | None = None
    raw_reference_id: str | None = None
    occurred_at: datetime


class InteractionResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    user_id: uuid.UUID
    platform: str
    direction: str
    content_preview: str | None = None
    raw_reference_id: str | None = None
    occurred_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
