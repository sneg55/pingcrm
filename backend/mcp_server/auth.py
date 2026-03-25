"""MCP API key generation, hashing, and verification."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User


def generate_api_key() -> str:
    """Generate a new API key with pingcrm_ prefix."""
    raw = secrets.token_urlsafe(32)
    return f"pingcrm_{raw}"


def hash_api_key(key: str) -> str:
    """HMAC-SHA256 hash for direct DB lookup."""
    return hmac.new(
        settings.SECRET_KEY.encode(),
        key.encode(),
        hashlib.sha256,
    ).hexdigest()


async def verify_api_key(key: str, db: AsyncSession) -> User | None:
    """Look up user by API key hash. Returns None if not found."""
    key_hash = hash_api_key(key)
    result = await db.execute(
        select(User).where(User.mcp_api_key_hash == key_hash)
    )
    return result.scalar_one_or_none()
