import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_emails_gin", "emails", postgresql_using="gin"),
        Index("ix_contacts_relationship_score", "relationship_score"),
        Index("ix_contacts_full_name", "full_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    given_name: Mapped[str | None] = mapped_column(String, nullable=True)
    family_name: Mapped[str | None] = mapped_column(String, nullable=True)

    emails: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True, default=list)
    phones: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True, default=list)

    company: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)

    twitter_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    twitter_bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_bio: Mapped[str | None] = mapped_column(Text, nullable=True)

    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)

    telegram_common_groups: Mapped[list | None] = mapped_column(JSON, nullable=True)
    telegram_groups_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    relationship_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    priority_level: Mapped[str] = mapped_column(String, default="medium", nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
