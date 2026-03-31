"""PingCRM MCP Server — expose CRM data to AI clients.

Usage:
    python -m mcp_server.server                          # stdio (local)
    python -m mcp_server.server --user-email user@x.com  # stdio with explicit user
    python -m mcp_server.server --sse --port 8808        # SSE (remote)
"""
from __future__ import annotations

import argparse
import logging

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp_app = FastMCP("pingcrm")


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
    from mcp_server.db import get_session
    from sqlalchemy import select
    from app.models.user import User

    _register_tools()

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
                print("Error: Multiple users found. Use --user-email to specify.")
                return
            user = users[0]

    from mcp_server.tools import contacts, interactions, suggestions, notifications, dashboard
    for mod in [contacts, interactions, suggestions, notifications, dashboard]:
        mod.set_user_id(user.id)

    logger.info("MCP server ready for user %s (%s)", user.email, user.id)

    await mcp_app.run_stdio_async()


async def run_sse(port: int):
    """Run in SSE mode (remote HTTP — standalone, no auth)."""
    import uvicorn
    _register_tools()
    logger.info("Starting PingCRM MCP server (SSE mode on port %d)", port)
    config = uvicorn.Config(mcp_app.sse_app(), host="0.0.0.0", port=port)
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
