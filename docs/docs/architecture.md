---
sidebar_position: 3
title: Technical Architecture
---

# Technical Architecture

## Dependency Layers

```
┌─────────────┐
│   Frontend  │  Next.js + React
├─────────────┤
│  API Layer  │  FastAPI routes (thin handlers)
├─────────────┤
│  Services   │  Business logic, follow-up engine, scoring
├─────────────┤
│Integrations │  Gmail, Telegram, Twitter, LinkedIn, Apollo
├─────────────┤
│   Models    │  SQLAlchemy ORM + Pydantic schemas
├─────────────┤
│    Core     │  Config, auth, database, Redis, logging
└─────────────┘
```

### Allowed Import Direction

- `api/` → `services/` → `integrations/` → `models/` → `core/`
- Never: `integrations/` → `api/` or `services/` → `api/`

### Module Ownership

| Directory | Responsibility |
|-----------|---------------|
| `api/` | HTTP request handling, validation, response formatting |
| `services/` | Business logic, orchestration, no HTTP concerns |
| `integrations/` | External API clients, protocol adapters |
| `models/` | Database schema, relationships |
| `schemas/` | Pydantic request/response models |
| `core/` | Cross-cutting: config, auth, database, logging, middleware |
| `task_jobs/` | Celery task definitions, organized by domain |

### Key Files by Size

| File | Lines | Role |
|------|-------|------|
| `integrations/telegram.py` | ~800 | Telegram DM/bio sync |
| `integrations/telegram_transport.py` | ~200 | Telethon client lifecycle |
| `integrations/telegram_helpers.py` | ~150 | Contact resolution helpers |
| `integrations/telegram_groups.py` | ~250 | Group member sync |
| `integrations/twitter.py` | ~700 | Twitter DM/mention/reply sync |
| `integrations/twitter_auth.py` | ~160 | OAuth 2.0 PKCE token management |
| `services/followup_engine.py` | ~750 | AI follow-up suggestion generation |
| `services/scoring.py` | ~200 | Relationship score calculation |

---

## System Overview

PingCRM is a three-tier application: a Next.js frontend communicates with a FastAPI backend, which persists data in PostgreSQL and uses Redis for caching, task brokering, and ephemeral state. Celery workers handle background sync, scoring, and AI-powered suggestion generation.

```
┌─────────────────┐       ┌──────────────────────┐       ┌────────────────┐
│   Next.js 15    │──────>│   FastAPI (async)     │──────>│  PostgreSQL    │
│   React 19      │ REST  │   Pydantic schemas    │  ORM  │  UUID PKs      │
│   Tailwind v4   │<──────│   JWT auth            │<──────│  GIN indexes   │
└─────────────────┘       └──────────┬───────────┘       └────────────────┘
                                     │
                          ┌──────────▼───────────┐
                          │   Redis              │
                          │   - Celery broker    │
                          │   - Rate gates       │
                          │   - Tweet cache      │
                          │   - OAuth nonces     │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │   Celery Workers     │
                          │   - Gmail sync       │
                          │   - Telegram sync    │
                          │   - Twitter polling  │
                          │   - Score refresh    │
                          │   - AI suggestions   │
                          └──────────────────────┘
```

External services: Gmail API (OAuth), Telegram MTProto (Telethon), Twitter/X via Bird CLI (primary, cookie-based) with Twitter API v2 (OAuth 2.0 PKCE) as fallback, Anthropic Claude API (event classification and message composition), and a Chrome extension for LinkedIn profile data ingestion.

---

## Backend Architecture

The FastAPI application lives under `backend/app/` and follows a layered structure:

