"""Tests for MCP Server (issue #7)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMcpAuth:
    def test_generate_api_key_has_prefix(self):
        from mcp_server.auth import generate_api_key
        key = generate_api_key()
        assert key.startswith("pingcrm_")
        assert len(key) > 40

    def test_hash_api_key_is_deterministic(self):
        from mcp_server.auth import hash_api_key
        key = "pingcrm_testkey123"
        assert hash_api_key(key) == hash_api_key(key)
        assert len(hash_api_key(key)) == 64

    def test_hash_api_key_differs_for_different_keys(self):
        from mcp_server.auth import hash_api_key
        assert hash_api_key("pingcrm_key1") != hash_api_key("pingcrm_key2")

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


class TestMcpKeyEndpoints:
    def test_response_schemas_exist(self):
        from app.schemas.responses import McpKeyData, McpKeyRevokedData, McpKeyStatusData
        assert McpKeyData(key="pingcrm_test").key == "pingcrm_test"
        assert McpKeyRevokedData(revoked=True).revoked is True
        assert McpKeyStatusData(has_key=False).has_key is False


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
