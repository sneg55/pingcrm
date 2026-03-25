# MCP Server Integration

**Date:** 2026-03-25
**Issue:** #7
**Status:** Approved

## Problem

Users want to interact with their PingCRM data from AI clients (Claude Desktop, Cursor, VS Code) without opening the web app. Currently there's no programmatic interface for AI agents to query contacts, suggestions, or interaction history.

## Solution

A Model Context Protocol (MCP) server that exposes PingCRM data as read-only tools. Supports two transports: stdio for local development and SSE with API key auth for remote/production access. Direct database access (no HTTP middleman). Per-user API keys managed via the Settings UI.

## Architecture

```
backend/
├── mcp_server/
│   ├── __init__.py
│   ├── server.py           # Entry point, transport selection, tool registration
│   ├── db.py               # Async session factory (module-level engine, per-tool-call sessions)
│   ├── auth.py             # API key hashing + verification
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── contacts.py     # search_contacts, get_contact
│   │   ├── interactions.py # get_interactions
│   │   ├── suggestions.py  # get_suggestions
│   │   ├── notifications.py # get_notifications
│   │   └── dashboard.py    # get_dashboard_stats
│   └── README.md           # Setup instructions for Claude Desktop / Cursor
```

- **SDK:** `mcp>=1.0.0,<2.0.0` Python package (official MCP SDK, pinned to avoid breaking changes)
- **DB access:** Lives inside `backend/` so it naturally imports `app.models` and `app.core.config` — same as Celery workers. Module-level engine created at startup; each tool call gets a fresh `AsyncSession` (no per-request dependency injection).
- **Docker:** Shares the same Docker image as the backend (same build context `./backend`). Different command in `docker-compose.yml`.
- **User resolution:** stdio mode takes `--user-email` CLI arg or uses the single user in DB; SSE mode resolves user from API key

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Transport | stdio + SSE | stdio for local (Claude Desktop, Cursor); SSE for remote (prod server) |
| Data access | Direct DB (SQLAlchemy) | Same pattern as Celery tasks; no HTTP overhead; no running backend needed |
| Auth (SSE) | Per-user API key (hashed) | Key identifies user; simple shared secret; appropriate for personal CRM |
| Auth (stdio) | None | Subprocess communication has no network exposure |
| Output format | Markdown text | More useful for LLM consumption than raw JSON |
| Initial scope | Read-only (6 tools) | Safe to ship; write tools added later |
| File location | `backend/mcp_server/` | Inside backend package; shares Docker image and Python path with Celery workers |
| Key hashing | HMAC-SHA256 | Direct DB lookup by hash; sub-ms verification; secure for random 32-byte keys |

## Transport & Auth

### stdio (local development)

Default mode. Server runs as a subprocess spawned by the AI client.

```bash
python mcp/server.py                          # uses single user in DB
python mcp/server.py --user-email user@example.com  # explicit user
```

No auth — communication is over stdin/stdout pipes with no network exposure.

### SSE (remote / production)

Enabled via flag. Runs an HTTP server for Server-Sent Events transport.

```bash
python mcp/server.py --sse --port 8808
```

Protected by per-user API key:
1. Client sends `Authorization: Bearer <key>` header
2. Server hashes the key, looks up matching user in DB
3. Rejects with 401 if no match
4. All subsequent tool calls are scoped to that user

### Caddy config addition

Insert before the frontend catch-all `handle` block:

```
handle /mcp/* {
    reverse_proxy mcp:8808
}
```

### Docker

The MCP SSE server shares the backend Docker image (same build context `./backend`), different command:

```yaml
mcp:
  build: ./backend
  command: python -m mcp_server.server --sse --port 8808
  environment:
    - DATABASE_URL=${DATABASE_URL}
    - SECRET_KEY=${SECRET_KEY}
    - ENCRYPTION_KEY=${ENCRYPTION_KEY}
  depends_on:
    - postgres
```

`ENCRYPTION_KEY` is passed to avoid crashes if any model relationship triggers decryption of encrypted columns.

## API Key Management

### Data model

New column on `User` (requires Alembic migration):
- `mcp_api_key_hash: String(128), nullable` — HMAC-SHA256 hash of the API key (hex-encoded)

Hashing: `hmac.new(SECRET_KEY.encode(), api_key.encode(), hashlib.sha256).hexdigest()`. This allows direct DB lookup via `WHERE mcp_api_key_hash = computed_hash` — no iteration over users, sub-ms verification.

### Settings UI

A new "MCP Access" card on the Settings page:
- **Generate API Key** button → generates a random 32-byte key, stores HMAC-SHA256 hash on User, displays the key once with a copy button
- **Revoke** button → clears the hash, invalidates the key immediately
- **Status indicator** — shows whether a key is active

### API endpoints

- `POST /api/v1/settings/mcp-key` → generates key, returns `Envelope[McpKeyData]` with `{ key: "pingcrm_..." }` (plaintext, shown once)
- `DELETE /api/v1/settings/mcp-key` → revokes key, returns `Envelope[McpKeyRevokedData]` with `{ revoked: true }`
- `GET /api/v1/settings/mcp-key` → returns `Envelope[McpKeyStatusData]` with `{ has_key: true/false }` (never exposes the key)

