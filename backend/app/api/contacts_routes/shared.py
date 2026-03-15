from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.responses import Envelope


def envelope(data: Any, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


__all__ = [
    "uuid",
    "datetime",
    "Any",
    "Depends",
    "HTTPException",
    "Query",
    "status",
    "func",
    "select",
    "AsyncSession",
    "get_current_user",
    "get_db",
    "Contact",
    "User",
    "Envelope",
    "envelope",
]
