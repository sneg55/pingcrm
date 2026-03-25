# MCP Server Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose PingCRM data as an MCP server with 6 read-only tools, supporting stdio (local) and SSE (remote) transports, with per-user API key auth for SSE.

**Architecture:** A Python MCP server inside `backend/mcp_server/` that directly queries the PostgreSQL database using SQLAlchemy async (same as Celery workers). Tools return Markdown-formatted text for LLM consumption. API keys are HMAC-SHA256 hashed for sub-millisecond DB lookup. The server shares the backend Docker image.

**Tech Stack:** Python, `mcp` SDK (>=1.0.0,<2.0.0), SQLAlchemy async, HMAC-SHA256, FastAPI (for API key endpoints)

**Spec:** `docs/specs/2026-03-25-mcp-server-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/mcp_server/__init__.py` | Package marker |
| Create | `backend/mcp_server/server.py` | Entry point, CLI args, transport setup, tool registration |
| Create | `backend/mcp_server/db.py` | Module-level engine, async session factory |
| Create | `backend/mcp_server/auth.py` | HMAC-SHA256 key hashing, user lookup by key |
| Create | `backend/mcp_server/tools/__init__.py` | Package marker |
| Create | `backend/mcp_server/tools/contacts.py` | search_contacts, get_contact tools |
| Create | `backend/mcp_server/tools/interactions.py` | get_interactions tool |
| Create | `backend/mcp_server/tools/suggestions.py` | get_suggestions tool |
| Create | `backend/mcp_server/tools/notifications.py` | get_notifications tool |
| Create | `backend/mcp_server/tools/dashboard.py` | get_dashboard_stats tool |
| Create | `backend/mcp_server/README.md` | Setup instructions for Claude Desktop / Cursor |
| Create | `backend/tests/test_mcp_server.py` | All MCP tests |
| Modify | `backend/app/models/user.py` | Add `mcp_api_key_hash` column |
| Modify | `backend/app/schemas/responses.py` | Add McpKeyData, McpKeyRevokedData, McpKeyStatusData |
| Modify | `backend/app/api/settings.py` | Add MCP key generate/revoke/status endpoints |
| Modify | `backend/requirements.txt` | Add `mcp>=1.0.0,<2.0.0` |
| Create | `backend/alembic/versions/xxxx_add_mcp_api_key_hash.py` | Migration for new column |

---

## Chunk 1: Foundation — DB Migration + API Key Management

### Task 1: Add mcp_api_key_hash column + migration

**Files:**
- Modify: `backend/app/models/user.py`
- Create: Alembic migration
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add column to User model**

In `backend/app/models/user.py`, add after the existing columns:

```python
mcp_api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
```

Add `String` to the `sqlalchemy` imports if not already present.

- [ ] **Step 2: Add mcp dependency**

In `backend/requirements.txt`, add:

```
mcp>=1.0.0,<2.0.0
```

- [ ] **Step 3: Generate Alembic migration**

```bash
cd backend && alembic revision --autogenerate -m "add mcp_api_key_hash column to users"
```

Verify the migration has `op.add_column('users', sa.Column('mcp_api_key_hash', sa.String(128), nullable=True))` in `upgrade()` and `op.drop_column('users', 'mcp_api_key_hash')` in `downgrade()`.

