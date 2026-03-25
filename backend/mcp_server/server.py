"""PingCRM MCP Server — expose CRM data to AI clients.

Usage:
    python -m mcp_server.server                          # stdio (local)
    python -m mcp_server.server --user-email user@x.com  # stdio with explicit user
    python -m mcp_server.server --sse --port 8808        # SSE (remote)
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
    # Tools will be registered when their modules are imported (Task 11)
    pass


async def run_stdio(user_email: str | None = None):
    """Run in stdio mode (local subprocess)."""
    from mcp.server.stdio import stdio_server

    _register_tools()
    logger.info("Starting PingCRM MCP server (stdio mode)")

    async with stdio_server() as (read_stream, write_stream):
        await mcp_app.run(read_stream, write_stream, mcp_app.create_initialization_options())


async def run_sse(port: int):
    """Run in SSE mode (remote HTTP)."""
    _register_tools()
    logger.info("Starting PingCRM MCP server (SSE mode on port %d)", port)
    # SSE transport implementation will be completed in Task 11
    raise NotImplementedError("SSE transport not yet wired")


def main():
    import asyncio

    args = parse_args()
    if args.sse:
        asyncio.run(run_sse(args.port))
    else:
        asyncio.run(run_stdio(args.user_email))


if __name__ == "__main__":
    main()
