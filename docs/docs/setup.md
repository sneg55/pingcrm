---
sidebar_position: 2
title: Setup Guide
description: "Set up PingCRM with Docker Compose for local development or self-hosting, or install each service yourself."
---

# Setup Guide

This guide covers setting up PingCRM for local development and a production deployment. Docker Compose is the recommended path. If you would rather install each service yourself, skip ahead to [Manual Setup](#manual-setup-alternative).

## Prerequisites

- **Docker** and **Docker Compose** (recommended)
- Or, for manual setup: **Python 3.12+**, **Node.js 20+**, **PostgreSQL 14+**, **Redis 6+**

## 1. Clone the Repository

```bash
git clone https://github.com/sneg55/pingcrm.git
cd pingcrm
```

## 2. Docker Setup (Recommended)

Docker Compose starts PostgreSQL, Redis, the backend, the frontend, and the Celery worker in a single command.

```bash
# Configure environment variables
cp backend/.env.example backend/.env
cp .env.docker.example .env

# Set required variables used by Docker Compose interpolation
# Edit .env and replace POSTGRES_PASSWORD and SECRET_KEY.

# Start all services
docker compose up

# Run database migrations (first time or after model changes)
docker compose exec backend alembic upgrade head
```

The dev compose file (`docker-compose.yml`) builds images from local source and mounts volumes for avatar storage and logs. PostgreSQL and Redis are also published on `127.0.0.1` (ports 5432 and 6379) for host-based development. Open [http://localhost:3000](http://localhost:3000) in your browser.

Registration is closed by default. To create your first account, set `ALLOW_REGISTRATION=true` in `backend/.env`, restart the backend, and register at `/auth/register`. Remove the setting afterwards.

### Environment variables

Docker Compose reads service runtime variables from `./backend/.env` (via `env_file`). It also interpolates root-level Compose variables from `./.env` or the shell before services start. At minimum, set:

- `POSTGRES_PASSWORD`: required in `./.env` or the shell; used by both the `postgres` and `backend` services
- `SECRET_KEY`: required in `./.env` or the shell, at least 32 characters (the backend refuses to start otherwise); generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`

All other integration credentials (`GOOGLE_CLIENT_ID`, `TWITTER_CLIENT_ID`, etc.) are passed through as optional environment variables. Skip ahead to [Platform Credentials](#3-platform-credentials) to fill them in.

Twitter/X cookies are stored per user and captured by the Chrome extension. There is no server-wide cookie setting. Each user pairs their browser once and the extension keeps the cookies fresh. See [Twitter/X Integration](features/twitter.md#connecting-your-x-account-bird-cli) for details.

### Production

The production compose file (`docker-compose.prod.yml`) uses pre-built images from `ghcr.io` and adds a Caddy reverse proxy with automatic HTTPS:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Key differences from dev:
- Pre-built container images instead of local builds
- Caddy reverse proxy on ports 80/443, serving the hostname in `DOMAIN` (compose refuses to start without it)
- A `whatsapp-sidecar` service for [WhatsApp](features/whatsapp.md), configured with `WHATSAPP_WEBHOOK_SECRET`
- Redis protected by `REDIS_PASSWORD`
- `restart: unless-stopped` on all services
- No `env_file`: the compose file passes a fixed list of variables from `./.env` or the shell into each service

Because of that fixed list, a variable such as `ALLOW_REGISTRATION` or `DISABLE_UPDATE_CHECK` reaches the containers only if you add it under the `environment` block of the `backend` service (and `worker`, for the update check).

## 3. Platform Credentials

All integrations are optional. The app works without them, and you can add contacts manually or via CSV. Add the credentials below to `backend/.env` (Docker) or `backend/.env` with your venv (manual).

### Google OAuth (Gmail, Contacts, Calendar)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable APIs: **Gmail API**, **Google People API**, **Google Calendar API**
4. Go to **Credentials > Create Credentials > OAuth 2.0 Client ID**
5. Set type to **Web application**
6. Add redirect URI: `http://localhost:3000/auth/google/callback`
7. Add to `.env`:

```env
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
```

Google is not a login method. You connect it from **Settings > Integrations** while signed in, and the Google account is attached to your user. You can connect more than one, and Gmail and Calendar sync run for every linked account. The redirect URI the backend sends comes from `GOOGLE_REDIRECT_URI`.

### Twitter/X (DMs, Mentions, Bio Monitoring)

1. Go to [Twitter Developer Portal](https://developer.twitter.com/)
2. Create a project and app with **OAuth 2.0 + PKCE**
3. Set callback: `http://localhost:3000/auth/twitter/callback`
4. Request scopes: `dm.read`, `tweet.read`, `users.read`, `offline.access`
5. Add to `.env`:

```env
TWITTER_CLIENT_ID=your_client_id
TWITTER_CLIENT_SECRET=your_client_secret
TWITTER_API_KEY=your_api_key
TWITTER_API_SECRET=your_api_secret
TWITTER_REDIRECT_URI=http://localhost:3000/auth/twitter/callback
```

### Telegram (Chat Sync, Group Discovery)

1. Go to [my.telegram.org](https://my.telegram.org/)
2. Log in and go to **API development tools**
3. Create a new application
4. Add to `.env`:

```env
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
```

### Anthropic / Claude AI

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Create an API key
3. Add to `.env`:

```env
ANTHROPIC_API_KEY=your_api_key
```

---

## Manual Setup (Alternative)

Prefer to run services directly on your host? Install PostgreSQL, Redis, Python, and Node.js yourself.

### Database

```bash
createdb pingcrm
```

### Redis

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# Verify
redis-cli ping  # PONG
```

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_urlsafe(64))">
ENCRYPTION_KEY=<run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
DATABASE_URL=postgresql+asyncpg://localhost:5432/pingcrm
REDIS_URL=redis://localhost:6379/0
```

Run migrations:

```bash
alembic upgrade head
```

### Frontend

```bash
cd frontend
npm install
```

The frontend proxies `/api/*` (and `/static/*`) to the backend via Next.js rewrites (default: `http://localhost:8000`, configurable via `NEXT_PUBLIC_API_URL`).

### Running the Application

Run three processes, each in its own terminal:

```bash
# Terminal 1: Backend API (http://localhost:8000)
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2: Frontend (http://localhost:3000)
cd frontend && npm run dev

# Terminal 3: Celery worker + beat
cd backend && source .venv/bin/activate
celery -A worker.celery_app worker --beat --loglevel=info
```

For production, run beat and worker as separate processes:

```bash
celery -A worker.celery_app beat --loglevel=info
celery -A worker.celery_app worker --loglevel=info
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | JWT signing key, at least 32 characters |
| `DATABASE_URL` | Yes | PostgreSQL connection string (asyncpg) |
| `REDIS_URL` | No | Redis URL (default: `redis://localhost:6379/0`) |
| `ENCRYPTION_KEY` | Prod / for OAuth | Fernet key for stored OAuth tokens. The backend refuses to start without it when `ENVIRONMENT=production`, and any platform integration needs it |
| `GOOGLE_CLIENT_ID` | No | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | No | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | No | Google OAuth redirect URI (default: `http://localhost:3000/auth/google/callback`) |
| `TWITTER_CLIENT_ID` | No | Twitter OAuth 2.0 client ID |
| `TWITTER_CLIENT_SECRET` | No | Twitter OAuth 2.0 client secret |
| `TWITTER_API_KEY` | No | Twitter API v2 key |
| `TWITTER_API_SECRET` | No | Twitter API v2 secret |
| `TWITTER_BEARER_TOKEN` | No | Twitter API v2 bearer token |
| `TWITTER_REDIRECT_URI` | No | Twitter OAuth redirect URI (default: `http://localhost:3000/auth/twitter/callback`) |
| `TELEGRAM_API_ID` | No | Telegram MTProto API ID |
| `TELEGRAM_API_HASH` | No | Telegram MTProto API hash |
| `ANTHROPIC_API_KEY` | No | Anthropic API key for Claude |
| `APOLLO_API_KEY` | No | Apollo API key for contact enrichment |
| `MAPBOX_SECRET_TOKEN` | No | Mapbox token used by the worker for geocoding (see [Map](features/map.md#configuration)) |
| `MAPBOX_PUBLIC_TOKEN` | No | Mapbox token surfaced to the browser via `/api/v1/map/config` |
| `CHROME_EXTENSION_ID` | No | Chrome extension ID for LinkedIn data ingestion via the browser extension |
| `WHATSAPP_WEBHOOK_SECRET` | Prod | HMAC secret shared with the WhatsApp sidecar. The backend refuses to start without it when `ENVIRONMENT=production` |
| `WHATSAPP_SIDECAR_URL` | No | Sidecar base URL (default: `http://localhost:3001`) |
| `ENVIRONMENT` | No | Runtime environment (default: `development`; set `production` to enforce the startup checks above) |
| `ALLOW_REGISTRATION` | No | Set to `true` to allow creating accounts (default: `false`) |
| `FRONTEND_URL` | No | Public frontend URL (default: `http://localhost:3000`) |
| `CORS_ORIGINS` | No | Allowed browser origins, as a JSON list (default: `http://localhost:3000` and `http://127.0.0.1:3000`) |
| `TRUSTED_PROXY_HOPS` | No | Reverse proxies in front of the backend, used to read the client IP for rate limiting (default: `1`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Login token lifetime (default: `1440`) |
| `DISABLE_UPDATE_CHECK` | No | Any non-empty value turns off the release check (see [Update Notifications](operations/updates.md)) |
| `NEXT_PUBLIC_API_URL` | No | Backend URL for frontend (default: `http://localhost:8000`) |
| `DOMAIN` | Prod compose | Hostname Caddy serves, read by `docker-compose.prod.yml` only |
| `POSTGRES_PASSWORD` | Compose | PostgreSQL password, read by both compose files only |
| `REDIS_PASSWORD` | Prod compose | Redis password, read by `docker-compose.prod.yml` only |

## Running Tests

```bash
# Backend (pytest)
cd backend
pytest
pytest --cov=app --cov-report=term-missing

# Frontend (Vitest)
cd frontend
npm test
```