- [ ] **Step 4: Run migration locally**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/ backend/requirements.txt
git commit -m "feat(mcp): add mcp_api_key_hash column to users + mcp dependency"
```

---

### Task 2: API key auth module

**Files:**
- Create: `backend/mcp_server/__init__.py`
- Create: `backend/mcp_server/auth.py`
- Create: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests for key hashing and verification**

Create `backend/tests/test_mcp_server.py`:

```python
"""Tests for MCP Server (issue #7)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMcpAuth:
    """Tests for mcp_server.auth module."""

    def test_generate_api_key_has_prefix(self):
        from mcp_server.auth import generate_api_key
        key = generate_api_key()
        assert key.startswith("pingcrm_")
        assert len(key) > 40  # prefix + 32 bytes base64url

    def test_hash_api_key_is_deterministic(self):
        from mcp_server.auth import hash_api_key
        key = "pingcrm_testkey123"
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_hash_api_key_differs_for_different_keys(self):
        from mcp_server.auth import hash_api_key
        h1 = hash_api_key("pingcrm_key1")
        h2 = hash_api_key("pingcrm_key2")
        assert h1 != h2

    @pytest.mark.asyncio
    async def test_verify_api_key_returns_user(self):
        from mcp_server.auth import verify_api_key, hash_api_key

        key = "pingcrm_testkey"
        key_hash = hash_api_key(key)

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.mcp_api_key_hash = key_hash

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        db = AsyncMock()
        db.execute.return_value = mock_result

        user = await verify_api_key(key, db)
        assert user is mock_user

    @pytest.mark.asyncio
    async def test_verify_api_key_returns_none_for_invalid(self):
        from mcp_server.auth import verify_api_key

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result

        user = await verify_api_key("pingcrm_wrong", db)
        assert user is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_server.py::TestMcpAuth -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement auth module**

Create `backend/mcp_server/__init__.py` (empty file).

Create `backend/mcp_server/auth.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_server.py::TestMcpAuth -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/ backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add API key generation and HMAC-SHA256 auth"
```

---

### Task 3: API key management endpoints + response schemas

**Files:**
- Modify: `backend/app/schemas/responses.py`
- Modify: `backend/app/api/settings.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests for the endpoints**

Append to `backend/tests/test_mcp_server.py`:

```python
class TestMcpKeyEndpoints:
    """Tests for MCP key management API endpoints."""

    def test_response_schemas_exist(self):
        from app.schemas.responses import McpKeyData, McpKeyRevokedData, McpKeyStatusData
        assert McpKeyData(key="pingcrm_test").key == "pingcrm_test"
        assert McpKeyRevokedData(revoked=True).revoked is True
        assert McpKeyStatusData(has_key=False).has_key is False
```

- [ ] **Step 2: Add response schemas**

In `backend/app/schemas/responses.py`, add:

```python
class McpKeyData(BaseModel):
    key: str

class McpKeyRevokedData(BaseModel):
    revoked: bool

class McpKeyStatusData(BaseModel):
    has_key: bool
```

- [ ] **Step 3: Add API endpoints**

In `backend/app/api/settings.py`, add the three MCP key endpoints:

```python
from mcp_server.auth import generate_api_key, hash_api_key
from app.schemas.responses import Envelope, McpKeyData, McpKeyRevokedData, McpKeyStatusData


@router.get("/mcp-key", response_model=Envelope[McpKeyStatusData])
async def get_mcp_key_status(
    current_user: User = Depends(get_current_user),
) -> Envelope[McpKeyStatusData]:
    return {"data": McpKeyStatusData(has_key=bool(current_user.mcp_api_key_hash)), "error": None}


@router.post("/mcp-key", response_model=Envelope[McpKeyData])
async def generate_mcp_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[McpKeyData]:
    key = generate_api_key()
    current_user.mcp_api_key_hash = hash_api_key(key)
    await db.flush()
    return {"data": McpKeyData(key=key), "error": None}


@router.delete("/mcp-key", response_model=Envelope[McpKeyRevokedData])
async def revoke_mcp_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[McpKeyRevokedData]:
    current_user.mcp_api_key_hash = None
    await db.flush()
    return {"data": McpKeyRevokedData(revoked=True), "error": None}
```

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_server.py -v`
Expected: All passed

Also verify CI guard:
Run: `cd backend && PYTHONPATH=. .venv/bin/python scripts/check_response_models.py`
Expected: Pass (all new endpoints have response_model)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/responses.py backend/app/api/settings.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add API key management endpoints (generate/revoke/status)"
```

---

## Chunk 2: MCP Server Core

### Task 4: Database session module

**Files:**
- Create: `backend/mcp_server/db.py`

- [ ] **Step 1: Implement db.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/mcp_server/db.py
git commit -m "feat(mcp): add database session module"
```

---

### Task 5: MCP server entry point

**Files:**
- Create: `backend/mcp_server/server.py`
- Create: `backend/mcp_server/tools/__init__.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write test for server module**

Append to `backend/tests/test_mcp_server.py`:

```python
class TestMcpServer:
    """Tests for the MCP server setup."""

    def test_server_module_importable(self):
        import mcp_server.server
        assert hasattr(mcp_server.server, "mcp_app")

    def test_parse_args_defaults(self):
        from mcp_server.server import parse_args
        args = parse_args([])
        assert args.sse is False
        assert args.port == 8808
        assert args.user_email is None

    def test_parse_args_sse_mode(self):
        from mcp_server.server import parse_args
        args = parse_args(["--sse", "--port", "9000", "--user-email", "test@example.com"])
        assert args.sse is True
        assert args.port == 9000
        assert args.user_email == "test@example.com"
```

- [ ] **Step 2: Implement server.py**

Create `backend/mcp_server/tools/__init__.py` (empty file).

Create `backend/mcp_server/server.py`:

```python
"""PingCRM MCP Server — expose CRM data to AI clients.

Usage:
    python -m mcp_server.server                        # stdio (local)
    python -m mcp_server.server --user-email user@x.com  # stdio with explicit user
    python -m mcp_server.server --sse --port 8808      # SSE (remote)
