import uuid
from datetime import datetime

from pydantic import BaseModel


class FollowUpResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    user_id: uuid.UUID
    trigger_type: str
    trigger_event_id: uuid.UUID | None = None
    suggested_message: str
    suggested_channel: str
    status: str
    scheduled_for: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class FollowUpUpdate(BaseModel):
    status: str
    scheduled_for: datetime | None = None
