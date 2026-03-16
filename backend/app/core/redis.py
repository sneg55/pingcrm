"""Async Redis client for ephemeral state (OAuth nonces, rate-limit caches).

NOTE: The connection pool is cached per event loop.  Celery tasks use _run()
which creates a fresh event loop for each coroutine invocation.  A pool
bound to a closed loop causes "Event loop is closed" errors, so we
invalidate the cached pool whenever the current loop differs from the one
that created it.
"""
from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from app.core.config import settings

_pool: aioredis.ConnectionPool | None = None
_pool_loop_id: int | None = None


def get_redis_pool() -> aioredis.ConnectionPool:
    global _pool, _pool_loop_id
    try:
        current_loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        current_loop_id = None

    if _pool is None or (current_loop_id is not None and current_loop_id != _pool_loop_id):
        # Pool was created on a different (now-closed) loop — recreate
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL, decode_responses=True
        )
        _pool_loop_id = current_loop_id
    return _pool


def get_redis() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=get_redis_pool())
