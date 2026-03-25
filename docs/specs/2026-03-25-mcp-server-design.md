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
mcp/
├── server.py           # Entry point, transport selection, tool registration
├── tools/
│   ├── contacts.py     # search_contacts, get_contact
│   ├── interactions.py # get_interactions
│   ├── suggestions.py  # get_suggestions
│   ├── notifications.py # get_notifications
│   └── dashboard.py    # get_dashboard_stats
├── db.py               # Async session factory (reuses backend config)
└── README.md           # Setup instructions for Claude Desktop / Cursor
```

- **SDK:** `mcp` Python package (official MCP SDK)
- **DB access:** Imports `backend/app/models` and `backend/app/core/config` (adds `backend/` to `sys.path`)
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
| File location | `mcp/` top-level | Clean separation from backend; imports backend models |

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

```
handle /mcp/* {
    reverse_proxy backend:8808
}
```

### Docker

The MCP SSE server runs as a separate service in `docker-compose.yml`:

```yaml
mcp:
  build: .
  command: python mcp/server.py --sse --port 8808
  environment:
    - DATABASE_URL=${DATABASE_URL}
  depends_on:
    - postgres
```

## API Key Management

### Data model

New column on `User`:
- `mcp_api_key_hash: String, nullable` — bcrypt hash of the API key

### Settings UI

A new "MCP Access" card on the Settings page:
- **Generate API Key** button → generates a random 32-byte key, stores bcrypt hash on User, displays the key once with a copy button
- **Revoke** button → clears the hash, invalidates the key immediately
- **Status indicator** — shows whether a key is active

### API endpoints

- `POST /api/v1/settings/mcp-key` → generates key, returns `{ key: "pingcrm_..." }` (plaintext, shown once)
- `DELETE /api/v1/settings/mcp-key` → revokes key, returns `{ revoked: true }`
- `GET /api/v1/settings/mcp-key` → returns `{ has_key: true/false }` (never exposes the key)

### Key format

`pingcrm_` prefix + 32 random bytes (base64url) = ~48 chars total. The prefix makes it easy to identify in configs.

## Tools (Read-Only)

### search_contacts

Search and filter contacts.

- **Inputs:** `query` (string, optional), `tag` (string, optional), `min_score` / `max_score` (int, optional), `priority` (string, optional), `limit` (int, default 20, max 50)
- **Returns:** Markdown table with: name, company, title, score, last_interaction_at, tags
- **Query logic:** Reuses existing `contact_search.py` relevance ranking (name prefix > name contains > company > handle > other)

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

## Client Configuration Examples

### Claude Desktop (local / stdio)

```json
{
  "mcpServers": {
    "pingcrm": {
      "command": "python",
      "args": ["mcp/server.py"],
      "cwd": "/path/to/pingcrm",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/pingcrm"
      }
    }
  }
}
```

### Claude Desktop (remote / SSE via SSH)

```json
{
  "mcpServers": {
    "pingcrm": {
      "command": "ssh",
      "args": [
        "-i", "~/.ssh/pingcrm_key",
        "root@pingcrm.sawinyh.com",
        "cd /opt/pingcrm && docker compose exec -T mcp python mcp/server.py"
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

- `mcp` — official MCP Python SDK (add to `requirements.txt` or a separate `mcp/requirements.txt`)
- `bcrypt` — for API key hashing (already in backend deps via `passlib`)
- All backend models/config imported at runtime

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
