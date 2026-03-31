# Project Instructions

## Memory System

You have a persistent, file-based memory system. Build it up over time so future conversations have a complete picture of who the user is, how they'd like to collaborate, what behaviors to avoid or repeat, and the context behind the work.

If the user explicitly asks you to remember something, save it immediately as whichever type fits best. If they ask you to forget something, find and remove the relevant entry.

## Types of Memory

There are four discrete types. Only save information that is NOT derivable from the current project state (code, git history, file structure).

### user
**What it stores:** Information about the user's role, goals, responsibilities, and knowledge.
**When to save:** When you learn any details about the user's role, preferences, responsibilities, or knowledge.
**How to use:** Tailor your behavior to the user's profile. Collaborate with a senior engineer differently than a first-time coder. Frame explanations relative to their domain knowledge.

Examples:
- "I'm a data scientist investigating what logging we have in place" → save: user is a data scientist, currently focused on observability/logging
- "I've been writing Go for ten years but this is my first time touching the React side" → save: deep Go expertise, new to React — frame frontend explanations in terms of backend analogues

### feedback
**What it stores:** Guidance the user has given about how to approach work — both what to avoid AND what to keep doing.
**When to save:** Any time the user corrects your approach ("no not that", "don't", "stop doing X") OR confirms a non-obvious approach worked ("yes exactly", "perfect, keep doing that"). Corrections are easy to notice; confirmations are quieter — watch for them.
**How to use:** Let these memories guide your behavior so the user doesn't need to offer the same guidance twice.
**Structure:** Lead with the rule, then a **Why:** line and a **How to apply:** line. Knowing why lets you judge edge cases.

Examples:
- "don't mock the database in these tests — we got burned when mocked tests passed but prod migration failed" → save: integration tests must hit a real database. Why: mock/prod divergence masked a broken migration. How to apply: all test files in this repo use real DB connections.
- "stop summarizing what you just did, I can read the diff" → save: terse responses, no trailing summaries.
- "yeah the single bundled PR was the right call here" → save: for refactors, user prefers one bundled PR over many small ones. Confirmed approach — not a correction.

### project
**What it stores:** Information about ongoing work, goals, initiatives, bugs, or incidents NOT derivable from code or git history.
**When to save:** When you learn who is doing what, why, or by when. Always convert relative dates to absolute (e.g., "Thursday" → "2026-03-05").
**How to use:** Understand broader context behind the user's requests, anticipate coordination issues, make better suggestions.
**Structure:** Lead with the fact/decision, then **Why:** and **How to apply:** lines. Project memories decay fast — the why helps judge if they're still relevant.

Examples:
- "we're freezing all non-critical merges after Thursday" → save: merge freeze begins 2026-03-05 for mobile release cut. Flag non-critical PRs after that date.
- "ripping out old auth middleware because legal flagged session token storage" → save: auth rewrite driven by compliance, not tech debt — scope decisions should favor compliance over ergonomics.

### reference
**What it stores:** Pointers to where information lives in external systems.
**When to save:** When you learn about resources in external systems and their purpose.
**How to use:** When the user references an external system or you need external info.

Examples:
- "check Linear project INGEST for pipeline bugs" → save: pipeline bugs tracked in Linear project "INGEST"
- "grafana.internal/d/api-latency is what oncall watches" → save: latency dashboard — check when editing request-path code.

## What NOT to Save

- Code patterns, conventions, architecture, file paths, or project structure — derivable by reading the project
- Git history, recent changes, who-changed-what — `git log` / `git blame` are authoritative
- Debugging solutions or fix recipes — the fix is in the code, commit message has context
- Anything already documented in CLAUDE.md files
- Ephemeral task details: in-progress work, temporary state, current conversation context

These exclusions apply even when the user explicitly asks. If they ask to save a PR list or activity summary, ask what was *surprising* or *non-obvious* — that's the part worth keeping.

## Memory File Format

Each memory is its own `.md` file with YAML frontmatter:

```markdown
---
name: {{memory name}}
description: {{one-line description — be specific, used to decide relevance in future conversations}}
type: {{user, feedback, project, reference}}
---

{{memory content — for feedback/project types: rule/fact, then **Why:** and **How to apply:** lines}}
```

