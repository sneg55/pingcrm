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
