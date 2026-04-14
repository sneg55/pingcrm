from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.contact import Contact
from app.services.task_jobs.geocoding import _do_backfill


@pytest.mark.asyncio
async def test_backfill_enqueues_only_ungeocoded(db_session, user_factory):
    user = await user_factory()
    c1 = Contact(
        id=uuid.uuid4(), user_id=user.id, full_name="A", location="Paris"
    )  # needs geocode
    c2 = Contact(
        id=uuid.uuid4(), user_id=user.id, full_name="B", location="Berlin",
        geocoded_location="Berlin", latitude=52.5, longitude=13.4,
    )  # already done
    c3 = Contact(
        id=uuid.uuid4(), user_id=user.id, full_name="C", location=None
    )  # no location
    db_session.add_all([c1, c2, c3])
    await db_session.commit()

    mock_task = MagicMock()
    mock_task.delay = MagicMock()

    with patch(
        "app.services.task_jobs.geocoding.geocode_contact", mock_task
    ):
        await _do_backfill(db_session)

    calls = [c.args[0] for c in mock_task.delay.call_args_list]
    assert str(c1.id) in calls
    assert str(c2.id) not in calls
    assert str(c3.id) not in calls