```
backend/app/
├── main.py              # FastAPI app factory, CORS, router mounting
├── api/                 # Route handlers (REST endpoints)
│   ├── contacts_routes/ # Contacts: CRUD, imports, sync, taxonomy, messaging
│   ├── interactions.py  # Interaction timeline
│   ├── suggestions.py   # Follow-up suggestions, snooze, dismiss
│   ├── identity.py      # Identity resolution scan, review, merge
│   ├── organizations.py # Company records and stats
│   ├── notifications.py # In-app notification feed
│   ├── auth.py          # Login, register, OAuth callbacks
│   ├── telegram.py      # Connect, sync, send messages
│   ├── twitter.py       # OAuth PKCE flow, polling
│   ├── linkedin.py      # Extension data push (profiles + messages)
│   ├── extension.py     # Chrome extension pairing
│   ├── activity.py      # Recent activity feed
│   └── settings.py      # User preferences
├── models/              # SQLAlchemy 2.x async ORM models
├── schemas/             # Pydantic request/response schemas
├── services/            # Business logic layer
├── integrations/        # Third-party API clients
└── core/                # Config, auth, database, encryption, Redis
```

### API Response Envelope

All endpoints return a typed generic envelope. This provides a consistent contract for the frontend:

```python
from pydantic import BaseModel, Generic, TypeVar

T = TypeVar("T")

class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    error: str | None = None
    meta: dict | None = None
```

Endpoints declare `response_model=Envelope[SomePayloadType]`, giving full type safety through the stack. For example:

```python
@router.get("/contacts/{contact_id}", response_model=Envelope[ContactRead])
async def get_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    ...
    return Envelope(data=contact)
```

### Services Layer

| Service | Responsibility |
|---|---|
| `followup_engine` | Two-pool suggestion generator (Pool A: active relationships, Pool B: dormant revival) |
| `identity_resolution` | Tier 1 deterministic + Tier 2 probabilistic duplicate detection and merge |
| `scoring` | Relationship score calculation (0-10 scale) |
| `event_classifier` | LLM-based classification of tweets and bio changes into structured events |
| `message_composer` | Context-aware AI draft generation with tone matching |
| `auto_tagger` | LLM-driven contact tagging with taxonomy management |
| `organization_service` | Company grouping, domain extraction, stats materialized view |
| `contact_search` | Full-text search across contacts |
| `telegram_service` | Higher-level Telegram orchestration with caching |
| `bio_refresh` | Twitter/Telegram bio change detection and tracking |

### Integrations

| Integration | Protocol | Auth |
|---|---|---|
| Gmail | Gmail API (REST) | OAuth 2.0 (per-account tokens via `GoogleAccount` model) |
| Telegram | MTProto via Telethon | Phone number + session string (encrypted at rest) |
| Twitter/X | Bird CLI (primary) + X API v2 (fallback) | Cookie-based (`AUTH_TOKEN` + `CT0`) / OAuth 2.0 PKCE |
| Google Calendar | Calendar API (REST) | Shared OAuth tokens with Gmail |
| LinkedIn | Chrome extension (browser-side scrape) | Extension ID (`CHROME_EXTENSION_ID`); no LinkedIn API key required |

---

## Database Schema

PostgreSQL with UUID primary keys throughout. Key models and their relationships:

```
┌──────────┐     ┌───────────┐     ┌──────────────┐
│   User   │────<│  Contact   │────<│  Interaction  │
│          │     │            │     │  (email/tg/x) │
│          │     │ org_id ──────>┌──┴──────────────┘
│          │     └─────┬──────┘ │
│          │           │        │  ┌──────────────────┐
│          │           ├───────<│  DetectedEvent      │
│          │           │        │  (job_change, etc.) │
│          │           │        └──────────────────────┘
│          │     ┌─────▼──────┐
│          │────<│FollowUp    │
│          │     │Suggestion  │
│          │     └────────────┘
│          │
│          │────<│ Notification │
│          │────<│ GoogleAccount │
└──────────┘
           ┌────────────────┐
           │ IdentityMatch  │  (contact_a_id, contact_b_id, score, status)
           │ ContactMerge   │  (audit trail for merged contacts)
           │ Organization   │  (company records with domain, industry)
           │ TagTaxonomy    │  (hierarchical tag categories)
           └────────────────┘
```

### Key Model Fields

