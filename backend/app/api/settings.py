"""Settings API — user preference endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.responses import Envelope
from app.services.user_settings import DEFAULT_PRIORITY_SETTINGS, get_priority_settings

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class PrioritySettingsInput(BaseModel):
    high: int
    medium: int
    low: int

    @field_validator("high", "medium", "low")
    @classmethod
    def validate_range(cls, v: int) -> int:
        if v < 7 or v > 365:
            raise ValueError("Interval must be between 7 and 365 days")
        return v


class PrioritySettingsData(BaseModel):
    high: int
    medium: int
    low: int


@router.get("/priority", response_model=Envelope[PrioritySettingsData])
async def get_priority(
    current_user: User = Depends(get_current_user),
) -> Envelope[PrioritySettingsData]:
    settings = get_priority_settings(current_user)
    return {"data": settings, "error": None}


@router.put("/priority", response_model=Envelope[PrioritySettingsData])
async def update_priority(
    body: PrioritySettingsInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[PrioritySettingsData]:
    current_user.priority_settings = body.model_dump()
    await db.flush()
    await db.refresh(current_user)
    settings = get_priority_settings(current_user)
    return {"data": settings, "error": None}


class SyncSettingsInput(BaseModel):
    """Per-platform sync configuration."""
    telegram: dict | None = None  # {auto_sync: bool, schedule: "daily"|"6h"|"12h"|"manual"}
    gmail: dict | None = None
    twitter: dict | None = None
    linkedin: dict | None = None


class SyncSettingsData(BaseModel):
    telegram: dict
    gmail: dict
    twitter: dict
    linkedin: dict


_DEFAULT_SYNC_SETTINGS: dict[str, dict] = {
    "telegram": {"auto_sync": True, "schedule": "daily"},
    "gmail": {"auto_sync": True, "schedule": "6h"},
    "twitter": {"auto_sync": True, "schedule": "daily"},
    "linkedin": {"auto_sync": False, "schedule": "manual"},
}


def _get_sync_settings(user: "User") -> dict:
    """Merge user sync_settings with defaults."""
    stored = user.sync_settings or {}
    result = {}
    for platform, defaults in _DEFAULT_SYNC_SETTINGS.items():
        result[platform] = {**defaults, **(stored.get(platform) or {})}
    return result


@router.get("/sync", response_model=Envelope[SyncSettingsData])
async def get_sync_settings(
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncSettingsData]:
    return {"data": _get_sync_settings(current_user), "error": None}


@router.put("/sync", response_model=Envelope[SyncSettingsData])
async def update_sync_settings(
    body: SyncSettingsInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[SyncSettingsData]:
    current = current_user.sync_settings or {}
    updates = body.model_dump(exclude_none=True)
    for platform, vals in updates.items():
        if vals:
            current[platform] = {**(current.get(platform) or {}), **vals}
    current_user.sync_settings = current
    await db.flush()
    return {"data": _get_sync_settings(current_user), "error": None}


class TelegramSettingsInput(BaseModel):
    sync_2nd_tier: bool


class TelegramSettingsData(BaseModel):
    sync_2nd_tier: bool


@router.get("/telegram", response_model=Envelope[TelegramSettingsData])
async def get_telegram_settings(
    current_user: User = Depends(get_current_user),
) -> Envelope[TelegramSettingsData]:
    return {"data": {"sync_2nd_tier": current_user.sync_2nd_tier}, "error": None}


@router.put("/telegram", response_model=Envelope[TelegramSettingsData])
async def update_telegram_settings(
    body: TelegramSettingsInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TelegramSettingsData]:
    current_user.sync_2nd_tier = body.sync_2nd_tier
    await db.flush()
    return {"data": {"sync_2nd_tier": current_user.sync_2nd_tier}, "error": None}
