"""Shared test fixtures using real PostgreSQL test database."""
import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force test config before any app imports
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["ENCRYPTION_KEY"] = "HiuobeEdnSk93dMtnycRm8Kob9D3-7-vCw3_L0YG9Ek="
_BASE_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://localhost:5432/pingcrm_test",
)

# Under pytest-xdist each worker gets its own database so concurrent tests never
# clear each other's rows. The worker id ("gw0", "gw1", ...) is set in the worker
# subprocess before this module imports, so the URL is finalized here once.
_XDIST_WORKER = os.environ.get("PYTEST_XDIST_WORKER")
if _XDIST_WORKER and _XDIST_WORKER != "master":
    _server, _db_name = _BASE_DATABASE_URL.rsplit("/", 1)
    _BASE_DATABASE_URL = f"{_server}/{_db_name}_{_XDIST_WORKER}"

os.environ["DATABASE_URL"] = _BASE_DATABASE_URL

from sqlalchemy import text

from app.core.auth import create_access_token, hash_password
from app.core.database import Base, get_db
from app.main import fastapi_app as app
from app.models._triggers import CLEAR_2ND_TIER_FUNCTION, CLEAR_2ND_TIER_TRIGGER
from app.models.contact import Contact
from app.models.detected_event import DetectedEvent
from app.models.follow_up import FollowUpSuggestion
from app.models.google_account import GoogleAccount
from app.models.identity_match import IdentityMatch
from app.models.interaction import Interaction
from app.models.notification import Notification
from app.models.contact_merge import ContactMerge
from app.models.user import User

# Speed up password hashing in tests: bcrypt's default cost (~12 rounds, ~250ms/hash)
# dominates fixture setup time across hundreds of tests. 4 rounds is the bcrypt minimum
# and verifies identically — verify_password() reads the cost factor from the hash itself,
# so behavior is preserved. Reassigning the module global is picked up by hash_password()/
# verify_password(), which resolve pwd_context at call time.
import app.core.auth as _auth_module

_auth_module.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4)


async def _ensure_database(url: str) -> None:
    """Create the target database if it doesn't exist (used for per-worker xdist DBs)."""
    import asyncpg

    server, db_name = url.rsplit("/", 1)
    maintenance_dsn = server.replace("postgresql+asyncpg", "postgresql") + "/postgres"
    conn = await asyncpg.connect(dsn=maintenance_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _create_schema(url: str) -> None:
    engine = create_async_engine(url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text(CLEAR_2ND_TIER_FUNCTION))
            await conn.execute(text(CLEAR_2ND_TIER_TRIGGER))
    finally:
        await engine.dispose()


async def _drop_schema(url: str) -> None:
    engine = create_async_engine(url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create the schema once for the whole test session, drop it at the end.

    Per-test isolation is handled by truncating tables in ``setup_database`` instead
    of rebuilding the schema for every test, which is dramatically faster. The
    schema DDL runs on its own short-lived event loop (``asyncio.run``) so it stays
    independent of pytest-asyncio's per-test loops and never shares an asyncpg
    connection pool across loops.
    """
    url = os.environ["DATABASE_URL"]

    async def _setup() -> None:
        await _ensure_database(url)
        await _create_schema(url)

    asyncio.run(_setup())
    yield
    asyncio.run(_drop_schema(url))


# Per-test cleanup statements: DELETE child tables first so foreign keys are satisfied.
# DELETE on the (near-)empty test tables benchmarks ~8x faster than TRUNCATE, which pays
# a fixed ACCESS EXCLUSIVE lock + RESTART IDENTITY cost regardless of row count. The only
# trigger in the schema fires AFTER INSERT ON interactions, so DELETE has no side effects.
_DELETE_STATEMENTS = [
    text(f'DELETE FROM "{table.name}"') for table in reversed(Base.metadata.sorted_tables)
]


@pytest_asyncio.fixture(autouse=True, loop_scope="function")
async def setup_database(_schema):
    """Give each test a clean database by deleting all rows.

    The engine is created on the test's own event loop so its asyncpg connections
    stay loop-local. Clearing rows (DELETE) instead of rebuilding the schema per test
    keeps each test fully isolated at a fraction of the cost.
    """
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        for stmt in _DELETE_STATEMENTS:
            await conn.execute(stmt)
    yield engine
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
