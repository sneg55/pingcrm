# PingCRM - AI Networking CRM

## Project Overview
Personal networking CRM that helps maintain professional relationships.
Users import contacts, connect email/messaging accounts, and get AI-powered follow-up suggestions.

## Tech Stack
- **Backend:** Python + FastAPI
- **Database:** PostgreSQL (relational)
- **Queue:** Redis + Celery
- **AI:** LLM API (Claude) for message generation and classification
- **Frontend:** Next.js (React)
- **Auth:** OAuth 2.0 (Google, Twitter, Telegram)

## Project Structure
```
pingcrm/
├── mvp.md              # Product spec (source of truth for requirements)
├── CLAUDE.md           # This file
├── backend/            # FastAPI application
│   ├── app/
│   │   ├── main.py
│   │   ├── models/     # SQLAlchemy models
│   │   ├── schemas/    # Pydantic schemas
│   │   ├── api/        # Route handlers
│   │   ├── services/   # Business logic
│   │   ├── integrations/  # Gmail, Telegram, Twitter
│   │   └── core/       # Config, auth, deps
│   ├── alembic/        # DB migrations
│   ├── tests/
│   └── requirements.txt
├── frontend/           # Next.js application
│   ├── src/
│   │   ├── app/        # App router pages
│   │   ├── components/ # React components
│   │   ├── lib/        # Utilities, API client
│   │   └── hooks/      # Custom React hooks
│   ├── package.json
│   └── tsconfig.json
├── landing/            # Marketing landing page (Next.js)
└── docs/               # Docusaurus documentation site
```

## Development Commands
```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install
npm run dev

# Database
alembic upgrade head
alembic revision --autogenerate -m "description"

# API type generation (run after adding/changing API endpoints)
cd backend && PYTHONPATH=. python3 -c "
import json; from app.main import app; from fastapi.openapi.utils import get_openapi
schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
with open('openapi.json', 'w') as f: json.dump(schema, f, indent=2)
"
cd frontend && npm run generate:api  # regenerates src/lib/api-types.d.ts

# CI guards
cd backend && PYTHONPATH=. python3 scripts/check_response_models.py  # all endpoints need response_model
cd frontend && bash scripts/check-as-any.sh  # as-any count must not increase

# Tests (fresh env setup)
cd backend && pip install -r requirements-test.txt  # includes pytest + pytest-asyncio
createdb pingcrm_test  # PostgreSQL test database (or set TEST_DATABASE_URL)
cd backend && pytest
cd frontend && npm install && npm test

# Celery worker + beat (combined, for development)
cd backend && celery -A worker.celery_app worker --beat --loglevel=info

# Celery worker and beat as separate processes (recommended for production)
cd backend && celery -A worker.celery_app beat --loglevel=info
cd backend && celery -A worker.celery_app worker --loglevel=info

# Production logs (structured JSON, rotating files)
# Local: logs/pingcrm.log (10MB, 5 backups)
# Docker: docker compose logs backend --tail=200
# Docker: docker compose logs worker --tail=200
# Env vars: LOG_LEVEL=DEBUG, LOG_LEVEL_SQL=WARNING, LOG_LEVEL_CELERY=INFO

# Production server access: see .claude/ memory for SSH details
```

## Key Conventions
- Python: snake_case, type hints, async where appropriate
- TypeScript: camelCase for variables/functions, PascalCase for components
- API endpoints follow REST conventions: `/api/v1/contacts`, `/api/v1/interactions`
- All API responses use standard envelope: `{ data, error, meta }`
- Database models use UUID primary keys
- Environment variables in `.env` (never commit)

## Exception Handling Policy

See @.claude/rules/exception-handling.md for the full policy (logging requirements, typed exceptions per provider, re-raise vs sentinel rules).

## Development Rules
- **Never skip pre-push tests** — always run tests before pushing, never use `--no-verify` unless the user explicitly asks
- **No debug endpoints in prod** — never add debug/temporary endpoints unless the user explicitly asks
- **Twitter polling strategy** — cron only polls bios via bird CLI; tweet fetching + LLM classification is on-demand for suggestion generation (not daily)

## Platform Integrations
1. **Gmail** - OAuth + Gmail API for per-message email sync + BCC logging
2. **Telegram** - MTProto client (Telethon) for chat history, group members, bios
3. **Twitter/X** - OAuth 2.0 PKCE for DMs; bird CLI (cookies) for mentions, replies, bios
4. **LinkedIn** - Chrome extension with client-side Voyager API (cookies stay in browser). Pairing code auth, GraphQL messaging sync, DOM profile scraping.
5. **MCP Server** - Model Context Protocol server for AI clients (Claude Desktop, Cursor). 6 read-only tools. Lives at `backend/mcp_server/`.

## Production Access

See `CLAUDE.local.md` for SSH credentials and server details (not committed to repo).
