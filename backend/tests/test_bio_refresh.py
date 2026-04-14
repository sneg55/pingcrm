"""Tests for bio_refresh service."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.notification import Notification
from app.models.user import User
from app.services.bio_refresh import refresh_contact_bios


# ---------------------------------------------------------------------------
# Local fixtures (use conftest `db` session so tables are guaranteed)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="function")
async def bio_user(db: AsyncSession) -> User:
    """A user for bio_refresh tests, with valid bird cookies."""
    from app.core.auth import hash_password

    u = User(
        id=uuid.uuid4(),
        email=f"biotest_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("pass"),
        full_name="Bio Test User",
        twitter_bird_auth_token="test_auth_token",
        twitter_bird_ct0="test_ct0",
        twitter_bird_status="connected",
    )
    db.add(u)
    await db.flush()
    return u


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contact(user_id: uuid.UUID, **kwargs) -> Contact:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name="Jane Smith",
        emails=["jane@example.com"],
        source="manual",
    )
    defaults.update(kwargs)
    return Contact(**defaults)


# ---------------------------------------------------------------------------
# Twitter bio tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twitter_bio_change_detected(db: AsyncSession, bio_user: User):
    """When Twitter returns a new bio, twitter_bio_changed is True and the
    contact's twitter_bio field is updated."""
    contact = _make_contact(
        bio_user.id,
        twitter_handle="janesmith",
        twitter_bio="Old bio text",
    )
    db.add(contact)
    await db.flush()

    fake_profile = {"description": "Brand new bio", "location": "", "profileImageUrl": None}

    with (
        patch(
            "app.integrations.bird.fetch_user_profile_bird",
            new=AsyncMock(return_value=(fake_profile, None)),
        ),
        patch(
            "app.integrations.twitter.download_twitter_avatar",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await refresh_contact_bios(contact, bio_user, db)

    assert result["twitter_bio_changed"] is True
    assert contact.twitter_bio == "Brand new bio"


@pytest.mark.asyncio
async def test_twitter_bio_no_change(db: AsyncSession, bio_user: User):
    """When the fetched bio equals the stored bio, twitter_bio_changed is False."""
    contact = _make_contact(
        bio_user.id,
        twitter_handle="janesmith",
        twitter_bio="Same bio",
    )
    db.add(contact)
    await db.flush()

    fake_profile = {"description": "Same bio", "location": "", "profileImageUrl": None}

    with (
        patch(
            "app.integrations.bird.fetch_user_profile_bird",
            new=AsyncMock(return_value=(fake_profile, None)),
        ),
        patch(
            "app.integrations.twitter.download_twitter_avatar",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await refresh_contact_bios(contact, bio_user, db)

    assert result["twitter_bio_changed"] is False
    assert contact.twitter_bio == "Same bio"


@pytest.mark.asyncio
async def test_notification_created_on_bio_change(db: AsyncSession, bio_user: User):
    """A Notification row is persisted when a bio changes and there was a
    previous value."""
    contact = _make_contact(
        bio_user.id,
        twitter_handle="janesmith",
        twitter_bio="Previous bio",
    )
    db.add(contact)
    await db.flush()

    fake_profile = {"description": "Updated bio", "location": "", "profileImageUrl": None}

    with (
        patch(
            "app.integrations.bird.fetch_user_profile_bird",
            new=AsyncMock(return_value=(fake_profile, None)),
        ),
        patch(
            "app.integrations.twitter.download_twitter_avatar",
            new=AsyncMock(return_value=None),
        ),
    ):
        await refresh_contact_bios(contact, bio_user, db)

    notifs = (await db.execute(
        select(Notification).where(
            Notification.user_id == bio_user.id,
            Notification.notification_type == "bio_change",
        )
    )).scalars().all()

    assert len(notifs) == 1
    notif = notifs[0]
    assert "janesmith" in notif.title
    assert "Updated bio" in notif.body
    assert str(contact.id) in notif.link


@pytest.mark.asyncio
async def test_no_notification_when_first_bio_set(db: AsyncSession, bio_user: User):
    """If there was no previous bio (first-time fetch), no notification is created."""
    contact = _make_contact(
        bio_user.id,
        twitter_handle="newbiouser",
        twitter_bio=None,
    )
    db.add(contact)
    await db.flush()

    fake_profile = {"description": "First bio ever", "location": "", "profileImageUrl": None}

    with (
        patch(
            "app.integrations.bird.fetch_user_profile_bird",
            new=AsyncMock(return_value=(fake_profile, None)),
        ),
        patch(
            "app.integrations.twitter.download_twitter_avatar",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await refresh_contact_bios(contact, bio_user, db)

    assert result["twitter_bio_changed"] is True
    assert contact.twitter_bio == "First bio ever"

    notifs = (await db.execute(
        select(Notification).where(Notification.user_id == bio_user.id)
    )).scalars().all()
    assert len(notifs) == 0


@pytest.mark.asyncio
async def test_missing_twitter_handle_skipped(db: AsyncSession, bio_user: User):
    """If the contact has no twitter_handle, the Twitter section is skipped entirely."""
    contact = _make_contact(
        bio_user.id,
        twitter_handle=None,
    )
    db.add(contact)
    await db.flush()

    with patch(
        "app.integrations.bird.fetch_user_profile_bird",
        new=AsyncMock(side_effect=RuntimeError("should not be called")),
    ):
        result = await refresh_contact_bios(contact, bio_user, db)

    assert result["twitter_bio_changed"] is False


@pytest.mark.asyncio
async def test_twitter_api_error_handled_gracefully(db: AsyncSession, bio_user: User):
    """A Twitter API exception must be swallowed; the service returns False and
    does not raise."""
    contact = _make_contact(
        bio_user.id,
        twitter_handle="janesmith",
        twitter_bio="Existing bio",
    )
    db.add(contact)
    await db.flush()

    with patch(
        "app.integrations.bird.fetch_user_profile_bird",
        new=AsyncMock(side_effect=Exception("network error")),
    ):
        result = await refresh_contact_bios(contact, bio_user, db)

    assert result["twitter_bio_changed"] is False
    assert contact.twitter_bio == "Existing bio"


@pytest.mark.asyncio
async def test_twitter_location_updated_from_profile(db: AsyncSession, bio_user: User):
    """Location is populated from the Twitter profile when the contact has none."""
    contact = _make_contact(
        bio_user.id,
        twitter_handle="janesmith",
        twitter_bio=None,
        location=None,
    )
    db.add(contact)
    await db.flush()

    fake_profile = {
        "description": "Bio text",
        "location": "San Francisco, CA",
        "profileImageUrl": None,
    }

    with (
        patch(
            "app.integrations.bird.fetch_user_profile_bird",
            new=AsyncMock(return_value=(fake_profile, None)),
        ),
        patch(
            "app.integrations.twitter.download_twitter_avatar",
            new=AsyncMock(return_value=None),
        ),
    ):
        await refresh_contact_bios(contact, bio_user, db)

    assert contact.location == "San Francisco, CA"


@pytest.mark.asyncio
async def test_twitter_avatar_downloaded_when_missing(db: AsyncSession, bio_user: User):
    """Avatar URL is set when the contact has none and the profile has one."""
    contact = _make_contact(
        bio_user.id,
        twitter_handle="janesmith",
        avatar_url=None,
    )
    db.add(contact)
    await db.flush()

    fake_profile = {
        "description": "",
        "location": "",
        "profileImageUrl": "https://pbs.twimg.com/profile_images/abc/photo.jpg",
    }

    with (
        patch(
            "app.integrations.bird.fetch_user_profile_bird",
            new=AsyncMock(return_value=(fake_profile, None)),
        ),
        patch(
            "app.integrations.twitter.download_twitter_avatar",
            new=AsyncMock(return_value="/media/avatars/avatar.jpg"),
        ),
    ):
        await refresh_contact_bios(contact, bio_user, db)

    assert contact.avatar_url == "/media/avatars/avatar.jpg"
