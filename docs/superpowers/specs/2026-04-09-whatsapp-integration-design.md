# WhatsApp Integration Design

**Date:** 2026-04-09
**Status:** Approved

## Overview

Add WhatsApp as a platform integration to PingCRM, enabling users to sync personal chat history and contact profile information. Uses the unofficial WhatsApp Web protocol (via whatsapp-web.js) running as a Node.js HTTP sidecar, consistent with the Telegram integration's approach of using unofficial clients for personal chat access.

## Scope

- **In scope:** Messages (inbound/outbound), contact profile info (name, about, avatar), QR code authentication, initial backfill + real-time live sync, session health monitoring with proactive notifications.
- **Out of scope:** Group messages/context, media attachments, read receipts, online status, sending messages from PingCRM.

## Architecture

### Node Sidecar (whatsapp-sidecar)

A standalone Express.js service wrapping whatsapp-web.js. One WhatsApp client instance per connected user, managed in memory.

**REST Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/sessions/:userId/start` | Initialize a WA client, return QR code data |
| GET | `/sessions/:userId/qr` | Get current QR code (for polling/refresh) |
| GET | `/sessions/:userId/status` | Connection status (connecting, qr_pending, connected, disconnected) |
| POST | `/sessions/:userId/backfill` | Fetch recent messages (last 30 days) |
| GET | `/sessions/:userId/contacts` | List WA contacts with profile info |
| DELETE | `/sessions/:userId` | Disconnect and destroy session |
| GET | `/health` | Docker health check |

**Webhook events (pushed to Python backend):**
- `message_received` — new incoming/outgoing message
- `session_disconnected` — session died (triggers user notification)
- `contact_updated` — profile name/about/photo changed

**Session persistence:** whatsapp-web.js `LocalAuth` strategy maps each userId to a directory on a Docker volume. Sessions survive container restarts. On container start, sessions are not auto-reconnected — the Python backend's health-check task calls `/sessions/:userId/start` for users with `whatsapp_connected = True`.

**Webhook authentication:** All callbacks include an `X-Webhook-Signature` header (HMAC-SHA256 of the request body using `WHATSAPP_WEBHOOK_SECRET`).

**Resource cap:** 50 concurrent sessions max per sidecar instance.

### Sidecar Project Structure

```
whatsapp-sidecar/
├── package.json
├── Dockerfile
├── src/
│   ├── index.js          # Express server, route setup
│   ├── session-manager.js # Create/destroy/track WA client instances per user
│   ├── routes.js          # REST endpoints
│   ├── webhook.js         # Push events to Python backend (HMAC-signed)
│   └── config.js          # Env vars (WEBHOOK_URL, WEBHOOK_SECRET, port, session path)
├── .dockerignore
└── .gitignore
```

**Backfill:** The backfill endpoint fetches messages and streams them as webhook callbacks in batches, so the Python side processes incrementally (not one giant response).

**Logging:** Structured JSON to stdout, userId on every log line. No phone numbers in logs.

### Deployment

New service in `docker-compose.prod.yml`:

```yaml
whatsapp-sidecar:
  image: ghcr.io/sneg55/pingcrm/whatsapp-sidecar:latest
  volumes:
    - whatsapp_sessions:/data/sessions
  environment:
    - WEBHOOK_URL=http://backend:8000/api/v1/webhooks/whatsapp
    - WEBHOOK_SECRET=${WHATSAPP_WEBHOOK_SECRET}
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3001/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

## Python Backend Integration

### New Files

- `backend/app/integrations/whatsapp.py` — HTTP client to the sidecar (httpx async). Start session, fetch contacts, trigger backfill.
- `backend/app/integrations/whatsapp_helpers.py` — Contact matching by phone number (E.164 normalization), `_upsert_interaction()` for WA messages.
- `backend/app/api/whatsapp.py` — User-facing endpoints.
- `backend/app/api/whatsapp_webhooks.py` — Internal webhook receiver for sidecar events (HMAC-verified).
- `backend/app/services/task_jobs/whatsapp.py` — Celery tasks.

### User-Facing API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/auth/whatsapp/connect` | Tell sidecar to start session, return QR data |
| GET | `/api/v1/auth/whatsapp/qr` | Poll for fresh QR code |
| GET | `/api/v1/auth/whatsapp/status` | Connection status |
| POST | `/api/v1/contacts/sync/whatsapp` | Trigger manual backfill sync |
| DELETE | `/api/v1/auth/whatsapp/disconnect` | Disconnect + destroy sidecar session |

### Webhook Endpoint

`POST /api/v1/webhooks/whatsapp` — receives events from the sidecar.

Event handling:
- **`message_received`**: Match contact by phone number, upsert interaction via `_upsert_interaction()`, recalculate contact score.
- **`session_disconnected`**: Set `user.whatsapp_connected = False`, create notification ("WhatsApp disconnected — please re-link").
- **`contact_updated`**: Update contact's `whatsapp_name`, `whatsapp_about`, `whatsapp_avatar_url`.

