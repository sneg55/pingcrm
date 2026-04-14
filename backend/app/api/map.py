"""Map-related client config (public Mapbox token, etc.)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.config import settings
from app.models.user import User
from app.schemas.responses import Envelope

router = APIRouter(prefix="/api/v1/map", tags=["map"])


class MapConfig(BaseModel):
    mapbox_public_token: str


@router.get("/config", response_model=Envelope[MapConfig])
async def map_config(_: User = Depends(get_current_user)) -> Envelope[MapConfig]:
    return Envelope(data=MapConfig(mapbox_public_token=settings.MAPBOX_PUBLIC_TOKEN))
