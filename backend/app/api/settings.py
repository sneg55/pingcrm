"""Settings API — user preference endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
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
    existing = current_user.priority_settings or {}
    existing.update(body.model_dump())
    current_user.priority_settings = existing
    await db.flush()
    await db.refresh(current_user)
    settings = get_priority_settings(current_user)
    return {"data": settings, "error": None}


class SuggestionPrefsInput(BaseModel):
    max_suggestions: int | None = Field(default=None, ge=5, le=20)
    include_dormant: bool | None = None
    birthday_reminders: bool | None = None
    preferred_channel: str | None = Field(default=None, pattern="^(auto|email|telegram|twitter)$")


class SuggestionPrefsData(BaseModel):
    max_suggestions: int
    include_dormant: bool
    birthday_reminders: bool
    preferred_channel: str


_DEFAULT_SUGGESTION_PREFS = {
    "max_suggestions": 10,
    "include_dormant": True,
    "birthday_reminders": True,
    "preferred_channel": "auto",
}


@router.get("/suggestions", response_model=Envelope[SuggestionPrefsData])
async def get_suggestion_prefs(
    current_user: User = Depends(get_current_user),
) -> Envelope[SuggestionPrefsData]:
    stored = (current_user.priority_settings or {}).get("suggestion_prefs", {})
    merged = {**_DEFAULT_SUGGESTION_PREFS, **stored}
    return {"data": merged, "error": None}


@router.put("/suggestions", response_model=Envelope[SuggestionPrefsData])
async def update_suggestion_prefs(
    body: SuggestionPrefsInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[SuggestionPrefsData]:
    settings = current_user.priority_settings or {}
    prefs = settings.get("suggestion_prefs", {})
    prefs.update(body.model_dump(exclude_none=True))
    settings["suggestion_prefs"] = prefs
    current_user.priority_settings = settings
    await db.flush()
    merged = {**_DEFAULT_SUGGESTION_PREFS, **prefs}
    return {"data": merged, "error": None}


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