### Celery Tasks

- `sync_whatsapp_backfill(user_id)` — Called after initial connect. Asks sidecar for recent messages (hardcoded 30-day lookback), processes in batches, creates interactions. Records SyncEvent.
- `check_whatsapp_sessions()` — Daily health-check task. Pings each active session's status via sidecar, notifies user if any are dead. Runs on Celery Beat schedule.

No `sync_whatsapp_all` needed — the sidecar pushes messages in real-time.

## Data Model Changes

### User Model — New Fields

| Field | Type | Purpose |
|-------|------|---------|
| `whatsapp_phone` | String, nullable | User's WhatsApp phone number (display/reference) |
| `whatsapp_connected` | Boolean, default False | Whether session is active |
| `whatsapp_last_synced_at` | DateTime, nullable | Last successful message sync |

No tokens stored — auth state lives in the sidecar's session files.

### Contact Model — New Fields

| Field | Type | Purpose |
|-------|------|---------|
| `whatsapp_phone` | String, nullable | Contact's phone number (E.164, primary match key) |
| `whatsapp_name` | String, nullable | Profile display name |
| `whatsapp_about` | String, nullable | "About" text (bio equivalent) |
| `whatsapp_avatar_url` | String, nullable | Profile photo URL |
| `whatsapp_bio_checked_at` | DateTime, nullable | Last profile info refresh |

### Interaction Table — No Changes

WhatsApp messages use existing fields:
- `platform = "whatsapp"`
- `raw_reference_id` = WhatsApp message ID (for dedup)
- `direction` = inbound/outbound
- `content_preview` = message text (truncated to 500 chars)
- `occurred_at` = message timestamp

### Contact Matching

Match by phone number in E.164 format (`+1234567890`). The helper normalizes both the incoming WA number and existing contact phone fields before matching. If no match, create a new contact with the WA profile name.

Single Alembic migration adds all new columns.

## Frontend

### New Files

- `frontend/src/app/settings/_components/platform-cards/whatsapp-card.tsx`
- `frontend/src/app/settings/_hooks/use-whatsapp-connect-flow.ts`

### WhatsApp Settings Card

Follows existing card pattern (like Telegram):

- **Disconnected:** "Connect WhatsApp" button.
- **Connecting:** QR code displayed inline with scan instructions. Frontend polls `/api/v1/auth/whatsapp/qr` every 3 seconds until status becomes `connected` or QR expires (then refreshes). QR string rendered via `qrcode.react`.
- **Connected:** Phone number, connection badge, last synced time. Sync button for manual backfill. Kebab menu with Disconnect.
- **Error:** "Session expired" with re-connect prompt.

### Connect Flow Hook

`use-whatsapp-connect-flow.ts`:
- States: `idle` -> `qr_pending` -> `connected` (or `error`)
- Calls POST `/connect`, gets QR data, renders as image
- Polls `/status` until connected
- On connect success: triggers backfill via POST `/sync/whatsapp`

### Contact Timeline

WhatsApp interactions get a WhatsApp icon (green speech bubble) in the timeline. The timeline already switches icon by `interaction.platform` — add the `"whatsapp"` case with the appropriate icon.

### Contact Detail Page

Next to the phone number field, show a WhatsApp icon if `contact.whatsapp_phone` is set. This signals "this person is reachable on WhatsApp."

No other frontend changes needed — interactions from WhatsApp automatically appear in contact timelines via the standard Interaction model.

## Security & Operational Concerns

### Service-to-Service Auth

All webhook calls from sidecar to backend include `X-Webhook-Signature` (HMAC-SHA256 of request body using `WHATSAPP_WEBHOOK_SECRET`). Backend verifies before processing. Shared secret via env var in both containers.

### Session Data at Rest

whatsapp-web.js `LocalAuth` stores session credentials on disk. Docker volume should be on encrypted filesystem in production. Session directories named by userId (UUID), not phone number.

### Phone Number Handling

Stored in E.164 format. Not logged — use contact_id in log messages instead.

### Rate Limiting

whatsapp-web.js handles WhatsApp's rate limits internally. Sidecar adds per-user mutex on backfill to prevent duplicate concurrent syncs.

### Failure Modes

- **Sidecar crashes:** Docker restarts it. Sessions restore from disk on next health-check cycle.
- **Backend crashes:** Sidecar queues webhook events in memory (small buffer, ~1000 events). If backend stays down too long, events are dropped but next backfill catches up.
- **WhatsApp bans:** Risk inherent to unofficial approach (same as Telegram). No mitigation beyond normal usage patterns — no bulk messaging, reasonable sync intervals.
- **QR code expires:** whatsapp-web.js emits new QR codes periodically. Frontend polls and re-renders.

### Monitoring

Daily `check_whatsapp_sessions()` Celery task covers session health. Sidecar logs + Docker health check cover process health.
