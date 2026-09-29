from __future__ import annotations

import uuid
from contextvars import ContextVar

current_user_id: ContextVar[uuid.UUID | None] = ContextVar("mcp_current_user_id", default=None)


def require_user_id() -> uuid.UUID:
    user_id = current_user_id.get()
    if user_id is None:
        raise PermissionError("MCP tool called without an authenticated user")
    return user_id
