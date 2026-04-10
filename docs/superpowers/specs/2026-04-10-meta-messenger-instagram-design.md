# Meta Integration: Facebook Messenger & Instagram DMs

**Date:** 2026-04-10
**Status:** Approved

## Overview

Cookie-based integration for syncing Facebook Messenger conversations and Instagram DMs into PingCRM. Uses the existing Chrome extension (extended from LinkedIn) to capture Meta session cookies and execute same-origin GraphQL requests. Raw data is pushed to the backend for processing — cookies never leave the browser.

## Architecture

### Approach: Hybrid (Cookie Proxy + Backend Processing)

The Chrome extension fetches raw conversation data via Meta's internal GraphQL API using same-origin requests in Facebook/Instagram tabs. Raw responses are pushed to the backend, which handles normalization, contact resolution, dedup, and interaction creation.

This mirrors the existing LinkedIn integration pattern: Voyager calls happen in-browser, parsed data gets pushed to `/api/v1/linkedin/push`.

## Chrome Extension Changes

### Manifest Updates

- **Host permissions:** Add `https://www.facebook.com/*` and `https://www.instagram.com/*`
- **Content scripts:** Add `meta-notify.js` for both `facebook.com` and `instagram.com` domains

### New Modules

| Module | Purpose |
|---|---|
| `meta-client.js` | Same-origin fetch proxy for Meta GraphQL API. Executes in Facebook/Instagram tabs via `chrome.scripting.executeScript()`. Extracts `fb_dtsg` CSRF token from page HTML/DOM. |
| `sync-facebook.js` | Orchestrates Messenger sync. Fetches conversations via `/api/graphql/`, extracts messages, reactions, read receipts. Watermark-based delta sync. |
| `sync-instagram.js` | Orchestrates Instagram DM sync. Same GraphQL endpoint family, different query `doc_id` hashes. Separate watermark. |
| `meta-notify.js` | Content script for `facebook.com` and `instagram.com`. Broadcasts page visit events (`META_PAGE_VISIT`), acts as same-origin request proxy. |

### Cookie Detection

- **Facebook:** `c_user` + `xs` cookies on `.facebook.com`
- **Instagram:** Shares the same Meta session. If Facebook cookies are present, Instagram works too.

### Throttling & Rate Limiting

- 15-minute sync throttle per platform (independent timers)
- 1-second delay between GraphQL calls (sequential, never parallel)
- Exponential backoff on rate-limit/error responses, capped at 15 minutes
- Stored as `metaNextRetryAt` in `chrome.storage.local`

### Fetch Limits (Lockout Mitigation)

- Max 50 conversations per sync cycle
- Max 100 messages per conversation
- Sync only on page visit (throttled) or manual trigger — no background timer

## Meta Internal API Endpoints

Meta uses a single GraphQL endpoint (`/api/graphql/`) for both Messenger and Instagram DMs. All requests are POST with form-encoded body:

- `fb_dtsg` — CSRF token extracted from page HTML
- `doc_id` — query hash identifying the operation
- `variables` — JSON-encoded parameters

### Messenger (Facebook)

| Operation | Query | Returns |
|---|---|---|
| List conversations | `LSPlatformGraphQLLightspeedRequestQuery` | Threads with participants, last message, unread count |
| Fetch messages | Thread messages query | Message nodes: `text`, `timestamp`, `message_sender`, `message_reactions` |
| Read receipts | Included in message metadata | `read_receipt` field per participant |

### Instagram DMs

| Operation | Query | Returns |
|---|---|---|
| List threads | `IGDInboxQuery` | DM threads with participants |
| Fetch messages | Thread detail query | `text`, `timestamp`, `sender`, `reactions`, `seen_by` |

### Differences from LinkedIn Voyager

- **Auth:** `fb_dtsg` token instead of CSRF header
- **Pagination:** Cursor-based (`end_cursor` / `has_next_page`) instead of timestamp-based
- **Rate limiting:** Meta is less aggressive than LinkedIn — no known hard 429 pattern, but defensive backoff implemented

### Extracted Fields Per Message

- `message_id` — dedup key (`mid.*` format, shared across Messenger and Instagram)
- `sender_id` + `sender_name`
- `text` — truncated to `content_preview`
- `timestamp`
- `direction` — inbound/outbound based on matching sender to `c_user`
- `reactions` — list of `{reactor_id, reaction_type}`
- `read_by` — list of user IDs who've seen the message

## Backend

### Push Endpoint: `POST /api/v1/meta/push`

Single endpoint for both Facebook Messenger and Instagram DMs. Route file: `backend/app/api/meta.py`.

**Request body:**

```json
{
  "platform": "facebook" | "instagram",
  "profiles": [
    {
      "platform_id": "100012345",
      "name": "Jane Doe",
      "username": "janedoe",
      "avatar_url": "https://..."
    }
  ],
  "messages": [
    {
      "message_id": "mid.xxx",
      "conversation_id": "conv_123",
      "platform_id": "100012345",
      "sender_name": "Jane Doe",
      "direction": "inbound",
      "content_preview": "Hey, are you coming to...",
      "timestamp": "2026-04-09T14:30:00Z",
      "reactions": [{"reactor_id": "100099", "type": "love"}],
      "read_by": ["100012345", "100099"]
    }
  ]
}
```

