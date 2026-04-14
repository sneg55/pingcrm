"""Verify the Postgres trigger that strips the '2nd tier' tag when an interaction is inserted."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User


async def _make_contact(db: AsyncSession, user: User, tags: list[str]) -> Contact:
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user.id,
        full_name="Group Friend",
        given_name="Group",
        family_name="Friend",
        tags=tags,
        source="telegram",
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@pytest.mark.asyncio
async def test_inserting_interaction_strips_lowercase_tag(db: AsyncSession, test_user: User):
    contact = await _make_contact(db, test_user, tags=["2nd tier", "friend"])

    db.add(Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        platform="telegram",
        direction="inbound",
        content_preview="hi",
        occurred_at=datetime.now(UTC),
    ))
    await db.commit()
    await db.refresh(contact)

    assert contact.tags == ["friend"]


@pytest.mark.asyncio
async def test_inserting_interaction_strips_titlecase_tag(db: AsyncSession, test_user: User):
    contact = await _make_contact(db, test_user, tags=["2nd Tier"])

    db.add(Interaction(
        id=uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        platform="telegram",
        direction="outbound",
        content_preview="hi",
        occurred_at=datetime.now(UTC),
    ))
    await db.commit()
    await db.refresh(contact)

    assert contact.tags == []


@pytest.mark.asyncio
async def test_trigger_leaves_other_contacts_alone(db: AsyncSession, test_user: User):
    other = await _make_contact(db, test_user, tags=["2nd tier"])
    target = await _make_contact(db, test_user, tags=["2nd tier"])

    db.add(Interaction(
        id=uuid.uuid4(),
        contact_id=target.id,
        user_id=test_user.id,
        platform="telegram",
        direction="inbound",
        content_preview="hi",
        occurred_at=datetime.now(UTC),
    ))
    await db.commit()
    await db.refresh(target)
    await db.refresh(other)

    assert target.tags == []
    assert other.tags == ["2nd tier"]
