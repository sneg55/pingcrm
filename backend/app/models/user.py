import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encryption import EncryptedString


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    google_refresh_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    twitter_access_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    twitter_refresh_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    twitter_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    twitter_username: Mapped[str | None] = mapped_column(String, nullable=True)
    twitter_dm_cursor: Mapped[str | None] = mapped_column(String, nullable=True)
    twitter_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    twitter_bird_auth_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    twitter_bird_ct0: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    twitter_bird_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="disconnected", server_default="disconnected"
    )
    twitter_bird_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    telegram_session: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    whatsapp_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    whatsapp_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    whatsapp_last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    priority_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sync_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sync_2nd_tier: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    linkedin_extension_paired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    meta_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    meta_connected_name: Mapped[str | None] = mapped_column(String, nullable=True)
    meta_sync_facebook: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    meta_sync_instagram: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    mcp_api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
