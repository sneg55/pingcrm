"""Database session management for the MCP server.

Creates a module-level engine at import time (reuses backend config).
Provides get_session() async context manager for per-tool-call sessions.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session():
    """Yield a fresh async session for one tool call."""
    async with _session_factory() as session:
        yield session