**Contact** -- `full_name`, `emails[]` (PostgreSQL ARRAY with GIN index), `phones[]`, `company`, `organization_id`, `twitter_handle`, `twitter_bio`, `telegram_username`, `telegram_bio`, `linkedin_url`, `relationship_score` (0-10), `interaction_count`, `priority_level` (high/medium/low/archived), `tags[]`, `last_interaction_at`, `last_followup_at`, `birthday`.

**Interaction** -- `contact_id`, `platform` (email/telegram/twitter/linkedin), `direction` (inbound/outbound), `content_preview`, `occurred_at`.

**FollowUpSuggestion** -- `contact_id`, `trigger_type` (time_based/event_based/scheduled/birthday/dormant_*), `suggested_message`, `suggested_channel`, `status` (pending/snoozed/dismissed/completed), `pool` (A/B), `snooze_until`.

**DetectedEvent** -- `contact_id`, `event_type` (job_change/fundraising/product_launch/promotion/milestone/event_attendance), `confidence` (0.0-1.0), `summary`, `source_url`.

### Materialized View

`organization_stats_mv` aggregates per-organization metrics (contact count, total interactions, average score) and is refreshed hourly via a Celery beat task.

### Notable Indexes

- `ix_contacts_emails_gin` -- GIN index on `contacts.emails` for `@>` (array containment) queries
- `ix_contacts_relationship_score` -- B-tree for score-based sorting and filtering
- `ix_contacts_interaction_count` -- B-tree for count-based sorting
- `ix_contacts_full_name` -- B-tree for name search

---

## Task Queue

Celery with Redis as both broker and result backend. Tasks use JSON serialization and run in UTC.

### Beat Schedule

| Task | Schedule | Description |
|---|---|---|
| `sync_gmail_all` | Every 6 hours | Sync email threads for all connected Gmail accounts |
| `sync_google_calendar_all` | Daily 06:00 UTC | Sync calendar events for meeting detection |
| `sync_telegram_all` | Daily 03:00 UTC | Sync Telegram chat history via MTProto |
| `poll_twitter_all` | Daily 04:00 UTC | Poll Twitter activity and bio changes |
| `update_relationship_scores` | Daily 02:00 UTC | Recalculate all contact relationship scores |
| `generate_suggestions_all` | Daily 08:00 UTC | Run follow-up engine for all users |
| `refresh_org_stats` | Hourly (:30) | Refresh `organization_stats_mv` materialized view |
| `reactivate_snoozed_suggestions` | Hourly (:00) | Un-snooze suggestions past their `snooze_until` |
| `send_weekly_digests` | Monday 09:00 UTC | Email weekly networking digest |
| `recheck_telegram_bios` | Every 3 days | Re-check Telegram bios for changes |
| `cleanup_stale_telegram_locks` | Hourly (:15) | Remove stale Telegram rate-limit locks |
| `scan_meeting_preps` | Every 10 minutes | Scan upcoming Calendar meetings and email pre-meeting prep briefs |
| `check_whatsapp_sessions` | Daily 01:00 UTC | Verify WhatsApp sidecar sessions are still connected |

### Task Safety

- Soft time limit: 5 minutes; hard time limit: 10 minutes
- Sync failure tasks (`notify_sync_failure`) create in-app notifications when retries are exhausted
- Each task runs its own async event loop via a `_run()` helper (Celery workers are synchronous)

```python
@shared_task(name="app.services.tasks.sync_gmail_all")
def sync_gmail_all() -> dict:
    return _run(_sync_gmail_all_async())
```

---

## AI Pipeline

All AI features use the Anthropic Claude API.

### Event Classification

Tweets and bio changes are classified into structured event types:

```
Tweet/Bio text
    │
    ▼
┌────────────────────┐     ┌─────────────────────────────┐
│ classify_tweet()   │────>│ JSON response:              │
│ classify_bio_      │     │ { event_type, confidence,   │
│   change()         │     │   summary }                 │
└────────────────────┘     └─────────────┬───────────────┘
                                         │
                                         ▼
                              confidence >= 0.7?
                              ├── yes ──> DetectedEvent record
                              └── no ───> discarded
```