Response schemas go in `backend/app/schemas/responses.py` following existing patterns. All three endpoints must declare `response_model` (CI guard).

### Key format

`pingcrm_` prefix + 32 random bytes (base64url) = ~48 chars total. The prefix makes it easy to identify in configs.

## Tools (Read-Only)

### search_contacts

Search and filter contacts.

- **Inputs:** `query` (string, optional), `tag` (string, optional), `score` (string, optional — "strong", "warm", or "cold"), `priority` (string, optional), `limit` (int, default 20, max 50)
- **Returns:** Markdown table with: name, company, title, score, last_interaction_at, tags
- **Query logic:** Reuses existing `contact_search.py` with `build_contact_filter_query()`. The `score` param maps to tier names matching the existing API (strong=7-10, warm=4-6, cold=0-3).

### get_contact

Full profile for one contact.

- **Inputs:** `contact_id` (UUID string) OR `name` (string for fuzzy lookup)
- **Returns:** Formatted profile with: name, title, company, emails, phone, all bios (Twitter, LinkedIn, Telegram), score + label, interaction_count, last_interaction_at, tags, priority
- **Fuzzy lookup:** If `name` provided, searches by name, returns top match. If multiple close matches, lists top 3 with a note to be more specific.

### get_interactions

Recent interactions with a contact.

- **Inputs:** `contact_id` (UUID string), `limit` (int, default 10), `platform` (string, optional filter)
- **Returns:** Markdown list with: date, platform, direction, content_preview, is_read

### get_suggestions

Pending follow-up suggestions.

- **Inputs:** `limit` (int, default 10)
- **Returns:** Markdown list with: contact name, trigger_type, suggested_message, created_at

### get_notifications

Recent notifications.

- **Inputs:** `unread_only` (bool, default true), `limit` (int, default 20)
- **Returns:** Markdown list with: title, body, type, created_at

### get_dashboard_stats

Network health overview.

- **Inputs:** none
- **Returns:** Formatted stats: total contacts, score distribution (strong/warm/cold), pending suggestions count, 7-day interaction count by platform

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No user found (stdio) | Server exits with message: "No user found in database" |
| DB connection failure | Tool returns: "Database connection failed — is PostgreSQL running?" |
| Invalid contact_id | Tool returns: "Contact not found" |
| Empty results | Tool returns: "No contacts match your search" (not an error) |
| Large result sets | Capped by `limit` parameter (max 50) |
| Missing API key (SSE) | Server refuses to start: "MCP_API_KEY required for SSE mode" |
| Invalid API key (SSE) | Returns 401 |

All error handlers must follow the project exception handling policy (`.claude/rules/exception-handling.md`): `logger.exception()` with structured `extra={"provider": "mcp", "operation": "..."}` before returning the user-friendly message.

## Client Configuration Examples

### Claude Desktop (local / stdio)

```json
{
  "mcpServers": {
    "pingcrm": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/pingcrm/backend",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/pingcrm"
      }
    }
  }
}
```

### Claude Desktop (remote / stdio via SSH)

```json
{
  "mcpServers": {
    "pingcrm": {
      "command": "ssh",
      "args": [
        "-i", "~/.ssh/pingcrm_key",
        "root@pingcrm.sawinyh.com",
        "cd /opt/pingcrm && docker compose exec -T backend python -m mcp_server.server"
      ]
    }
  }
}
```

### Claude Desktop (remote / SSE direct)

```json
{
  "mcpServers": {
    "pingcrm": {
      "url": "https://pingcrm.sawinyh.com/mcp/sse",
      "headers": {
        "Authorization": "Bearer pingcrm_abc123..."
      }
    }
  }
}
```

## Future Write Tools (Out of Scope)

These are not part of the initial release but the architecture supports adding them:

- `create_contact` — add a new contact
- `update_contact` — edit fields, tags, priority
- `send_message` — send via Telegram/email/Twitter
- `dismiss_suggestion` — dismiss or snooze a suggestion
- `trigger_sync` — start a platform sync
- `merge_contacts` — merge duplicate contacts

## Dependencies

- `mcp>=1.0.0,<2.0.0` — official MCP Python SDK (add to `backend/requirements.txt`)
- `hmac` + `hashlib` — for API key hashing (stdlib, no new dependency)
- All backend models/config imported naturally (lives inside `backend/`)

## Testing

- Unit tests for each tool function (mocked DB session)
- Unit test for API key generation and validation
- Unit test for SSE auth middleware (valid key, invalid key, missing key)
- Integration test: start stdio server, list tools via MCP SDK test client
- Test: search_contacts with various filter combinations
- Test: get_contact by ID and by name (fuzzy)
- Test: empty results return friendly messages, not errors

## Out of Scope

- Write tools (create, update, delete, send)
- Streamable HTTP transport (newer MCP spec, not widely supported yet)
- Multi-key per user (one key is enough for personal CRM)
- Key rotation without revocation (revoke + regenerate is fine)
- Rate limiting on SSE (single-player, not needed)
