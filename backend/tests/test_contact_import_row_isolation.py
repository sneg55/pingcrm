from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.user import User
from app.services import organization_service
from app.services.contact_import import import_csv, import_linkedin_connections

POISON_NAME = "Poison Row"


@pytest_asyncio.fixture(loop_scope="function")
async def user(db: AsyncSession) -> User:
    from app.core.auth import hash_password

    u = User(
        id=uuid.uuid4(),
        email=f"isolation_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("pw"),
        full_name="Isolation Test User",
    )
    db.add(u)
    await db.commit()
    return u


@pytest.fixture
def poison_org_step(monkeypatch):
    original = organization_service.auto_create_organization

    async def _auto_create(contact, user_id, db):
        if contact.full_name == POISON_NAME:
            await db.execute(text("SELECT 1/0"))
        return await original(contact, user_id, db)

    monkeypatch.setattr(organization_service, "auto_create_organization", _auto_create)


async def _persisted_names(db: AsyncSession, user: User) -> set[str]:
    await db.commit()
    result = await db.execute(select(Contact.full_name).where(Contact.user_id == user.id))
    return set(result.scalars().all())


@pytest.mark.asyncio
async def test_import_csv_failing_row_does_not_discard_other_rows(
    db: AsyncSession, user: User, poison_org_step
):
    csv_bytes = (
        "full_name,emails\n"
        "Before Row,before@example.com\n"
        f"{POISON_NAME},poison@example.com\n"
        "After Row,after@example.com\n"
    ).encode()

    result = await import_csv(csv_bytes, user.id, db)

    assert [c["full_name"] for c in result["created"]] == ["Before Row", "After Row"]
    assert len(result["errors"]) == 1
    assert result["errors"][0].startswith("Row 2:")
    assert await _persisted_names(db, user) == {"Before Row", "After Row"}


@pytest.mark.asyncio
async def test_import_linkedin_connections_failing_row_does_not_discard_other_rows(
    db: AsyncSession, user: User, poison_org_step
):
    first, last = POISON_NAME.split()
    csv_bytes = (
        "First Name,Last Name,Email Address,Company,Position,URL\n"
        "Before,Row,,Acme,Eng,https://www.linkedin.com/in/before-row\n"
        f"{first},{last},,Acme,Eng,https://www.linkedin.com/in/poison-row\n"
        "After,Row,,Acme,Eng,https://www.linkedin.com/in/after-row\n"
    ).encode()

    result = await import_linkedin_connections(csv_bytes, user.id, db)

    assert result["created"] == 2
    assert len(result["errors"]) == 1
    assert result["errors"][0].startswith("Row 2:")
    assert await _persisted_names(db, user) == {"Before Row", "After Row"}


@pytest.mark.asyncio
async def test_import_csv_poison_row_count_matches_database(
    db: AsyncSession, user: User, poison_org_step
):
    csv_bytes = (
        "full_name\n"
        + "".join(f"Row {n}\n" for n in range(5))
        + f"{POISON_NAME}\n"
        + "".join(f"Row {n}\n" for n in range(5, 10))
    ).encode()

    result = await import_csv(csv_bytes, user.id, db)
    await db.commit()
    count = await db.scalar(select(func.count()).select_from(Contact).where(Contact.user_id == user.id))

    assert len(result["created"]) == 10
    assert count == 10
