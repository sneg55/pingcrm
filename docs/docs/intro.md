---
slug: /
sidebar_position: 1
title: Introduction
description: "PingCRM is an open-source, self-hostable AI personal networking CRM that syncs Gmail, Telegram, Twitter/X, and LinkedIn to help you keep in touch."
---

# PingCRM

An AI-powered personal networking CRM that helps you maintain professional relationships.

**Upload your contacts, connect your accounts. Ping tells you who to reach out to and writes the message.**

## What is PingCRM?

PingCRM is a single-player networking tool designed for professionals who want to stay on top of their relationships without the overhead of a full-blown CRM. It connects to your existing communication channels (Gmail, Telegram, Twitter/X, WhatsApp), analyzes your interaction patterns, and uses AI to suggest who you should reach out to and draft contextual messages.

## Key Capabilities

- **Contact Management** -- import from CSV, Google Contacts, or add manually. Full-text search across names, emails, bios, and message content.
- **Multi-Platform Sync** -- Gmail threads, Telegram DMs, Twitter DMs and mentions, LinkedIn messages, and WhatsApp chats (via a QR-paired sidecar) are automatically imported as interactions.
- **AI Follow-Up Suggestions** -- Claude analyzes your interaction patterns and generates contextual draft messages when it's time to reconnect.
- **Identity Resolution** -- automatically detects when contacts across different platforms (Gmail, Telegram, Twitter, LinkedIn) are the same person and merges them.
- **Organization Tracking** -- group contacts by company, track relationship health per org.
- **LinkedIn Extension** -- Chrome extension syncs LinkedIn messages and profiles via the Voyager API, with AI suggestion buttons injected into the LinkedIn composer.
- **Bio Monitoring** -- detects Twitter and Telegram bio changes (job changes, milestones) and surfaces them as events.
- **Relationship Scoring** -- automatic scoring based on interaction recency, frequency, and reciprocity.
- **Map View** -- a geographic map of your contacts by location, useful for planning trips and local meetups.
- **MCP Server** -- a read-only Model Context Protocol server that exposes your CRM data to AI clients like Claude Desktop and Cursor.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x (async) |
| Database | PostgreSQL |
| Task Queue | Redis + Celery |
| AI | Anthropic Claude |
| Frontend | Next.js 15, React 19, Tailwind CSS v4 |
| Telegram | Telethon (MTProto) |
| State Management | TanStack React Query v5 |

## Quick Start

```bash
git clone https://github.com/sneg55/pingcrm.git
cd pingcrm
```

See the [Setup Guide](/setup) for detailed installation instructions.
