"""Auth-protected ASGI wrapper for the FastMCP SSE app."""
from __future__ import annotations


class MCPAuthMiddleware:
    """Raw ASGI middleware that validates Bearer API keys before forwarding to the MCP SSE app."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode()

        if not auth.startswith("Bearer "):
            await _send_401(scope, send)
            return

        api_key = auth[7:]

        from mcp_server.db import get_session
        from mcp_server.auth import verify_api_key

        async with get_session() as db:
            user = await verify_api_key(api_key, db)

        if not user:
            await _send_401(scope, send)
            return

        from mcp_server.tools import contacts, interactions, suggestions, notifications, dashboard
        for mod in [contacts, interactions, suggestions, notifications, dashboard]:
            mod.set_user_id(user.id)

        await self.app(scope, receive, send)


async def _send_401(scope, send) -> None:
    if scope["type"] == "http":
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"text/plain")],
        })
        await send({"type": "http.response.body", "body": b"Unauthorized"})
