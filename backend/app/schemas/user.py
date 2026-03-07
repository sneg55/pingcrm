import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    created_at: datetime
    google_connected: bool = False
    google_email: str | None = None
    telegram_connected: bool = False
    telegram_username: str | None = None
    twitter_connected: bool = False
    twitter_username: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user: "User") -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            created_at=user.created_at,
            google_connected=bool(user.google_refresh_token),
            google_email=user.email if user.google_refresh_token else None,
            telegram_connected=bool(user.telegram_session),
            telegram_username=getattr(user, "telegram_username", None),
            twitter_connected=bool(user.twitter_access_token),
            twitter_username=getattr(user, "twitter_username", None),
        )


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
