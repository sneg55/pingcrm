---
slug: /
sidebar_position: 1
title: Introduction
---

# Ping CRM

An AI-powered personal networking CRM that helps you maintain professional relationships.

**Upload your contacts, connect your accounts. Ping tells you who to reach out to and writes the message.**

## What is Ping CRM?

Ping CRM is a single-player networking tool designed for professionals who want to stay on top of their relationships without the overhead of a full-blown CRM. It connects to your existing communication channels (Gmail, Telegram, Twitter/X), analyzes your interaction patterns, and uses AI to suggest who you should reach out to and draft contextual messages.

## Key Capabilities

- **Contact Management** -- import from CSV, Google Contacts, or add manually. Full-text search across names, emails, bios, and message content.
- **Multi-Platform Sync** -- Gmail threads, Telegram DMs, Twitter DMs and mentions are automatically imported as interactions.
- **AI Follow-Up Suggestions** -- Claude analyzes your interaction patterns and generates contextual draft messages when it's time to reconnect.
- **Identity Resolution** -- automatically detects when contacts across different platforms are the same person and merges them.
- **Organization Tracking** -- group contacts by company, track relationship health per org.
- **Bio Monitoring** -- detects Twitter and Telegram bio changes (job changes, milestones) and surfaces them as events.
- **Relationship Scoring** -- automatic scoring based on interaction recency, frequency, and reciprocity.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x (async) |
| Database | PostgreSQL |
| Task Queue | Redis + Celery |
| AI | Anthropic Claude 3.5 Haiku |
| Frontend | Next.js 15, React 19, Tailwind CSS v4 |
| Telegram | Telethon (MTProto) |
| State Management | TanStack React Query v5 |

## Quick Start

```bash
git clone https://github.com/sneg55/pingcrm.git
cd pingcrm
```

See the [Setup Guide](/setup) for detailed installation instructions.
