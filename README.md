# PingCRM

**Open-source personal networking CRM — AI-powered, self-hostable.**

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/sneg55/pingcrm)](https://github.com/sneg55/pingcrm/stargazers)
[![Build](https://github.com/sneg55/pingcrm/actions/workflows/deploy.yml/badge.svg)](https://github.com/sneg55/pingcrm/actions/workflows/deploy.yml)

Auto-syncs Gmail, Telegram, Twitter/X, LinkedIn, and WhatsApp. Detects life events. Drafts contextual follow-ups with AI. Tells you who to reach out to and why.

**[Docs](https://docs.pingcrm.xyz/)** · **[Setup Guide](https://docs.pingcrm.xyz/setup)** · **[Hosted Waitlist](https://pingcrm.xyz)**

---

## Why PingCRM?

| | PingCRM | Monica | Dex |
|---|---|---|---|
| Price | Free (self-hosted) | Free / $9/mo | Free tier / $12/mo |
| AI message drafting | ✅ | ❌ | ❌ |
| Gmail sync | ✅ threads | ❌ | ✅ contacts only |
| Telegram sync | ✅ | ❌ | ❌ |
| Twitter/X sync | ✅ DMs + mentions | ❌ | Import only |
| WhatsApp sync | ✅ QR pairing | ❌ | ❌ |
| LinkedIn sync | ✅ Chrome extension | ❌ | ✅ |
| Life event detection | ✅ multi-source | Manual | Job changes only |
| Self-hostable | ✅ | ✅ | ❌ |
| Open source | ✅ AGPL-3.0 | ✅ AGPL-3.0 | ❌ |

## What it does

- **Unified timeline** — every email, DM, mention, and call in one contact view
- **Relationship scoring** — 0–10 score surfaces who's going cold
- **AI suggestions** — drafts contextual follow-ups, never sends automatically
- **Life event detection** — new jobs, birthdays, bio changes across platforms
- **Identity resolution** — merges the same person across Gmail, LinkedIn, Telegram, etc.
- **MCP server** — query your CRM from Claude Desktop, Cursor, and other MCP clients

See the [feature docs](https://docs.pingcrm.xyz/features/dashboard) for screenshots and details.

---

## Get it running

### Option 1 — One-click deploy

| Platform | Deploy |
|---|---|
| **Railway** | [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template?template=https://github.com/sneg55/pingcrm) |
| **Render** | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sneg55/pingcrm) |
| **DigitalOcean** | [![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/sneg55/pingcrm/tree/main) |
| **Fly.io** | `fly launch --from https://github.com/sneg55/pingcrm` |
| **Coolify** (self-hosted) | [Import as Docker Compose app](https://coolify.io/docs/applications/) |

After deploy, set `ANTHROPIC_API_KEY` and any OAuth credentials for integrations you want. [Environment reference →](https://docs.pingcrm.xyz/setup#environment-variables)

### Option 2 — Have an AI agent deploy it

Point Claude Code, Cursor, Codex, or any coding agent at [`AGENT_SETUP.md`](AGENT_SETUP.md) and ask it to deploy PingCRM on your VPS. Twelve-phase runbook — DNS, TLS, secrets, OAuth, the works.

```
"Read AGENT_SETUP.md and set up PingCRM for me on my server."
```

### Option 3 — Run it yourself

```bash
git clone https://github.com/sneg55/pingcrm.git
cd pingcrm
cp backend/.env.example backend/.env  # edit values
docker compose up -d
```

Full walk-through with integration setup: **[docs.pingcrm.xyz/setup](https://docs.pingcrm.xyz/setup)**

---

## Stack

**Backend:** FastAPI · PostgreSQL · Redis · Celery · Claude (Anthropic)
**Frontend:** Next.js · React · Tailwind
**Deploy:** Docker Compose · Caddy · GitHub Actions

[Architecture overview →](https://docs.pingcrm.xyz/architecture)

---

## Contributing

Contributions welcome — bugs, features, integrations, docs.

- [Contributing guide](CONTRIBUTING.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Open issues](https://github.com/sneg55/pingcrm/issues)

## License

[AGPL-3.0](LICENSE) — free to use, modify, self-host. Network use requires source disclosure.