"""
from __future__ import annotations

import argparse
import logging

from mcp.server import Server

logger = logging.getLogger(__name__)

mcp_app = Server("pingcrm")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PingCRM MCP Server")
    parser.add_argument("--sse", action="store_true", help="Enable SSE transport (remote)")
    parser.add_argument("--port", type=int, default=8808, help="SSE port (default: 8808)")
    parser.add_argument("--user-email", type=str, default=None, help="User email for stdio mode")
    return parser.parse_args(argv)


def _register_tools():
    """Import tool modules to register @mcp_app.tool() handlers."""
    from mcp_server.tools import contacts, interactions, suggestions, notifications, dashboard  # noqa: F401


async def run_stdio(user_email: str | None = None):
    """Run in stdio mode (local subprocess)."""
    from mcp.server.stdio import stdio_server

    _register_tools()
    logger.info("Starting PingCRM MCP server (stdio mode)")

    async with stdio_server() as (read_stream, write_stream):
        await mcp_app.run(read_stream, write_stream, mcp_app.create_initialization_options())


async def run_sse(port: int):
    """Run in SSE mode (remote HTTP)."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    import uvicorn

    _register_tools()
    logger.info("Starting PingCRM MCP server (SSE mode on port %d)", port)

    sse = SseServerTransport("/mcp/messages")

    async def handle_sse(request):
        # Auth check
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Missing API key"}, status_code=401)

        key = auth_header[7:]
        from mcp_server.db import get_session
        from mcp_server.auth import verify_api_key
        async with get_session() as db:
            user = await verify_api_key(key, db)
        if not user:
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Invalid API key"}, status_code=401)

        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_app.run(streams[0], streams[1], mcp_app.create_initialization_options())

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    app = Starlette(routes=[
        Route("/mcp/sse", endpoint=handle_sse),
        Route("/mcp/messages", endpoint=handle_messages, methods=["POST"]),
    ])

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main():
    import asyncio
    args = parse_args()
    if args.sse:
        asyncio.run(run_sse(args.port))
    else:
        asyncio.run(run_stdio(args.user_email))


if __name__ == "__main__":
    main()
```

Also create `backend/mcp_server/__main__.py` so `python -m mcp_server.server` works:

```python
from mcp_server.server import main
main()
```

Wait — actually `python -m mcp_server.server` runs `server.py` as `__main__`, which already has `if __name__ == "__main__": main()`. So we just need the package-level `__main__.py` for `python -m mcp_server`:

Create `backend/mcp_server/__main__.py`:

```python
from mcp_server.server import main
main()
```

- [ ] **Step 3: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_server.py::TestMcpServer -v`
Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add backend/mcp_server/
git commit -m "feat(mcp): add server entry point with stdio + SSE transports"
```

---

## Chunk 3: Tools

### Task 6: search_contacts + get_contact tools

**Files:**
- Create: `backend/mcp_server/tools/contacts.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

Append to `backend/tests/test_mcp_server.py`:

```python
class TestContactTools:
    """Tests for MCP contact tools."""

    @pytest.mark.asyncio
    async def test_search_contacts_returns_markdown_table(self):
        from mcp_server.tools.contacts import _search_contacts

        contact = MagicMock()
        contact.full_name = "Jane Doe"
        contact.company = "Acme Corp"
        contact.title = "CTO"
        contact.relationship_score = 8
        contact.last_interaction_at = None
        contact.tags = ["investor", "tech"]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [contact]

        db = AsyncMock()
        db.execute.return_value = mock_result

        user_id = uuid.uuid4()
        result = await _search_contacts(user_id, db, query="Jane", limit=20)

        assert "Jane Doe" in result
        assert "Acme Corp" in result
        assert "CTO" in result

    @pytest.mark.asyncio
    async def test_search_contacts_empty(self):
        from mcp_server.tools.contacts import _search_contacts

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _search_contacts(uuid.uuid4(), db, limit=20)
        assert "No contacts" in result

    @pytest.mark.asyncio
    async def test_get_contact_by_id(self):
        from mcp_server.tools.contacts import _get_contact

        contact = MagicMock()
        contact.id = uuid.uuid4()
        contact.full_name = "Jane Doe"
        contact.title = "CTO"
        contact.company = "Acme Corp"
        contact.emails = ["jane@acme.com"]
        contact.phones = []
        contact.relationship_score = 8
        contact.interaction_count = 15
        contact.last_interaction_at = None
        contact.tags = ["investor"]
        contact.priority_level = "high"
        contact.twitter_bio = "Building things"
        contact.linkedin_headline = "CTO at Acme"
        contact.linkedin_bio = None
        contact.telegram_bio = None
        contact.avatar_url = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = contact

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_contact(uuid.uuid4(), db, contact_id=str(contact.id))
        assert "Jane Doe" in result
        assert "CTO" in result
        assert "Building things" in result

    @pytest.mark.asyncio
    async def test_get_contact_not_found(self):
        from mcp_server.tools.contacts import _get_contact

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_contact(uuid.uuid4(), db, contact_id=str(uuid.uuid4()))
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_get_contact_by_name_fuzzy(self):
        from mcp_server.tools.contacts import _get_contact

        contact = MagicMock()
        contact.full_name = "Jane Doe"
        contact.title = "CTO"
        contact.company = "Acme"
        contact.emails = []
        contact.phones = []
        contact.relationship_score = 7
        contact.interaction_count = 10
        contact.last_interaction_at = None
        contact.tags = []
        contact.priority_level = "high"
        contact.twitter_bio = None
        contact.linkedin_headline = None
        contact.linkedin_bio = None
        contact.telegram_bio = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [contact]

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_contact(uuid.uuid4(), db, name="jane")
        assert "Jane Doe" in result

    @pytest.mark.asyncio
    async def test_get_contact_no_params(self):
        from mcp_server.tools.contacts import _get_contact

        db = AsyncMock()
        result = await _get_contact(uuid.uuid4(), db)
        assert "Provide either" in result

    @pytest.mark.asyncio
    async def test_get_contact_invalid_uuid(self):
        from mcp_server.tools.contacts import _get_contact

        db = AsyncMock()
        result = await _get_contact(uuid.uuid4(), db, contact_id="not-a-uuid")
        assert "Invalid" in result
```

