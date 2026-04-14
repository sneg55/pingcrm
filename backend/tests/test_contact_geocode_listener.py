from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.models.contact import Contact


@pytest.mark.asyncio
async def test_listener_enqueues_on_new_contact_with_location(db_session, user_factory):
    user = await user_factory()
    with patch("app.services.task_jobs.geocoding.geocode_contact") as mock_task:
        contact = Contact(
            id=uuid.uuid4(), user_id=user.id, full_name="Alice", location="Paris"
        )
        db_session.add(contact)
        await db_session.commit()
        mock_task.delay.assert_called_once_with(str(contact.id))


@pytest.mark.asyncio
async def test_listener_skips_when_location_unchanged(db_session, user_factory):
    user = await user_factory()
    contact = Contact(
        id=uuid.uuid4(), user_id=user.id, full_name="Bob", location="Paris"
    )
    db_session.add(contact)
    await db_session.commit()
    with patch("app.services.task_jobs.geocoding.geocode_contact") as mock_task:
        contact.full_name = "Bob B."
        await db_session.commit()
        mock_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_listener_enqueues_when_location_changes(db_session, user_factory):
    user = await user_factory()
    contact = Contact(
        id=uuid.uuid4(), user_id=user.id, full_name="Carol", location="Paris"
    )
    db_session.add(contact)
    await db_session.commit()
    with patch("app.services.task_jobs.geocoding.geocode_contact") as mock_task:
        contact.location = "London"
        await db_session.commit()
        mock_task.delay.assert_called_once_with(str(contact.id))
