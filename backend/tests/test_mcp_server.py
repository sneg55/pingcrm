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


class TestContactTools:
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

        result = await _search_contacts(uuid.uuid4(), db, query="Jane", limit=20)
        assert "Jane Doe" in result
        assert "Acme Corp" in result

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
        assert "\u2713\u2713" in result
        assert "\u2713" in result


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
    async def test_get_notifications_empty_unread(self):
        from mcp_server.tools.notifications import _get_notifications

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_notifications(uuid.uuid4(), db, unread_only=True, limit=20)
        assert "No unread" in result

    @pytest.mark.asyncio
    async def test_get_notifications_empty_all(self):
        from mcp_server.tools.notifications import _get_notifications

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _get_notifications(uuid.uuid4(), db, unread_only=False, limit=20)
        assert "No notifications" in result


class TestDashboardTools:
    @pytest.mark.asyncio
    async def test_get_dashboard_stats_returns_formatted(self):
        from mcp_server.tools.dashboard import _get_dashboard_stats

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
        ix_result.all.return_value = [("telegram", 20), ("email", 10)]

        db = AsyncMock()
        db.execute.side_effect = [total_result, score_result, sugg_result, ix_result]

        result = await _get_dashboard_stats(uuid.uuid4(), db)
        assert "150" in result
        assert "Strong" in result
        assert "telegram" in result

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


class TestMcpKeyApi:
    """Integration tests for POST/GET/DELETE /api/v1/settings/mcp-key."""

    @pytest.mark.asyncio
    async def test_get_key_status_no_key(self, client, auth_headers):
        """GET /settings/mcp-key returns has_key=false when no key exists."""
        resp = await client.get("/api/v1/settings/mcp-key", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["has_key"] is False

    @pytest.mark.asyncio
    async def test_generate_key_returns_pingcrm_prefix(self, client, auth_headers):
        """POST /settings/mcp-key returns a key starting with pingcrm_."""
        resp = await client.post("/api/v1/settings/mcp-key", headers=auth_headers)
        assert resp.status_code == 200
        key = resp.json()["data"]["key"]
        assert key.startswith("pingcrm_")
        assert len(key) > 40

    @pytest.mark.asyncio
    async def test_get_key_status_after_generate(self, client, auth_headers):
        """GET returns has_key=true after generating a key."""
        await client.post("/api/v1/settings/mcp-key", headers=auth_headers)
        resp = await client.get("/api/v1/settings/mcp-key", headers=auth_headers)
        assert resp.json()["data"]["has_key"] is True

    @pytest.mark.asyncio
    async def test_revoke_key(self, client, auth_headers):
        """DELETE /settings/mcp-key revokes the key."""
        await client.post("/api/v1/settings/mcp-key", headers=auth_headers)
        resp = await client.delete("/api/v1/settings/mcp-key", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["revoked"] is True
        # Verify key is gone
        status = await client.get("/api/v1/settings/mcp-key", headers=auth_headers)
        assert status.json()["data"]["has_key"] is False

    @pytest.mark.asyncio
    async def test_generate_key_overwrites_existing(self, client, auth_headers):
        """Generating a new key replaces the old one."""
        resp1 = await client.post("/api/v1/settings/mcp-key", headers=auth_headers)
        key1 = resp1.json()["data"]["key"]
        resp2 = await client.post("/api/v1/settings/mcp-key", headers=auth_headers)
        key2 = resp2.json()["data"]["key"]
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_key_endpoints_require_auth(self, client):
        """All MCP key endpoints return 401 without auth."""
        for method, path in [
            (client.get, "/api/v1/settings/mcp-key"),
            (client.post, "/api/v1/settings/mcp-key"),
            (client.delete, "/api/v1/settings/mcp-key"),
        ]:
            resp = await method(path)
            assert resp.status_code == 401


class TestMcpKeyVerification:
    """Test that generated keys verify correctly via auth module."""

    @pytest.mark.asyncio
    async def test_generated_key_verifies(self, client, auth_headers, db, test_user):
        """A key generated via API can be verified via auth.verify_api_key."""
        from mcp_server.auth import verify_api_key

        resp = await client.post("/api/v1/settings/mcp-key", headers=auth_headers)
        key = resp.json()["data"]["key"]
        user = await verify_api_key(key, db)
        assert user is not None
        assert user.id == test_user.id

    @pytest.mark.asyncio
    async def test_revoked_key_does_not_verify(self, client, auth_headers, db):
        """After revocation, the key no longer verifies."""
        from mcp_server.auth import verify_api_key

        resp = await client.post("/api/v1/settings/mcp-key", headers=auth_headers)
        key = resp.json()["data"]["key"]
        await client.delete("/api/v1/settings/mcp-key", headers=auth_headers)
        user = await verify_api_key(key, db)
        assert user is None


class TestScoreTierMapping:
    """Test score tier name mapping in contacts tool."""

    def test_score_map_values(self):
        from mcp_server.tools.contacts import _SCORE_MAP

        assert _SCORE_MAP["strong"] == "strong"
        assert _SCORE_MAP["warm"] == "active"
        assert _SCORE_MAP["cold"] == "dormant"

    def test_unknown_score_returns_none(self):
        from mcp_server.tools.contacts import _SCORE_MAP

        assert _SCORE_MAP.get("invalid") is None
