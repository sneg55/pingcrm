"""Tests for WhatsApp contact matching and interaction upsert helpers."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.whatsapp_helpers import (
    find_contact_by_phone_list,
    find_contact_by_whatsapp_phone,
    normalize_phone,
    resolve_contact,
    upsert_whatsapp_interaction,
)
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User


# ---------------------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------------------


def test_normalize_phone_strips_cus_suffix():
    assert normalize_phone("15551234567@c.us") == "+15551234567"


def test_normalize_phone_strips_whatsapp_net_suffix():
    assert normalize_phone("15551234567@s.whatsapp.net") == "+15551234567"


def test_normalize_phone_strips_spaces_and_dashes():
    assert normalize_phone("+1 555-123-4567") == "+15551234567"


def test_normalize_phone_adds_plus_if_missing():
    assert normalize_phone("15551234567") == "+15551234567"


def test_normalize_phone_passes_through_e164():
    assert normalize_phone("+15551234567") == "+15551234567"


def test_normalize_phone_strips_parentheses_and_dots():
    assert normalize_phone("+1 (555) 123.4567") == "+15551234567"


# ---------------------------------------------------------------------------
# find_contact_by_whatsapp_phone
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="function")
async def user(db: AsyncSession) -> User:
    from app.core.auth import hash_password

    u = User(
        id=uuid.uuid4(),
        email="wa_test@example.com",
        hashed_password=hash_password("pass"),
        full_name="WA Test User",
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture(loop_scope="function")
async def contact_with_whatsapp(db: AsyncSession, user: User) -> Contact:
    c = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name="Alice WA",
        whatsapp_phone="+15551110000",
        phones=["+15551110000"],
        source="whatsapp",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest_asyncio.fixture(loop_scope="function")
async def contact_phone_only(db: AsyncSession, user: User) -> Contact:
    """Contact with phone in phones array but no whatsapp_phone set."""
    c = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name="Bob Phone",
        phones=["+15559990000"],
        source="manual",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest.mark.asyncio
async def test_find_contact_by_whatsapp_phone_found(
    db: AsyncSession, user: User, contact_with_whatsapp: Contact
):
    result = await find_contact_by_whatsapp_phone("+15551110000", user.id, db)
    assert result is not None
    assert result.id == contact_with_whatsapp.id


@pytest.mark.asyncio
async def test_find_contact_by_whatsapp_phone_not_found(db: AsyncSession, user: User):
    result = await find_contact_by_whatsapp_phone("+19999999999", user.id, db)
    assert result is None


@pytest.mark.asyncio
async def test_find_contact_by_whatsapp_phone_wrong_user(
    db: AsyncSession, contact_with_whatsapp: Contact
):
    other_user_id = uuid.uuid4()
    result = await find_contact_by_whatsapp_phone("+15551110000", other_user_id, db)
    assert result is None


# ---------------------------------------------------------------------------
# find_contact_by_phone_list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_contact_by_phone_list_found(
    db: AsyncSession, user: User, contact_phone_only: Contact
):
    result = await find_contact_by_phone_list("+15559990000", user.id, db)
    assert result is not None
    assert result.id == contact_phone_only.id


@pytest.mark.asyncio
async def test_find_contact_by_phone_list_not_found(db: AsyncSession, user: User):
    result = await find_contact_by_phone_list("+18880000000", user.id, db)
    assert result is None


@pytest.mark.asyncio
async def test_find_contact_by_phone_list_wrong_user(
    db: AsyncSession, contact_phone_only: Contact
):
    other_user_id = uuid.uuid4()
    result = await find_contact_by_phone_list("+15559990000", other_user_id, db)
    assert result is None


# ---------------------------------------------------------------------------
# resolve_contact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_contact_finds_by_whatsapp_phone(
    db: AsyncSession, user: User, contact_with_whatsapp: Contact
):
    contact, is_new = await resolve_contact("+15551110000", user.id, db)
    assert not is_new
    assert contact.id == contact_with_whatsapp.id


@pytest.mark.asyncio
async def test_resolve_contact_finds_by_phone_list(
    db: AsyncSession, user: User, contact_phone_only: Contact
):
    contact, is_new = await resolve_contact("+15559990000", user.id, db)
    assert not is_new
    assert contact.id == contact_phone_only.id


@pytest.mark.asyncio
async def test_resolve_contact_creates_new(db: AsyncSession, user: User):
    phone = "+12223334444"
    contact, is_new = await resolve_contact(phone, user.id, db, name="Carol New")
    assert is_new
    assert contact.whatsapp_phone == phone
    assert contact.full_name == "Carol New"
    assert contact.source == "whatsapp"


@pytest.mark.asyncio
async def test_resolve_contact_creates_new_without_name(db: AsyncSession, user: User):
    phone = "+13334445555"
    contact, is_new = await resolve_contact(phone, user.id, db)
    assert is_new
    assert contact.whatsapp_phone == phone
    # full_name defaults to None when no name given
    assert contact.full_name is None


# ---------------------------------------------------------------------------
# upsert_whatsapp_interaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_whatsapp_interaction_creates_new(
    db: AsyncSession, user: User, contact_with_whatsapp: Contact
):
    msg_id = "msg_abc_001"
    occurred = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    interaction, is_new = await upsert_whatsapp_interaction(
        contact=contact_with_whatsapp,
        user_id=user.id,
        message_id=msg_id,
        direction="inbound",
        content_preview="Hello there!",
        occurred_at=occurred,
        db=db,
    )
    assert is_new
    assert interaction.platform == "whatsapp"
    assert interaction.raw_reference_id == msg_id
    assert interaction.direction == "inbound"
    assert interaction.content_preview == "Hello there!"
    assert interaction.contact_id == contact_with_whatsapp.id
    assert interaction.user_id == user.id
    assert interaction.occurred_at == occurred


@pytest.mark.asyncio
async def test_upsert_whatsapp_interaction_deduplicates(
    db: AsyncSession, user: User, contact_with_whatsapp: Contact
):
    msg_id = "msg_dup_999"
    occurred = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    kwargs = dict(
        contact=contact_with_whatsapp,
        user_id=user.id,
        message_id=msg_id,
        direction="outbound",
        content_preview="Hi!",
        occurred_at=occurred,
        db=db,
    )
    interaction1, is_new1 = await upsert_whatsapp_interaction(**kwargs)
    await db.flush()
    interaction2, is_new2 = await upsert_whatsapp_interaction(**kwargs)

    assert is_new1 is True
    assert is_new2 is False
    assert interaction1.id == interaction2.id


@pytest.mark.asyncio
async def test_upsert_whatsapp_interaction_truncates_long_preview(
    db: AsyncSession, user: User, contact_with_whatsapp: Contact
):
    long_text = "x" * 600
    occurred = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    interaction, is_new = await upsert_whatsapp_interaction(
        contact=contact_with_whatsapp,
        user_id=user.id,
        message_id="msg_long_001",
        direction="inbound",
        content_preview=long_text,
        occurred_at=occurred,
        db=db,
    )
    assert is_new
    assert len(interaction.content_preview) == 500


@pytest.mark.asyncio
async def test_upsert_whatsapp_interaction_none_preview(
    db: AsyncSession, user: User, contact_with_whatsapp: Contact
):
    occurred = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    interaction, is_new = await upsert_whatsapp_interaction(
        contact=contact_with_whatsapp,
        user_id=user.id,
        message_id="msg_no_preview",
        direction="inbound",
        content_preview=None,
        occurred_at=occurred,
        db=db,
    )
    assert is_new
    assert interaction.content_preview is None