- [ ] **Step 2: Implement contacts.py**

Create `backend/mcp_server/tools/contacts.py`:

```python
"""MCP tools: search_contacts and get_contact."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.services.contact_search import build_contact_filter_query

logger = logging.getLogger(__name__)

# Score tier mapping (spec uses warm/cold; code uses active/dormant)
_SCORE_MAP = {"strong": "strong", "warm": "active", "cold": "dormant"}


async def _search_contacts(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    query: str | None = None,
    tag: str | None = None,
    score: str | None = None,
    priority: str | None = None,
    limit: int = 20,
) -> str:
    """Search contacts and return Markdown table."""
    mapped_score = _SCORE_MAP.get(score) if score else None
    stmt = build_contact_filter_query(
        user_id,
        search=query,
        tag=tag,
        score=mapped_score,
        priority=priority,
    ).limit(min(limit, 50))

    result = await db.execute(stmt)
    contacts = result.scalars().all()

    if not contacts:
        return "No contacts match your search."

    lines = ["| Name | Company | Title | Score | Last Interaction | Tags |",
             "|------|---------|-------|-------|------------------|------|"]
    for c in contacts:
        name = c.full_name or "—"
        company = c.company or "—"
        title = c.title or "—"
        score_val = c.relationship_score or 0
        last = c.last_interaction_at.strftime("%Y-%m-%d") if c.last_interaction_at else "Never"
        tags = ", ".join(c.tags) if c.tags else "—"
        lines.append(f"| {name} | {company} | {title} | {score_val}/10 | {last} | {tags} |")

    return "\n".join(lines)


async def _get_contact(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    contact_id: str | None = None,
    name: str | None = None,
) -> str:
    """Get full contact profile. Lookup by ID or fuzzy name search."""
    contact = None

    if contact_id:
        try:
            cid = uuid.UUID(contact_id)
        except ValueError:
            return f"Invalid contact ID: {contact_id}"
        result = await db.execute(
            select(Contact).where(Contact.id == cid, Contact.user_id == user_id)
        )
        contact = result.scalar_one_or_none()
    elif name:
        # Fuzzy name search — return top match
        result = await db.execute(
            select(Contact)
            .where(Contact.user_id == user_id, Contact.full_name.ilike(f"%{name}%"))
            .order_by(Contact.relationship_score.desc().nullslast())
            .limit(3)
        )
        matches = result.scalars().all()
        if not matches:
            return f"No contact found matching '{name}'."
        if len(matches) > 1:
            names = ", ".join(m.full_name or "?" for m in matches)
            contact = matches[0]
            # Show profile of best match but note ambiguity
        else:
            contact = matches[0]
    else:
        return "Provide either contact_id or name."

    if not contact:
        return "Contact not found."

    # Format profile
    lines = [f"# {contact.full_name or 'Unknown'}"]
    if contact.title or contact.company:
        parts = [p for p in [contact.title, contact.company] if p]
        lines.append(f"**{' at '.join(parts)}**")

    lines.append("")
    score = contact.relationship_score or 0
    label = "Strong" if score >= 7 else ("Warm" if score >= 4 else "Cold")
    lines.append(f"**Score:** {score}/10 ({label})")
    lines.append(f"**Interactions:** {contact.interaction_count or 0}")
    last = contact.last_interaction_at.strftime("%Y-%m-%d") if contact.last_interaction_at else "Never"
    lines.append(f"**Last interaction:** {last}")
    lines.append(f"**Priority:** {contact.priority_level or 'medium'}")

    if contact.tags:
        lines.append(f"**Tags:** {', '.join(contact.tags)}")

    if contact.emails:
        lines.append(f"**Emails:** {', '.join(contact.emails)}")
    if contact.phones:
        lines.append(f"**Phones:** {', '.join(contact.phones)}")

    # Bios
    bios = []
    if contact.twitter_bio:
        bios.append(f"- **Twitter:** {contact.twitter_bio}")
    if contact.linkedin_headline:
        bios.append(f"- **LinkedIn:** {contact.linkedin_headline}")
    if contact.linkedin_bio:
        bios.append(f"- **LinkedIn about:** {contact.linkedin_bio[:200]}")
    if contact.telegram_bio:
        bios.append(f"- **Telegram:** {contact.telegram_bio}")
    if bios:
        lines.append("\n**Bios:**")
        lines.extend(bios)

    return "\n".join(lines)
```

