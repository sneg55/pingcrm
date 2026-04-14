from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.models.contact import Contact
from app.services.task_jobs.geocoding import _do_geocode


@pytest.mark.asyncio
async def test_do_geocode_stores_coordinates(db_session, user_factory):
    user = await user_factory()
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name="Alice",
        location="San Francisco, CA",
    )
    db_session.add(contact)
    await db_session.commit()

    geocoder = AsyncMock()
    geocoder.geocode = AsyncMock(
        return_value=type("R", (), {"latitude": 37.77, "longitude": -122.42})()
    )

    await _do_geocode(db_session, str(contact.id), geocoder)
    await db_session.refresh(contact)

    assert contact.latitude == pytest.approx(37.77)
    assert contact.longitude == pytest.approx(-122.42)
    assert contact.geocoded_location == "San Francisco, CA"
    assert contact.geocoded_at is not None


@pytest.mark.asyncio
async def test_do_geocode_skips_when_unchanged(db_session, user_factory):
    from unittest.mock import AsyncMock, MagicMock
    user = await user_factory()
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name="Bob",
        location="Berlin",
        geocoded_location="Berlin",
        latitude=52.52,
        longitude=13.40,
        geocoded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db_session.add(contact)
    await db_session.commit()

    geocoder = MagicMock()
    geocoder.geocode = AsyncMock()
    await _do_geocode(db_session, str(contact.id), geocoder)
    geocoder.geocode.assert_not_called()


@pytest.mark.asyncio
async def test_do_geocode_clears_when_location_blanked(db_session, user_factory):
    from unittest.mock import AsyncMock, MagicMock
    user = await user_factory()
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name="Carol",
        location=None,
        geocoded_location="Berlin",
        latitude=52.52,
        longitude=13.40,
    )
    db_session.add(contact)
    await db_session.commit()

    geocoder = MagicMock()
    geocoder.geocode = AsyncMock()
    await _do_geocode(db_session, str(contact.id), geocoder)
    await db_session.refresh(contact)

    assert contact.latitude is None
    assert contact.longitude is None
    assert contact.geocoded_location is None
    assert contact.geocoded_at is not None
    geocoder.geocode.assert_not_called()


@pytest.mark.asyncio
async def test_do_geocode_sets_sentinel_on_not_found(db_session, user_factory):
    from unittest.mock import AsyncMock
    from app.services.geocoding import GeocodingNotFoundError

    user = await user_factory()
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name="Dan",
        location="asdfghjkl",
    )
    db_session.add(contact)
    await db_session.commit()

    geocoder = AsyncMock()
    geocoder.geocode = AsyncMock(side_effect=GeocodingNotFoundError("no"))
    await _do_geocode(db_session, str(contact.id), geocoder)
    await db_session.refresh(contact)

    assert contact.latitude is None
    assert contact.longitude is None
    assert contact.geocoded_location == "asdfghjkl"
    assert contact.geocoded_at is not None
