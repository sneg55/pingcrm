"""Tests for app/services/telegram_service.py."""
from __future__ import annotations

import sys
import types
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _install_telegram_stub(fake_groups=None):
    """Inject a stub module into sys.modules so lazy imports inside the service
    pick it up without touching real Telethon/MTProto code."""
    stub = types.ModuleType("app.integrations.telegram")
    stub.fetch_common_groups = AsyncMock(return_value=(fake_groups if fake_groups is not None else [], None))
    sys.modules["app.integrations.telegram"] = stub
    return stub


def _remove_telegram_stub():
    sys.modules.pop("app.integrations.telegram", None)


# ---------------------------------------------------------------------------
# Shared fixtures — single DB session per test
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="function")
async def tg_user_and_contact(db: AsyncSession):
    """Create a telegram-enabled user and matching contact in one session."""
    from app.core.auth import hash_password

    user = User(
        id=uuid.uuid4(),
        email="tguser@example.com",
        hashed_password=hash_password("pass"),
        full_name="TG User",
        telegram_session="fake-session-string",
    )
    db.add(user)
    await db.flush()

    contact = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name="TG Contact",
        emails=[],
        phones=[],
        source="manual",
        telegram_username="tgcontact",
        telegram_common_groups=None,
        telegram_groups_fetched_at=None,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(user)
    await db.refresh(contact)
    return user, contact


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_calls_fetch_and_persists(
    db: AsyncSession,
    tg_user_and_contact,
) -> None:
    """When cache is empty, fetch_common_groups is called and result is stored."""
    user, contact = tg_user_and_contact
    fake_groups = [{"id": 1, "title": "Dev Chat"}]

    stub = _install_telegram_stub(fake_groups)
    try:
        from app.services.telegram_service import get_common_groups_cached
        result = await get_common_groups_cached(contact, user, db)
    finally:
        _remove_telegram_stub()

    stub.fetch_common_groups.assert_awaited_once_with(
        user,
        telegram_username=contact.telegram_username,
        telegram_user_id=contact.telegram_user_id,
    )
    assert result == fake_groups
    assert contact.telegram_common_groups == fake_groups
    assert contact.telegram_groups_fetched_at is not None


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_data_without_fetch(
    db: AsyncSession,
    tg_user_and_contact,
) -> None:
    """When cache is fresh (< 24 h), fetch_common_groups is NOT called."""
    user, contact = tg_user_and_contact
    cached_groups = [{"id": 99, "title": "Old Group"}]
    contact.telegram_common_groups = cached_groups
    contact.telegram_groups_fetched_at = datetime.now(UTC) - timedelta(hours=1)
    await db.flush()

    stub = _install_telegram_stub([])
    try:
        from app.services.telegram_service import get_common_groups_cached
        result = await get_common_groups_cached(contact, user, db)
    finally:
        _remove_telegram_stub()

    stub.fetch_common_groups.assert_not_awaited()
    assert result == cached_groups


@pytest.mark.asyncio
async def test_stale_cache_triggers_refresh(
    db: AsyncSession,
    tg_user_and_contact,
) -> None:
    """When cached data is older than 24 h, fresh data is fetched and cached."""
    user, contact = tg_user_and_contact
    new_groups = [{"id": 5, "title": "Fresh Group"}]

    contact.telegram_common_groups = [{"id": 5, "title": "Stale Group"}]
    contact.telegram_groups_fetched_at = datetime.now(UTC) - timedelta(hours=25)
    await db.flush()

    stub = _install_telegram_stub(new_groups)
    try:
        from app.services.telegram_service import get_common_groups_cached
        result = await get_common_groups_cached(contact, user, db)
    finally:
        _remove_telegram_stub()

    stub.fetch_common_groups.assert_awaited_once()
    assert result == new_groups
    assert contact.telegram_common_groups == new_groups


@pytest.mark.asyncio
async def test_cache_boundary_exactly_24h_triggers_refresh(
    db: AsyncSession,
    tg_user_and_contact,
) -> None:
    """Data fetched exactly 24 h ago is considered stale (boundary is exclusive)."""
    user, contact = tg_user_and_contact
    contact.telegram_common_groups = [{"id": 7, "title": "Boundary Group"}]
    contact.telegram_groups_fetched_at = datetime.now(UTC) - timedelta(hours=24)
    await db.flush()

    stub = _install_telegram_stub([])
    try:
        from app.services.telegram_service import get_common_groups_cached
        result = await get_common_groups_cached(contact, user, db)
    finally:
        _remove_telegram_stub()

    stub.fetch_common_groups.assert_awaited_once()
    assert result == []


@pytest.mark.asyncio
async def test_groups_fetched_at_updated_after_refresh(
    db: AsyncSession,
    tg_user_and_contact,
) -> None:
    """After a fresh fetch, telegram_groups_fetched_at is set to approximately now."""
    user, contact = tg_user_and_contact
    before = datetime.now(UTC)

    stub = _install_telegram_stub([])
    try:
        from app.services.telegram_service import get_common_groups_cached
        await get_common_groups_cached(contact, user, db)
    finally:
        _remove_telegram_stub()

    after = datetime.now(UTC)
    fetched_at = contact.telegram_groups_fetched_at
    assert fetched_at is not None
    assert before <= fetched_at <= after