- [ ] **Step 3: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_server.py::TestContactTools -v`
Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add backend/mcp_server/tools/contacts.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add search_contacts and get_contact tools"
```

---

### Task 7: get_interactions tool

**Files:**
- Create: `backend/mcp_server/tools/interactions.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write tests**

Append to `backend/tests/test_mcp_server.py`:

```python
from datetime import UTC, datetime


class TestInteractionTools:
    @pytest.mark.asyncio
    async def test_get_interactions_returns_list(self):
        from mcp_server.tools.interactions import _get_interactions

        ix = MagicMock()
        ix.occurred_at = datetime(2026, 3, 20, tzinfo=UTC)
        ix.platform = "telegram"
        ix.direction = "inbound"
        ix.content_preview = "Hey, how's the project going?"
        ix.is_read_by_recipient = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ix]

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_interactions(uuid.uuid4(), db, contact_id=str(uuid.uuid4()), limit=10)
        assert "telegram" in result
        assert "project going" in result

    @pytest.mark.asyncio
    async def test_get_interactions_empty(self):
        from mcp_server.tools.interactions import _get_interactions

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_interactions(uuid.uuid4(), db, contact_id=str(uuid.uuid4()), limit=10)
        assert "No interactions" in result

    @pytest.mark.asyncio
    async def test_get_interactions_invalid_uuid(self):
        from mcp_server.tools.interactions import _get_interactions

        db = AsyncMock()
        result = await _get_interactions(uuid.uuid4(), db, contact_id="not-a-uuid", limit=10)
        assert "Invalid" in result

    @pytest.mark.asyncio
    async def test_get_interactions_read_receipts(self):
        from mcp_server.tools.interactions import _get_interactions

        ix_read = MagicMock()
        ix_read.occurred_at = datetime(2026, 3, 20, tzinfo=UTC)
        ix_read.platform = "telegram"
        ix_read.direction = "outbound"
        ix_read.content_preview = "Hello there"
        ix_read.is_read_by_recipient = True

        ix_unread = MagicMock()
        ix_unread.occurred_at = datetime(2026, 3, 21, tzinfo=UTC)
        ix_unread.platform = "telegram"
        ix_unread.direction = "outbound"
        ix_unread.content_preview = "Follow up"
        ix_unread.is_read_by_recipient = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ix_unread, ix_read]

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_interactions(uuid.uuid4(), db, contact_id=str(uuid.uuid4()), limit=10)
        assert "✓✓" in result  # read
        assert "✓" in result   # delivered (unread)
