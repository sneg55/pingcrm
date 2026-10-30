---
slug: /
sidebar_position: 1
title: Introduction
description: "PingCRM is an open-source, self-hostable AI personal networking CRM that syncs Gmail, Telegram, Twitter/X, and LinkedIn to help you keep in touch."
---

# PingCRM

An AI-powered personal networking CRM for maintaining professional relationships.

**Upload your contacts, connect your accounts. Ping tells you who to reach out to and writes the message.**

## What is PingCRM?

PingCRM is a single-user networking tool for people who want to keep up with their relationships without running a full CRM. It connects to your existing communication channels (Gmail, Telegram, Twitter/X, LinkedIn, WhatsApp), analyzes your interaction patterns, and uses AI to suggest who you should reach out to and draft contextual messages.

## Key Capabilities

- **Contact Management**: import from CSV, Google Contacts, or add manually. Search covers names, emails, bios, and message content.
- **Multi-Platform Sync**: Gmail threads, Telegram DMs, Twitter DMs and mentions, LinkedIn messages, and WhatsApp chats (via a QR-paired sidecar) are imported as interactions.
- **AI Follow-Up Suggestions**: Claude reads your interaction patterns and drafts a message when it is time to reconnect.
- **Identity Resolution**: detects when contacts on different platforms (Gmail, Telegram, Twitter, LinkedIn) are the same person and merges them.
- **Organization Tracking**: group contacts by company and track relationship health per organization.
- **LinkedIn Extension**: a Chrome extension syncs LinkedIn messages and profiles via the Voyager API and adds AI suggestion buttons to the LinkedIn composer.
- **Bio Monitoring**: detects Twitter and Telegram bio changes (job changes, milestones) and surfaces them as events.
- **Relationship Scoring**: scores each relationship from interaction recency, frequency, and reciprocity.
- **Map View**: shows your contacts on a map by location, which helps when planning trips and local meetups.
- **MCP Server**: a read-only Model Context Protocol server that exposes your CRM data to AI clients like Claude Desktop and Cursor.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x (async) |
| Database | PostgreSQL |
| Task Queue | Redis + Celery |
| AI | Anthropic Claude |
| Frontend | Next.js 16, React 19, Tailwind CSS v4 |
| Telegram | Telethon (MTProto) |
| State Management | TanStack React Query v5 |

## Quick Start

```bash
git clone https://github.com/sneg55/pingcrm.git
cd pingcrm
```

See the [Setup Guide](/setup) for detailed installation instructions.
