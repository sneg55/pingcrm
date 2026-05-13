import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TRANSACTION POLICY (Phase 5.2)
# ---------------------------------------------------------------------------
# API route handlers MUST use flush() only — never call commit() directly.
#   - flush() sends SQL to the DB within the current transaction without
#     finalising it, allowing subsequent operations to see the changes.
#   - commit() is the exclusive responsibility of get_db() (see below).
#
# get_db() dependency owns the transaction lifecycle:
#   - On successful handler return  → session.commit()
#   - On any exception              → session.rollback()
#   This keeps transaction boundaries at the HTTP request level.
#
# Celery tasks use task_session() (see below) which creates an isolated
# engine per task invocation.  They are responsible for their own commit/rollback.
#
# Reference: Phase 5.2 in Plans-archive.md
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=20,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


# ---------------------------------------------------------------------------
# Task-scoped session for Celery workers
# ---------------------------------------------------------------------------
# asyncio.run() creates a new event loop per task. Reusing the module-level
# engine across event loops can cause "another operation is in progress"
# errors because asyncpg connections are tied to a single event loop.
#
# task_session() creates a short-lived engine + session scoped to one task
# invocation, then disposes the engine when done. This guarantees connection
# isolation between concurrent Celery tasks.
# ---------------------------------------------------------------------------

from contextlib import asynccontextmanager


@asynccontextmanager
async def task_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated async session for a Celery task.

    Creates a dedicated engine (with a small pool) per task invocation so
    that concurrent Celery tasks never share asyncpg connections across
    event loops.
    """
    task_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
    )
    factory = async_sessionmaker(
        bind=task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        try:
            yield session
        except BaseException:
            # BaseException also catches CancelledError / SoftTimeLimitExceeded,
            # so an idle-in-transaction row lock can't survive a worker kill path.
            await session.rollback()
            raise
        finally:
            await session.close()
    await task_engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a database session for a single request.

    Transaction behaviour (auto-commit on success):
        - Yields the session to the route handler.
        - Calls commit() when the handler returns without raising.
        - Calls rollback() if any exception propagates out of the handler.
        - Always closes the session in the finally block.

    Route handlers MUST use flush() instead of commit() so that this
    dependency retains exclusive ownership of the transaction boundary.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.exception("get_db transaction rolled back")
            await session.rollback()
            raise
        finally:
            await session.close()