Valid event types: `job_change`, `fundraising`, `product_launch`, `promotion`, `milestone`, `event_attendance`, `none`.

LLM calls are capped at 5 concurrent requests via `asyncio.Semaphore` and use exponential backoff with jitter on transient errors (429, 500, 529).

### Message Composition

The message composer builds context-aware drafts by assembling:

1. **Contact profile** -- name, company, title, bios, relationship score
2. **Conversation history** -- last 5 interactions with direction labels
3. **Tone analysis** -- `analyze_conversation_tone()` classifies past messages as formal/casual based on language indicators
4. **Twitter context** -- recent tweets fetched via bird CLI (cached 12h in Redis) for time-based and revival triggers
5. **Trigger context** -- reason for follow-up (time gap, detected event, birthday, dormant revival)

The prompt instructs the model to produce 2-3 sentences matching the detected tone, referencing the trigger naturally. A template fallback is used if the API call fails.

### Auto-Tagging

LLM-generated tags are managed through a `TagTaxonomy` system with hierarchical categories. Tags can be generated per-contact or applied in bulk via background tasks.

---

## Rate Limiting

### Telegram Rate Gate

Telegram's MTProto API enforces aggressive rate limits via `FloodWaitError`. PingCRM coordinates across all operations using a Redis-based rate gate:

```
┌─────────────────┐     FloodWaitError(seconds=N)
│ Any Telegram    │────────────────┐
│ operation       │                ▼
│ (sync, send,    │     ┌──────────────────────┐
│  bio refresh)   │     │ Redis SET            │
└────────┬────────┘     │ tg_flood:{user_id}   │
         │              │ EX = N seconds       │
         │              └──────────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────────┐
│ _check_rate_    │────>│ Redis TTL            │
│ gate(user_id)   │     │ tg_flood:{user_id}   │
└────────┬────────┘     └──────────────────────┘
         │
    TTL > 0?
    ├── yes ──> skip operation / return error with wait time
    └── no ───> proceed
```

Key behaviors:

- **Cross-operation coordination** -- When any Telegram call triggers `FloodWaitError`, the gate is set for that user. All subsequent operations (sync, send, bio refresh, group member fetch) check the gate before connecting.
- **Skip unchanged dialogs** -- The sync skips dialogs with no new messages since the last sync timestamp, reducing API calls.
- **7-day bio freshness filter** -- Bio refresh skips contacts whose bio was checked within the last 7 days (`telegram_bio_checked_at`).
- **Max contacts per bio sync** -- Capped at 100 contacts per run to stay within rate limits.

### Frontend Rate Limit UX

The `MessageEditor` component detects 429 responses and displays a countdown timer. When a send fails with a rate limit, it parses the `Retry-After` header and shows the remaining wait time to the user.

---

## Identity Resolution

Three tiers of duplicate detection, with a colleague guard to prevent false positives:

```
Contacts
    │
    ▼
┌────────────────────────────────────┐
│ Tier 1: Deterministic              │
│ - Same email in two contacts       │
│ - Same normalized phone number     │
│ - Email found in Twitter bio       │
│                                    │
│ Result: auto-merge immediately     │
└───────────────┬────────────────────┘
                ▼
┌────────────────────────────────────┐
│ Tier 2: Probabilistic (weighted)   │
│                                    │
│ Signal          Base Weight        │
│ ─────────────── ───────────        │
│ Email domain    0.40               │
│ Name similarity 0.20               │
│ Company match   0.20               │
│ Username sim.   0.10               │
│ Mutual signals  0.10               │
│                                    │
│ Adaptive: weights redistribute     │
│ when signals are unavailable       │
│                                    │
│ Score > 0.85  ──> auto-merge       │
│ 0.70 - 0.85  ──> pending review   │
│ Score < 0.70  ──> ignored          │
└───────────────┬────────────────────┘
                ▼
┌────────────────────────────────────┐
│ Tier 3: Manual Review              │
│ - UI presents side-by-side diff    │
│ - User confirms or rejects match   │
└────────────────────────────────────┘
```

