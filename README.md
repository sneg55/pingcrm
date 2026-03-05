# Ping CRM

AI-powered personal networking CRM. Import contacts from Gmail, Telegram, and Twitter, track interactions across platforms, and get intelligent follow-up suggestions powered by Claude.

## Architecture

```
frontend/          Next.js 15 + React 19 + TypeScript + Tailwind CSS v4
backend/           FastAPI + SQLAlchemy 2.x (async) + Alembic + Celery
database           PostgreSQL (asyncpg)
cache/queue        Redis (Celery broker + result backend)
AI                 Anthropic Claude (event classification + message composition)
```

## Features

- **Contact Management** -- Import via CSV, Google Contacts sync, or manual entry. Unified profiles with email, phone, social handles, company, and tags.
- **Multi-Platform Sync** -- Gmail thread tracking, Telegram chat history, Twitter DMs/mentions/bio monitoring.
- **Identity Resolution** -- Automatic deduplication via deterministic (email/phone) and probabilistic (weighted scoring) matching, with manual merge UI.
- **Relationship Scoring** -- Signal-based 0-10 score factoring in message recency, reply speed, introductions, and silence periods. Green/yellow/red badges.
- **AI Follow-Up Suggestions** -- Weekly digest of people to reach out to, with AI-drafted messages adapted to your conversation tone.
- **Context Detection** -- LLM-powered event classification from Twitter activity (job changes, fundraising, product launches, etc.).
- **Notification System** -- In-app notifications for new suggestions and detected events, with unread badge.
- **Onboarding Flow** -- 4-step guided setup: welcome, connect Google, import contacts, done.

## Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+

## Getting Started

### 1. Clone and configure

```bash
git clone <repo-url> && cd pingcrm
```

### 2. Backend setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy and configure environment variables:

```bash
cp .env.example .env
# Edit .env -- at minimum set:
#   SECRET_KEY  (generate with: python -c "import secrets; print(secrets.token_urlsafe(64))")
#   DATABASE_URL
```

Run database migrations:

```bash
alembic upgrade head
```

Start the API server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:3000` and proxies `/api/*` requests to the backend.

### 4. Background workers (optional)

For periodic sync tasks (Gmail, Telegram, Twitter polling, weekly digest):

```bash
cd backend
celery -A worker worker --loglevel=info
celery -A worker beat --loglevel=info
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | JWT signing key (random, 64+ chars) |
| `DATABASE_URL` | Yes | PostgreSQL connection string (asyncpg) |
| `REDIS_URL` | No | Redis URL for Celery (default: `redis://localhost:6379/0`) |
| `GOOGLE_CLIENT_ID` | No | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | No | Google OAuth client secret |
| `TWITTER_API_KEY` | No | Twitter API v2 key |
| `TWITTER_API_SECRET` | No | Twitter API v2 secret |
| `TWITTER_CLIENT_ID` | No | Twitter OAuth 2.0 client ID |
| `TWITTER_CLIENT_SECRET` | No | Twitter OAuth 2.0 client secret |
| `TWITTER_REDIRECT_URI` | No | Twitter OAuth callback URL |
| `TELEGRAM_API_ID` | No | Telegram MTProto API ID |
| `TELEGRAM_API_HASH` | No | Telegram MTProto API hash |
| `ANTHROPIC_API_KEY` | No | Anthropic API key for Claude |

## Project Structure

```
backend/
  app/
    api/             Route handlers (auth, contacts, interactions, suggestions,
                     telegram, twitter, identity, notifications)
    core/            Config, database, auth, Celery setup
    integrations/    Google (OAuth, Contacts, Gmail), Telegram, Twitter
    models/          SQLAlchemy models (User, Contact, Interaction,
                     DetectedEvent, FollowUpSuggestion, IdentityMatch, Notification)
    schemas/         Pydantic request/response schemas
    services/        Business logic (scoring, identity resolution, event
                     classification, message composition, follow-up engine,
                     notifications, background tasks)
  alembic/           Database migrations

frontend/
  src/
    app/             Next.js pages (dashboard, contacts, suggestions,
                     identity, settings, notifications, onboarding, auth)
    components/      Reusable UI (nav, contact-card, timeline, score-badge,
                     csv-import, message-editor, empty-state, error-boundary)
    hooks/           React Query hooks (use-auth, use-contacts, use-suggestions,
                     use-identity, use-notifications, use-dashboard)
    lib/             API client, utilities
```

## API Overview

All endpoints return `{ data, error, meta }` envelope format.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Login (returns JWT) |
| GET | `/api/v1/auth/me` | Current user profile |
| POST | `/api/v1/auth/google/callback` | Google OAuth exchange |
| GET | `/api/v1/auth/twitter/url` | Twitter OAuth 2.0 URL |
| POST | `/api/v1/auth/twitter/callback` | Twitter OAuth exchange |
| POST | `/api/v1/auth/telegram/connect` | Send Telegram OTP |
| POST | `/api/v1/auth/telegram/verify` | Verify Telegram code |
| GET | `/api/v1/contacts` | List contacts (search, tag filter, pagination) |
| POST | `/api/v1/contacts` | Create contact |
| GET | `/api/v1/contacts/:id` | Get contact detail |
| PUT | `/api/v1/contacts/:id` | Update contact |
| DELETE | `/api/v1/contacts/:id` | Delete contact |
| POST | `/api/v1/contacts/import/csv` | Import contacts from CSV |
| POST | `/api/v1/contacts/sync/google` | Sync Google Contacts |
| POST | `/api/v1/contacts/sync/telegram` | Sync Telegram chats |
| GET | `/api/v1/contacts/:id/interactions` | Contact timeline |
| POST | `/api/v1/contacts/:id/interactions` | Add manual note |
| GET | `/api/v1/suggestions` | Pending follow-up suggestions |
| GET | `/api/v1/suggestions/digest` | Weekly digest |
| PUT | `/api/v1/suggestions/:id` | Update status (send/snooze/dismiss) |
| POST | `/api/v1/suggestions/generate` | Trigger suggestion generation |
| GET | `/api/v1/identity/matches` | Pending identity matches |
| POST | `/api/v1/identity/matches/:id/merge` | Confirm merge |
| POST | `/api/v1/identity/matches/:id/reject` | Reject match |
| POST | `/api/v1/identity/scan` | Trigger identity scan |
| GET | `/api/v1/notifications` | List notifications |
| GET | `/api/v1/notifications/unread-count` | Unread count |
| PUT | `/api/v1/notifications/:id/read` | Mark notification read |
| PUT | `/api/v1/notifications/read-all` | Mark all read |

## Celery Beat Schedule

| Task | Interval |
|------|----------|
| Gmail sync (all users) | Every 6 hours |
| Telegram sync (all users) | Every 12 hours |
| Twitter activity + DM poll | Every 12 hours |
| Relationship score recalculation | Daily |
| Follow-up suggestion generation | Weekly (Monday 9:00 UTC) |
| Weekly digest email | Weekly (Monday 9:00 UTC) |
| Snooze reactivation | Hourly |

## License

Private / All rights reserved.
