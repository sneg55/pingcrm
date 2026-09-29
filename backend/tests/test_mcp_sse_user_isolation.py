from __future__ import annotations

import asyncio
import socket
import uuid

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.sse import sse_client
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.models.contact import Contact
from app.models.user import User
from mcp_server.auth import generate_api_key, hash_api_key


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _make_user_with_contact(db: AsyncSession, contact_name: str) -> str:
    key = generate_api_key()
    user = User(
        id=uuid.uuid4(),
        email=f"mcp_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("pw"),
        full_name="MCP User",
        mcp_api_key_hash=hash_api_key(key),
    )
    db.add(user)
    await db.flush()
    db.add(Contact(user_id=user.id, full_name=contact_name, emails=[], phones=[]))
    await db.commit()
    return key


@pytest.fixture
async def mcp_url():
    import mcp_server.db
    from app.main import _mcp_asgi

    await mcp_server.db.engine.dispose()
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(_mcp_asgi, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    yield f"http://127.0.0.1:{port}/sse"
    server.should_exit = True
    await task
    await mcp_server.db.engine.dispose()


async def _search(session: ClientSession) -> str:
    result = await session.call_tool("search_contacts", {})
    return "\n".join(c.text for c in result.content)


@pytest.mark.asyncio
async def test_concurrent_sse_sessions_only_see_their_own_user(db: AsyncSession, mcp_url: str):
    key_a = await _make_user_with_contact(db, "Alice Only-A")
    key_b = await _make_user_with_contact(db, "Bob Only-B")

    async with sse_client(mcp_url, headers={"Authorization": f"Bearer {key_a}"}) as streams_a:
        async with ClientSession(*streams_a) as session_a:
            await session_a.initialize()
            async with sse_client(mcp_url, headers={"Authorization": f"Bearer {key_b}"}) as streams_b:
                async with ClientSession(*streams_b) as session_b:
                    await session_b.initialize()

                    result_a = await _search(session_a)
                    result_b = await _search(session_b)

    assert "Alice Only-A" in result_a
    assert "Bob Only-B" not in result_a
    assert "Bob Only-B" in result_b
    assert "Alice Only-A" not in result_b


def test_tools_fail_closed_without_authenticated_user():
    from mcp_server.context import require_user_id

    with pytest.raises(PermissionError):
        require_user_id()


@pytest.mark.asyncio
async def test_standalone_sse_server_rejects_requests_without_api_key():
    import httpx

    from mcp_server.server import build_standalone_sse_app

    transport = httpx.ASGITransport(app=build_standalone_sse_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sse")

    assert response.status_code == 401


def test_standalone_sse_binds_loopback_by_default():
    from mcp_server.server import parse_args

    assert parse_args(["--sse"]).host == "127.0.0.1"