**Processing (mirrors LinkedIn push pattern):**

1. Pre-load user's Facebook/Instagram contacts into memory (by `platform_id`)
2. Pre-load existing interaction `raw_reference_id` set for dedup
3. Upsert contacts from profiles
4. Create interactions from messages — store reactions and read receipts as JSON in `metadata` field on Interaction
5. Update `last_interaction_at`, increment `interaction_count`
6. Auto-dismiss pending suggestions for contacts with new interactions
7. Return `contacts_created`, `contacts_updated`, `interactions_created`, `backfill_needed` (contacts missing avatar URLs)

**Response:**

```json
{
  "data": {
    "contacts_created": 5,
    "contacts_updated": 12,
    "interactions_created": 47,
    "backfill_needed": [
      {"contact_id": "uuid", "platform_id": "100012345", "platform": "facebook"}
    ]
  }
}
```

## Data Model Changes

### Contact Model — New Fields

| Field | Type | Purpose |
|---|---|---|
| `facebook_id` | `str` | Meta user ID (numeric string) |
| `facebook_name` | `str` | Display name from Messenger |
| `facebook_avatar_url` | `str` | Profile picture URL |
| `instagram_id` | `str` | Instagram user ID (different from Facebook ID) |
| `instagram_username` | `str` | Instagram handle |
| `instagram_avatar_url` | `str` | Profile picture URL |

No `facebook_username` — Facebook deprecated public usernames for most users.

### Interaction Model — New Column

| Field | Type | Purpose |
|---|---|---|
| `metadata` | `JSON` (nullable) | Reactions, read receipts. Generic — usable by other platforms later. |

Example value:
```json
{
  "reactions": [{"reactor_id": "100099", "type": "love"}],
  "read_by": ["100012345", "100099"]
}
```

### User Model — New Fields

| Field | Type | Purpose |
|---|---|---|
| `meta_connected` | `bool` | Whether Meta cookies are active (set on first push) |
| `meta_connected_name` | `str` | Display name of connected Facebook account |
| `meta_sync_facebook` | `bool` (default true) | Toggle Messenger sync |
| `meta_sync_instagram` | `bool` (default true) | Toggle Instagram DM sync |

No token fields on User — cookies stay in the browser extension, never sent to backend.

### Migration

Single Alembic migration adding all columns to contacts, interactions, and users tables.

## Frontend

### Meta Card (`meta-card.tsx`)

Single "Meta" card in settings integrations tab.

**States:**

| State | Display |
|---|---|
| Disconnected | "Connect Meta" button. Instructions: install extension, visit facebook.com. |
| Connected | Facebook name, toggles for "Sync Messenger" / "Sync Instagram DMs", Sync button, last sync timestamps. |
| Syncing | Spinner with progress. |

**Sync trigger:** Extension-initiated only (no backend Celery task — backend has no cookies). User clicks "Sync" in PingCRM, frontend relays to extension via `window.postMessage` / content script, extension runs sync and pushes to backend.

**Auto-sync:** Triggers on `facebook.com` / `instagram.com` page visits (15-minute throttle).

### Interaction Display

- Messenger messages: Facebook Messenger icon in contact timeline
- Instagram DMs: Instagram icon in contact timeline
- Reactions: small emoji badges on interaction rows (if present)
- Read receipts: subtle "seen" indicator

## Contact Resolution & Dedup

### Matching Strategy

1. **Primary match:** `facebook_id` or `instagram_id` exact match on existing contacts
2. **Cross-platform fuzzy match:** Name-based matching against existing contacts (same algorithm as LinkedIn/WhatsApp). High confidence = merge platform fields onto existing contact. Ambiguous = create new contact (user merges manually).
3. **No automatic Facebook-Instagram cross-linking.** User IDs differ between platforms. Fuzzy name matcher may link them to the same contact, but no Meta-specific logic.

### Message Dedup

- `raw_reference_id` = `message_id` (`mid.*` format)
- Cross-app messages (Messenger message appearing in Instagram) deduped by shared `mid.*` format

### Manual Merge

Already exists in the UI. No changes needed.

## Error Handling

### Cookie Expiration

Meta sessions expire or get invalidated (password change, suspicious login). Extension detects auth errors from GraphQL, sets `meta_connected: false` via backend status endpoint. Frontend shows "Reconnect needed — visit facebook.com while extension is active."

### Account Lockout Risk

Mitigated by:
- Conservative fetch limits (50 conversations, 100 messages)
- Sequential requests only (no parallelism)
- No background polling timer — sync on page visit or manual click only

### Missing Data

Deactivated/deleted accounts: `platform_id` still works for dedup, name may be "Facebook User". Store whatever Meta returns.

### Extension Not Installed

Frontend shows "Extension not detected" after 3-second timeout on postMessage relay if extension doesn't respond.

### Dual-Platform Dedup

Messages sent via Messenger that also appear in Instagram (cross-app messaging) deduped by `message_id` — Meta uses the same `mid.*` format across both.

## Out of Scope

- Facebook profile/bio enrichment (future enhancement)
- Facebook friends list import (API deprecated)
- Facebook/Instagram posts, comments, stories
- Instagram Reels interactions
- WhatsApp integration via Meta (separate existing integration)
- Autonomous message sending (PingCRM is AI-drafts-only)
