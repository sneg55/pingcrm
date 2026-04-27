"""Tests for contact_resolver — race-safe find_or_create per identity axis.

Treats as duplicates: any two contacts (same user) sharing exactly:
  - any email (case-insensitive)
  - linkedin_profile_id (slug)
  - telegram_user_id  / telegram_username (case-insensitive)
  - twitter_user_id   / twitter_handle    (case-insensitive)
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.contact import Contact
from app.models.user import User
from app.services import contact_resolver


# ---------------------------------------------------------------------------
# normalize_email
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Bob@Example.com", "bob@example.com"),
        ("  bob@example.com  ", "bob@example.com"),
        ("BOB+work@EXAMPLE.com", "bob+work@example.com"),  # plus-aliases preserved
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_email(raw, expected):
    assert contact_resolver.normalize_email(raw) == expected


# ---------------------------------------------------------------------------
# normalize_handle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("@JackDorsey", "jackdorsey"),
        ("JackDorsey", "jackdorsey"),
        ("  @jack  ", "jack"),
        ("", None),
        ("@", None),
        (None, None),
    ],
)
def test_normalize_handle(raw, expected):
    assert contact_resolver.normalize_handle(raw) == expected


# ---------------------------------------------------------------------------
# find_or_create_contact_by_email
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_email_create_when_missing(db: AsyncSession, test_user: User):
    contact, created = await contact_resolver.find_or_create_contact_by_email(
        db, test_user.id, "Bob@Example.com", defaults={"full_name": "Bob"}
    )
    await db.commit()

    assert created is True
    assert contact.full_name == "Bob"
    assert contact.emails == ["bob@example.com"]


@pytest.mark.asyncio
async def test_email_returns_existing_case_insensitive(
    db: AsyncSession, test_user: User
):
    existing = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Bob",
        emails=["bob@example.com"],
        priority_level="medium",
    )
    db.add(existing)
    await db.commit()

    contact, created = await contact_resolver.find_or_create_contact_by_email(
        db, test_user.id, "BOB@Example.COM", defaults={"full_name": "Should Not Overwrite"}
    )
    await db.commit()

    assert created is False
    assert contact.id == existing.id
    assert contact.full_name == "Bob"  # defaults ignored on existing


@pytest.mark.asyncio
async def test_email_per_user_scoping(db: AsyncSession, test_user: User):
    other = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="x",
        full_name="Other",
    )
    db.add(other)
    await db.commit()

    other_contact = Contact(
        id=uuid.uuid4(),
        user_id=other.id,
        full_name="Bob",
        emails=["bob@example.com"],
        priority_level="medium",
    )
    db.add(other_contact)
    await db.commit()

    contact, created = await contact_resolver.find_or_create_contact_by_email(
        db, test_user.id, "bob@example.com", defaults={"full_name": "Bob"}
    )
    await db.commit()

    assert created is True
    assert contact.id != other_contact.id


@pytest.mark.asyncio
async def test_email_concurrent_creates_produce_one_contact(
    setup_database, test_user: User
):
    """Two parallel transactions must not both insert. Advisory lock or
    similar mechanism must serialize the find-or-create."""
    factory = async_sessionmaker(
        bind=setup_database, class_=AsyncSession, expire_on_commit=False
    )

    async def worker():
        async with factory() as session:
            contact, created = await contact_resolver.find_or_create_contact_by_email(
                session,
                test_user.id,
                "race@example.com",
                defaults={"full_name": "Race"},
            )
            await session.commit()
            return contact.id, created

    results = await asyncio.gather(*(worker() for _ in range(5)))

    ids = {cid for cid, _ in results}
    created_count = sum(1 for _, c in results if c)

    assert len(ids) == 1, f"expected 1 contact, got {len(ids)}: {ids}"
    assert created_count == 1, f"expected exactly 1 creator, got {created_count}"

    # Verify only one row exists
    async with factory() as session:
        r = await session.execute(
            select(Contact).where(
                Contact.user_id == test_user.id,
                Contact.emails.contains(["race@example.com"]),
            )
        )
        rows = r.scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# find_or_create_contact_by_telegram_user_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_user_id_create_when_missing(
    db: AsyncSession, test_user: User
):
    contact, created = await contact_resolver.find_or_create_contact_by_telegram_user_id(
        db, test_user.id, "12345", defaults={"full_name": "TG", "telegram_username": "Foo"}
    )
    await db.commit()

    assert created is True
    assert contact.telegram_user_id == "12345"
    assert contact.telegram_username == "foo"  # normalized on write
    assert contact.full_name == "TG"


@pytest.mark.asyncio
async def test_telegram_user_id_returns_existing(db: AsyncSession, test_user: User):
    existing = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="TG",
        telegram_user_id="12345",
        priority_level="medium",
    )
    db.add(existing)
    await db.commit()

    contact, created = await contact_resolver.find_or_create_contact_by_telegram_user_id(
        db, test_user.id, "12345", defaults={"full_name": "Other"}
    )
    await db.commit()

    assert created is False
    assert contact.id == existing.id


# ---------------------------------------------------------------------------
# find_or_create_contact_by_telegram_username
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_username_case_insensitive(
    db: AsyncSession, test_user: User
):
    existing = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="TG",
        telegram_username="foo",
        priority_level="medium",
    )
    db.add(existing)
    await db.commit()

    contact, created = await contact_resolver.find_or_create_contact_by_telegram_username(
        db, test_user.id, "@FOO", defaults={"full_name": "Other"}
    )
    await db.commit()

    assert created is False
    assert contact.id == existing.id


# ---------------------------------------------------------------------------
# find_or_create_contact_by_twitter_user_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_twitter_user_id_concurrent_creates_produce_one_contact(
    setup_database, test_user: User
):
    """Reproduces the Issa / Francis Erokwu prod bug: two parallel sync
    workers both try to create a contact for the same twitter_user_id."""
    factory = async_sessionmaker(
        bind=setup_database, class_=AsyncSession, expire_on_commit=False
    )

    async def worker():
        async with factory() as session:
            contact, created = await contact_resolver.find_or_create_contact_by_twitter_user_id(
                session,
                test_user.id,
                "987654321",
                defaults={"full_name": "Issa", "twitter_handle": "issa5775"},
            )
            await session.commit()
            return contact.id, created

    results = await asyncio.gather(*(worker() for _ in range(5)))
    ids = {cid for cid, _ in results}
    assert len(ids) == 1

    async with factory() as session:
        r = await session.execute(
            select(Contact).where(
                Contact.user_id == test_user.id,
                Contact.twitter_user_id == "987654321",
            )
        )
        assert len(r.scalars().all()) == 1


# ---------------------------------------------------------------------------
# find_or_create_contact_by_twitter_handle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_twitter_handle_case_insensitive(db: AsyncSession, test_user: User):
    existing = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Francis",
        twitter_handle="lightedcoach",
        priority_level="medium",
    )
    db.add(existing)
    await db.commit()

    contact, created = await contact_resolver.find_or_create_contact_by_twitter_handle(
        db, test_user.id, "@LightedCoach", defaults={"full_name": "Other"}
    )
    await db.commit()

    assert created is False
    assert contact.id == existing.id


# ---------------------------------------------------------------------------
# find_or_create_contact_by_linkedin_profile_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_linkedin_profile_id_concurrent_creates_produce_one_contact(
    setup_database, test_user: User
):
    factory = async_sessionmaker(
        bind=setup_database, class_=AsyncSession, expire_on_commit=False
    )

    async def worker():
        async with factory() as session:
            contact, created = await contact_resolver.find_or_create_contact_by_linkedin_profile_id(
                session,
                test_user.id,
                "sidrmsh",
                defaults={"full_name": "Sid Ramesh"},
            )
            await session.commit()
            return contact.id, created

    results = await asyncio.gather(*(worker() for _ in range(5)))
    ids = {cid for cid, _ in results}
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_linkedin_profile_id_finds_existing_with_different_source(
    db: AsyncSession, test_user: User
):
    """Sid Ramesh in prod: linkedin_profile_id=sidrmsh exists once as
    source=linkedin and another as source=telegram. Resolver must find
    the existing row regardless of source rather than creating a new one."""
    existing = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="Sid Ramesh",
        linkedin_profile_id="sidrmsh",
        source="telegram",
        priority_level="medium",
    )
    db.add(existing)
    await db.commit()

    contact, created = await contact_resolver.find_or_create_contact_by_linkedin_profile_id(
        db, test_user.id, "sidrmsh", defaults={"full_name": "Other", "source": "linkedin"}
    )
    await db.commit()

    assert created is False
    assert contact.id == existing.id