```

- [ ] **Step 2: Implement interactions.py**

Create `backend/mcp_server/tools/interactions.py`:

```python
"""MCP tool: get_interactions."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import Interaction


async def _get_interactions(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    contact_id: str,
    limit: int = 10,
    platform: str | None = None,
) -> str:
    """Get recent interactions for a contact."""
    try:
        cid = uuid.UUID(contact_id)
    except ValueError:
        return f"Invalid contact ID: {contact_id}"

    stmt = (
        select(Interaction)
        .where(Interaction.contact_id == cid, Interaction.user_id == user_id)
        .order_by(Interaction.occurred_at.desc())
        .limit(min(limit, 50))
    )
    if platform:
        stmt = stmt.where(Interaction.platform == platform)

    result = await db.execute(stmt)
    interactions = result.scalars().all()

    if not interactions:
        return "No interactions found for this contact."

    lines = []
    for ix in interactions:
        date = ix.occurred_at.strftime("%Y-%m-%d %H:%M") if ix.occurred_at else "?"
        direction = ix.direction or "?"
        preview = (ix.content_preview or "")[:120]
        read = ""
        if ix.is_read_by_recipient is True:
            read = " ✓✓"
        elif ix.is_read_by_recipient is False:
            read = " ✓"
        lines.append(f"- **{date}** [{ix.platform}] ({direction}{read}): {preview}")

    return "\n".join(lines)
```

- [ ] **Step 3: Run tests and commit**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_server.py::TestInteractionTools -v`

```bash
git add backend/mcp_server/tools/interactions.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add get_interactions tool"
```

---

### Task 8: get_suggestions tool

**Files:**
- Create: `backend/mcp_server/tools/suggestions.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write test, implement, commit**

Create `backend/mcp_server/tools/suggestions.py`:

```python
"""MCP tool: get_suggestions."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion


async def _get_suggestions(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    limit: int = 10,
) -> str:
    """Get pending follow-up suggestions."""
    result = await db.execute(
        select(FollowUpSuggestion)
        .where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "pending",
        )
        .order_by(FollowUpSuggestion.created_at.desc())
        .limit(min(limit, 50))
    )
    suggestions = result.scalars().all()

    if not suggestions:
        return "No pending follow-up suggestions."

    # Batch-load contact names
    contact_ids = [s.contact_id for s in suggestions]
    contacts_result = await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
    )
    contacts_by_id = {c.id: c for c in contacts_result.scalars().all()}

    lines = []
    for s in suggestions:
        contact = contacts_by_id.get(s.contact_id)
        name = contact.full_name if contact else "Unknown"
        date = s.created_at.strftime("%Y-%m-%d") if s.created_at else "?"
        trigger = s.trigger_type or "?"
        msg = (s.suggested_message or "")[:150]
        lines.append(f"### {name}\n- **Trigger:** {trigger}\n- **Date:** {date}\n- **Suggested message:** {msg}\n")

    return "\n".join(lines)
```

Test and commit:

```python
class TestSuggestionsTools:
    @pytest.mark.asyncio
    async def test_get_suggestions_returns_list(self):
        from mcp_server.tools.suggestions import _get_suggestions

        suggestion = MagicMock()
        suggestion.contact_id = uuid.uuid4()
        suggestion.trigger_type = "time_based"
        suggestion.suggested_message = "Hey, long time no talk!"
        suggestion.created_at = datetime(2026, 3, 25, tzinfo=UTC)

        contact = MagicMock()
        contact.id = suggestion.contact_id
        contact.full_name = "Jane Doe"

        sugg_result = MagicMock()
        sugg_result.scalars.return_value.all.return_value = [suggestion]

        contact_result = MagicMock()
        contact_result.scalars.return_value.all.return_value = [contact]

        db = AsyncMock()
        db.execute.side_effect = [sugg_result, contact_result]

        result = await _get_suggestions(uuid.uuid4(), db, limit=10)
        assert "Jane Doe" in result
        assert "time_based" in result

    @pytest.mark.asyncio
    async def test_get_suggestions_empty(self):
        from mcp_server.tools.suggestions import _get_suggestions

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_suggestions(uuid.uuid4(), db, limit=10)
        assert "No pending" in result
```

```bash
git add backend/mcp_server/tools/suggestions.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add get_suggestions tool"
```

---

### Task 9: get_notifications tool

**Files:**
- Create: `backend/mcp_server/tools/notifications.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Implement and test**

Create `backend/mcp_server/tools/notifications.py`:

```python
"""MCP tool: get_notifications."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def _get_notifications(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    unread_only: bool = True,
    limit: int = 20,
) -> str:
    """Get recent notifications."""
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(min(limit, 50))
    )
    if unread_only:
        stmt = stmt.where(Notification.read == False)  # noqa: E712

    result = await db.execute(stmt)
    notifications = result.scalars().all()

    if not notifications:
        return "No unread notifications." if unread_only else "No notifications."

    lines = []
    for n in notifications:
        date = n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "?"
        status = "🔵" if not n.read else ""
        lines.append(f"- {status} **{n.title}** ({date})")
        if n.body:
            lines.append(f"  {n.body[:200]}")

    return "\n".join(lines)
```

Tests to append:

```python
class TestNotificationTools:
    @pytest.mark.asyncio
    async def test_get_notifications_returns_unread(self):
        from mcp_server.tools.notifications import _get_notifications

        notif = MagicMock()
        notif.title = "Twitter sync completed"
        notif.body = "3 DMs, 1 new contact"
        notif.notification_type = "sync"
        notif.read = False
        notif.created_at = datetime(2026, 3, 25, 10, 0, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [notif]

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_notifications(uuid.uuid4(), db, unread_only=True, limit=20)
        assert "Twitter sync completed" in result
        assert "3 DMs" in result

    @pytest.mark.asyncio
    async def test_get_notifications_empty(self):
        from mcp_server.tools.notifications import _get_notifications

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_notifications(uuid.uuid4(), db, unread_only=True, limit=20)
        assert "No unread" in result

    @pytest.mark.asyncio
    async def test_get_notifications_all_includes_read(self):
        from mcp_server.tools.notifications import _get_notifications

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_notifications(uuid.uuid4(), db, unread_only=False, limit=20)
        assert "No notifications" in result  # different message for all vs unread
```

```bash
git add backend/mcp_server/tools/notifications.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add get_notifications tool"
```

---

### Task 10: get_dashboard_stats tool

**Files:**
- Create: `backend/mcp_server/tools/dashboard.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Implement and test**

Create `backend/mcp_server/tools/dashboard.py`:

```python
"""MCP tool: get_dashboard_stats."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction


async def _get_dashboard_stats(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> str:
    """Network health overview."""
    # Total contacts (exclude archived)
    total_result = await db.execute(
        select(func.count()).where(
            Contact.user_id == user_id,
            Contact.priority_level != "archived",
        )
    )
    total = total_result.scalar_one()

    # Score distribution
    score_result = await db.execute(
        select(
            func.count().filter(Contact.relationship_score >= 7).label("strong"),
            func.count().filter(
                Contact.relationship_score >= 4,
                Contact.relationship_score < 7,
            ).label("warm"),
            func.count().filter(
                (Contact.relationship_score < 4) | (Contact.relationship_score.is_(None))
            ).label("cold"),
        ).where(Contact.user_id == user_id, Contact.priority_level != "archived")
    )
    row = score_result.one()

    # Pending suggestions
    sugg_result = await db.execute(
        select(func.count()).where(
            FollowUpSuggestion.user_id == user_id,
            FollowUpSuggestion.status == "pending",
        )
    )
    pending = sugg_result.scalar_one()

    # 7-day interaction count by platform
    week_ago = datetime.now(UTC) - timedelta(days=7)
    ix_result = await db.execute(
        select(Interaction.platform, func.count())
        .where(
            Interaction.user_id == user_id,
            Interaction.occurred_at >= week_ago,
        )
        .group_by(Interaction.platform)
    )
    ix_by_platform = {p: c for p, c in ix_result.all()}
    total_ix = sum(ix_by_platform.values())

    lines = [
        "# Network Health",
        "",
        f"**Total contacts:** {total}",
        f"**Strong (7-10):** {row.strong} | **Warm (4-6):** {row.warm} | **Cold (0-3):** {row.cold}",
        f"**Pending suggestions:** {pending}",
        "",
        f"## Last 7 Days ({total_ix} interactions)",
    ]

    if ix_by_platform:
        for platform, count in sorted(ix_by_platform.items(), key=lambda x: -x[1]):
            lines.append(f"- **{platform}:** {count}")
    else:
        lines.append("No interactions in the last 7 days.")

    return "\n".join(lines)
```

Tests to append:

```python
class TestDashboardTools:
    @pytest.mark.asyncio
    async def test_get_dashboard_stats_returns_formatted(self):
        from mcp_server.tools.dashboard import _get_dashboard_stats

        # Mock 4 DB calls: total count, score distribution, pending suggestions, 7d interactions
        total_result = MagicMock()
        total_result.scalar_one.return_value = 150

        score_row = MagicMock()
        score_row.strong = 30
        score_row.warm = 60
        score_row.cold = 60
        score_result = MagicMock()
        score_result.one.return_value = score_row

        sugg_result = MagicMock()
        sugg_result.scalar_one.return_value = 5

        ix_result = MagicMock()
        ix_result.all.return_value = [("telegram", 20), ("email", 10), ("twitter", 5)]

        db = AsyncMock()
        db.execute.side_effect = [total_result, score_result, sugg_result, ix_result]

        result = await _get_dashboard_stats(uuid.uuid4(), db)
        assert "150" in result
        assert "Strong" in result
        assert "Warm" in result
        assert "Cold" in result
        assert "telegram" in result
        assert "5" in result  # pending suggestions

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_empty_interactions(self):
        from mcp_server.tools.dashboard import _get_dashboard_stats

        total_result = MagicMock()
        total_result.scalar_one.return_value = 0

        score_row = MagicMock()
        score_row.strong = 0
        score_row.warm = 0
        score_row.cold = 0
        score_result = MagicMock()
        score_result.one.return_value = score_row

        sugg_result = MagicMock()
        sugg_result.scalar_one.return_value = 0

        ix_result = MagicMock()
        ix_result.all.return_value = []

        db = AsyncMock()
        db.execute.side_effect = [total_result, score_result, sugg_result, ix_result]

        result = await _get_dashboard_stats(uuid.uuid4(), db)
        assert "No interactions" in result
```

```bash
git add backend/mcp_server/tools/dashboard.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add get_dashboard_stats tool"
```

---

## Chunk 4: Tool Registration + README + Final Verification

### Task 11: Wire tools to MCP server with @mcp_app.tool() decorators

**Files:**
- Modify: `backend/mcp_server/tools/contacts.py`
- Modify: `backend/mcp_server/tools/interactions.py`
- Modify: `backend/mcp_server/tools/suggestions.py`
- Modify: `backend/mcp_server/tools/notifications.py`
- Modify: `backend/mcp_server/tools/dashboard.py`
- Modify: `backend/mcp_server/server.py`

Each tool module needs to register its functions with the MCP server. Add tool decorators that wrap the inner `_*` functions, handling session creation and user resolution.

- [ ] **Step 1: Add tool registration to each module**

In each tool file, add the MCP tool registration. Example for `contacts.py`:

```python
from mcp_server.server import mcp_app
from mcp_server.db import get_session

# Module-level user_id (set during server startup)
_current_user_id = None

def set_user_id(uid):
    global _current_user_id
    _current_user_id = uid


@mcp_app.tool()
async def search_contacts(
    query: str = "",
    tag: str = "",
    score: str = "",
    priority: str = "",
    limit: int = 20,
) -> str:
    """Search your contacts by name, company, tag, score tier (strong/warm/cold), or priority level."""
    async with get_session() as db:
        return await _search_contacts(
            _current_user_id, db,
            query=query or None,
            tag=tag or None,
            score=score or None,
            priority=priority or None,
            limit=limit,
        )


@mcp_app.tool()
async def get_contact(
    contact_id: str = "",
    name: str = "",
) -> str:
    """Get the full profile for a contact. Provide either a contact_id (UUID) or a name for fuzzy search."""
    async with get_session() as db:
        return await _get_contact(
            _current_user_id, db,
            contact_id=contact_id or None,
            name=name or None,
        )
```

Apply the same pattern to all 5 tool modules. Each gets `set_user_id()` + `@mcp_app.tool()` wrappers.

- [ ] **Step 2: Add user resolution to server.py startup**

In `run_stdio()`, before starting the server, resolve the user and call `set_user_id()` on all tool modules:

```python
async def run_stdio(user_email: str | None = None):
    from mcp_server.db import get_session
    from sqlalchemy import select, func
    from app.models.user import User

    _register_tools()

    # Resolve user
    async with get_session() as db:
        if user_email:
            result = await db.execute(select(User).where(User.email == user_email))
            user = result.scalar_one_or_none()
            if not user:
                print(f"Error: No user found with email '{user_email}'")
                return
        else:
            result = await db.execute(select(User))
            users = result.scalars().all()
            if not users:
                print("Error: No users found in database")
                return
            if len(users) > 1:
                print("Error: Multiple users found. Use --user-email to specify which one.")
                return
            user = users[0]

    # Set user_id on all tool modules
    from mcp_server.tools import contacts, interactions, suggestions, notifications, dashboard
    for mod in [contacts, interactions, suggestions, notifications, dashboard]:
        mod.set_user_id(user.id)

    logger.info("MCP server ready for user %s (%s)", user.email, user.id)

    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await mcp_app.run(read_stream, write_stream, mcp_app.create_initialization_options())
```

- [ ] **Step 3: Run all tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_server.py -v`
Expected: All passed

- [ ] **Step 4: Commit**

```bash
git add backend/mcp_server/
git commit -m "feat(mcp): wire tool decorators and user resolution"
```

---

### Task 12: README + final verification

**Files:**
- Create: `backend/mcp_server/README.md`

- [ ] **Step 1: Create README**

Create `backend/mcp_server/README.md` with setup instructions for Claude Desktop (stdio local, stdio via SSH, SSE direct), Cursor, and VS Code. Include the JSON config blocks from the spec.

- [ ] **Step 2: Run full test suite**

```bash
cd backend && .venv/bin/python -m pytest --tb=short -q
```
Expected: All tests pass, no regressions

- [ ] **Step 3: Verify CI guards**

```bash
cd backend && PYTHONPATH=. .venv/bin/python scripts/check_response_models.py
```

- [ ] **Step 4: Final commit**

```bash
git add backend/mcp_server/README.md
git commit -m "docs(mcp): add README with client setup instructions"
```
