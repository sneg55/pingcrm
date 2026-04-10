import hashlib
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _generate_bcc_hash() -> str:
    """Generate a short hash for BCC email addressing."""
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:7]


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_emails_gin", "emails", postgresql_using="gin"),
        Index("ix_contacts_relationship_score", "relationship_score"),
        Index("ix_contacts_interaction_count", "interaction_count"),
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

    company: Mapped[str | None] = mapped_column(String, nullable=True)  # legacy — migrating to organization_id
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)

    twitter_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    twitter_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    twitter_bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    telegram_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    telegram_bio: Mapped[str | None] = mapped_column(Text, nullable=True)

    location: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_profile_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    linkedin_headline: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    birthday: Mapped[str | None] = mapped_column(String, nullable=True)  # "MM-DD" or "YYYY-MM-DD"

    telegram_common_groups: Mapped[list | None] = mapped_column(JSON, nullable=True)
    telegram_groups_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_bio_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_read_outbox_max_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    whatsapp_phone: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    whatsapp_name: Mapped[str | None] = mapped_column(String, nullable=True)
    whatsapp_about: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    whatsapp_bio_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    facebook_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    facebook_name: Mapped[str | None] = mapped_column(String, nullable=True)
    facebook_avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    instagram_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    instagram_username: Mapped[str | None] = mapped_column(String, nullable=True)
    instagram_avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)

    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    relationship_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    priority_level: Mapped[str] = mapped_column(String, default="medium", nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    user_edited_fields: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    google_resource_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    bcc_hash: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True, default=_generate_bcc_hash)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
