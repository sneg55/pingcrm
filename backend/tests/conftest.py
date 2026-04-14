"""Shared test fixtures using real PostgreSQL test database."""
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force test config before any app imports
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["ENCRYPTION_KEY"] = "HiuobeEdnSk93dMtnycRm8Kob9D3-7-vCw3_L0YG9Ek="
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://localhost:5432/pingcrm_test",
)

from app.core.auth import create_access_token, hash_password
from app.core.database import Base, get_db
from app.main import fastapi_app as app
from app.models.contact import Contact
from app.models.detected_event import DetectedEvent
from app.models.follow_up import FollowUpSuggestion
from app.models.google_account import GoogleAccount
from app.models.identity_match import IdentityMatch
from app.models.interaction import Interaction
from app.models.notification import Notification
from app.models.contact_merge import ContactMerge
from app.models.user import User


@pytest_asyncio.fixture(autouse=True, loop_scope="function")
async def setup_database():
    """Create all tables before each test, drop after."""
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def db(setup_database):
    """Provide a clean database session for each test."""
    session_factory = async_sessionmaker(
        bind=setup_database, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(loop_scope="function")
async def client(setup_database):
    """Async HTTP test client with shared DB session."""
    session_factory = async_sessionmaker(
        bind=setup_database, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(loop_scope="function")
async def test_user(db: AsyncSession) -> User:
    """Create and return a test user."""
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        hashed_password=hash_password("testpass123"),
        full_name="Test User",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(loop_scope="function")
async def auth_headers(test_user: User) -> dict[str, str]:
    """Return Authorization headers for the test user."""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="function")
async def test_contact(db: AsyncSession, test_user: User) -> Contact:
    """Create and return a test contact."""
    contact = Contact(
        id=uuid.uuid4(),
        user_id=test_user.id,
        full_name="John Doe",
        given_name="John",
        family_name="Doe",
        emails=["john@example.com"],
        phones=["+1234567890"],
        company="Acme Inc",
        title="CEO",
        relationship_score=5,
        source="manual",
        last_interaction_at=datetime.now(UTC) - timedelta(days=5),
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@pytest_asyncio.fixture(loop_scope="function")
async def test_interaction(db: AsyncSession, test_user: User, test_contact: Contact) -> Interaction:
    """Create and return a test interaction."""
    interaction = Interaction(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=test_user.id,
        platform="email",
        direction="inbound",
        content_preview="Hey, how are you doing?",
        occurred_at=datetime.now(UTC) - timedelta(days=5),
    )
    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)
    return interaction


@pytest_asyncio.fixture(loop_scope="function")
async def test_suggestion(db: AsyncSession, test_user: User, test_contact: Contact) -> FollowUpSuggestion:
    """Create and return a test follow-up suggestion."""
    suggestion = FollowUpSuggestion(
        id=uuid.uuid4(),
        contact_id=test_contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="Hey John, it's been a while!",
        suggested_channel="email",
        status="pending",
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


@pytest_asyncio.fixture(loop_scope="function")
async def db_session(setup_database):
    """Alias for db — used by Task 5+ tests."""
    session_factory = async_sessionmaker(
        bind=setup_database, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(loop_scope="function")
def user_factory(db_session: AsyncSession):
    """Factory fixture for creating users with arbitrary fields."""
    async def _factory(**kwargs) -> User:
        defaults = dict(
            id=uuid.uuid4(),
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=hash_password("testpass123"),
            full_name="Test User",
        )
        defaults.update(kwargs)
        user = User(**defaults)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user
    return _factory


@pytest_asyncio.fixture(loop_scope="function")
async def test_notification(db: AsyncSession, test_user: User) -> Notification:
    """Create and return a test notification."""
    notif = Notification(
        id=uuid.uuid4(),
        user_id=test_user.id,
        notification_type="suggestion",
        title="3 new follow-up suggestions",
        body="You have 3 new people to reach out to this week.",
        link="/suggestions",
        read=False,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return notif
