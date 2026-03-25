# PingCRM MCP Server

Expose your PingCRM data to AI clients (Claude Desktop, Cursor, VS Code) via the Model Context Protocol.

## Available Tools

| Tool | Description |
|------|-------------|
| `search_contacts` | Search by name, company, tag, score, priority |
| `get_contact` | Full profile by ID or fuzzy name search |
| `get_interactions` | Recent interactions with a contact |
| `get_suggestions` | Pending follow-up suggestions |
| `get_notifications` | Recent notifications (unread or all) |
| `get_dashboard_stats` | Network health overview |

## Setup

### Claude Desktop (local / stdio)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pingcrm": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/pingcrm/backend",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/pingcrm",
        "SECRET_KEY": "your-secret-key"
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

### Remote / SSE (direct HTTP)

1. Generate an API key in PingCRM Settings > MCP Access
2. Configure your client:

```json
{
  "mcpServers": {
    "pingcrm": {
      "url": "https://pingcrm.sawinyh.com/mcp/sse",
      "headers": {
        "Authorization": "Bearer pingcrm_your_key_here"
      }
    }
  }
}
```

## API Key Management

Generate and manage API keys from **Settings > MCP Access** in the PingCRM web app.

- **Generate** creates a new key (shown once — copy it!)
- **Revoke** invalidates the key immediately