### Blocking Keys

To avoid O(n^2) comparisons, contacts are only compared if they share a blocking key:

- Name prefix (first 3 characters)
- Name tokens (words >= 3 characters)
- Company (exact, lowercase)
- Email domain
- Email local part tokens (e.g., `pengcheng.chen@gmail.com` generates tokens `pengcheng`, `chen`)
- Twitter handle, Telegram username, LinkedIn profile ID

Blocks larger than 500 contacts are skipped to prevent degenerate cases (e.g., the `gmail.com` domain block).

### Colleague Guard

When two contacts share both company and email domain but have clearly different names (similarity < 0.5), the score is capped at 0.35 -- below the 0.70 display threshold. This prevents coworkers at the same company from being flagged as duplicates.

Additional guards:
- **Short name penalty** -- Names shorter than 6 characters (e.g., "Alex", "David") without supporting signals get a 0.5x multiplier
- **Name-only cap** -- When name is the sole available signal, the score is capped at 0.85 to force human review

### Merge Behavior

When contacts are merged, the richer contact (by non-null field count) becomes the primary:

- List fields (`emails`, `phones`, `tags`) are unioned with order-preserving, case-insensitive dedup
- Scalar fields are filled from the secondary contact where the primary has nulls
- Interactions are reassigned to the surviving contact
- A `ContactMerge` audit record is created
- An `IdentityMatch` record tracks the merge (secondary's FK becomes NULL after deletion)

---

## Frontend Architecture

### Stack

- **Next.js 15** with App Router (file-based routing under `src/app/`)
- **React 19** with server and client components
- **Tailwind CSS v4** for styling
- **TanStack React Query** for server state management (via `QueryClientProvider` wrapper)
- **openapi-fetch** for a fully typed API client generated from the backend OpenAPI spec

### API Client

The typed client is generated from the backend's OpenAPI schema and uses interceptors for auth:

```typescript
import createClient from "openapi-fetch";
import type { paths } from "./api-types";

const client = createClient<paths>({ baseUrl: "" });

client.use({
  async onRequest({ request }) {
    const token = localStorage.getItem("access_token");
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/auth/login";
    }
    if (response.status >= 500) {
      throw new Error(`API error: ${response.status}`);
    }
    return response;
  },
});
```

### Key Pages

| Route | Component | Purpose |
|---|---|---|
| `/dashboard` | `DashboardPage` | Overview with stats, recent activity, suggestions |
| `/contacts` | `ContactsPage` | Contact list with search, filters, CSV import |
| `/contacts/[id]` | `ContactDetailPage` | Full contact profile with interaction timeline |
| `/suggestions` | `SuggestionsPage` | Follow-up suggestions with inline message composer |
| `/identity` | `IdentityPage` | Duplicate review queue |
| `/organizations` | `OrganizationsPage` | Company directory with aggregated stats |
| `/notifications` | `NotificationsPage` | In-app notification feed |
| `/settings` | `SettingsPage` | Account connections, sync preferences |
| `/onboarding` | `OnboardingPage` | Initial setup flow |

### Error Handling

A class-based error boundary (`error.tsx`, `global-error.tsx`) wraps the application. React requires `componentDidCatch` to be a class method, so this cannot be a function component. The boundary provides recovery options and logs errors for debugging.

### Custom Hooks

| Hook | Purpose |
|---|---|
| `useAuth` | JWT token management, login/logout, user state |
| `useContacts` | Contact CRUD with React Query mutations |
| `useSuggestions` | Follow-up suggestion fetching and actions |
| `useDashboard` | Dashboard stats and activity data |
| `useNotifications` | Notification feed with unread count |
| `useIdentity` | Identity match review and resolution |
| `useTelegramSync` | Monitor Telegram sync progress |