### Saving Process
1. Write the memory to its own file (e.g., `user_role.md`, `feedback_testing.md`)
2. Add a one-line pointer in `MEMORY.md`: `- [Title](file.md) — one-line hook`
3. Keep `MEMORY.md` under 200 lines — it's an index, not a dump

### Maintenance
- Keep name, description, and type fields up-to-date with content
- Organize semantically by topic, not chronologically
- Update or remove memories that are wrong or outdated
- Check for existing memories before writing duplicates

## When to Access Memories

- When memories seem relevant, or the user references prior-conversation work
- You MUST access memory when the user explicitly asks you to check, recall, or remember
- If the user says to *ignore* or *not use* memory: proceed as if MEMORY.md were empty

## Before Recommending from Memory

A memory that names a specific function, file, or flag is a claim that it existed *when written*. It may have been renamed, removed, or never merged. Before recommending:

- If the memory names a file path: check the file exists
- If the memory names a function or flag: grep for it
- If the user is about to act on your recommendation: verify first

"The memory says X exists" is not the same as "X exists now."

A memory that summarizes repo state is frozen in time. For *recent* or *current* state, prefer `git log` or reading the code over recalling the snapshot.

## Memory Consolidation (Dream)

Periodically review and consolidate memories:

### Phase 1 — Orient
- List the memory directory to see what exists
- Read MEMORY.md to understand the current index
- Skim existing topic files to improve rather than duplicate

### Phase 2 — Gather
- Check for new information worth persisting
- Look for existing memories that contradict current codebase state
- Search transcripts narrowly for specific context if needed

### Phase 3 — Consolidate
- Merge new signal into existing topic files (don't create near-duplicates)
- Convert relative dates to absolute dates
- Delete contradicted facts at the source

### Phase 4 — Prune
- Keep MEMORY.md under 200 lines / ~25KB
- Each index entry: one line, under ~150 chars: `- [Title](file.md) — one-line hook`
- Remove pointers to stale/superseded memories
- Resolve contradictions between files

---

## Git Safety

- Never force push
- Never skip hooks
- Never commit secrets
- Use heredoc syntax for multi-line commit messages

## Project-Specific Instructions

### Overview
PingCRM — Personal networking CRM that helps maintain professional relationships.
Users import contacts, connect email/messaging accounts, and get AI-powered follow-up suggestions.

### Tech Stack
- **Backend:** Python + FastAPI
- **Database:** PostgreSQL (relational)
- **Queue:** Redis + Celery
- **AI:** LLM API (Claude) for message generation and classification
- **Frontend:** Next.js (React)
- **Auth:** OAuth 2.0 (Google, Twitter, Telegram)

### Project Structure
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

### Development Commands
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

### Key Conventions
- Python: snake_case, type hints, async where appropriate
- TypeScript: camelCase for variables/functions, PascalCase for components
- API endpoints follow REST conventions: `/api/v1/contacts`, `/api/v1/interactions`
- All API responses use standard envelope: `{ data, error, meta }`
- Database models use UUID primary keys
- Environment variables in `.env` (never commit)

### Exception Handling Policy

See @.claude/rules/exception-handling.md for the full policy (logging requirements, typed exceptions per provider, re-raise vs sentinel rules).

### Development Rules
- **Never skip pre-push tests** — always run tests before pushing, never use `--no-verify` unless the user explicitly asks
- **No debug endpoints in prod** — never add debug/temporary endpoints unless the user explicitly asks
- **Twitter polling strategy** — cron only polls bios via bird CLI; tweet fetching + LLM classification is on-demand for suggestion generation (not daily)

### Platform Integrations
1. **Gmail** - OAuth + Gmail API for per-message email sync + BCC logging
2. **Telegram** - MTProto client (Telethon) for chat history, group members, bios
3. **Twitter/X** - OAuth 2.0 PKCE for DMs; bird CLI (cookies) for mentions, replies, bios
4. **LinkedIn** - Chrome extension with client-side Voyager API (cookies stay in browser). Pairing code auth, GraphQL messaging sync, DOM profile scraping.
5. **MCP Server** - Model Context Protocol server for AI clients (Claude Desktop, Cursor). 6 read-only tools. Lives at `backend/mcp_server/`.

### Production Access

See `CLAUDE.local.md` for SSH credentials and server details (not committed to repo).
