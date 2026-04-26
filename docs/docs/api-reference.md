---
sidebar_position: 20
title: API Reference
---

# API Reference

All endpoints are prefixed with `/api/v1` (except `/api/health`). Every response uses a standard envelope:

```json
{
  "data": {},
  "error": null,
  "meta": {}
}
```

All endpoints require authentication via Bearer token, except registration, login, OAuth URL generation, the extension pairing poll, error reporting, and the WhatsApp webhook.

> This reference is generated from the live FastAPI OpenAPI schema. The CI guard `backend/scripts/check_api_doc.py` fails the pre-push hook if the schema and this page drift. To regenerate locally, run the OpenAPI export described in `CLAUDE.md` and rerun the guard.

---

## Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register a new account with email and password |
| POST | `/api/v1/auth/login` | Login with email and password |
| GET | `/api/v1/auth/me` | Current authenticated user |
| PUT | `/api/v1/auth/me` | Update profile fields |
| DELETE | `/api/v1/auth/me` | Delete the authenticated account |
| POST | `/api/v1/auth/change-password` | Change account password |
| GET | `/api/v1/auth/google/url` | Google OAuth authorization URL |
| POST | `/api/v1/auth/google/callback` | Google OAuth callback handler |
| GET | `/api/v1/auth/google/accounts` | List connected Google accounts |
| DELETE | `/api/v1/auth/google/accounts/{account_id}` | Remove a connected Google account |
| GET | `/api/v1/auth/twitter/url` | Twitter OAuth authorization URL |
| POST | `/api/v1/auth/twitter/callback` | Twitter OAuth callback handler |
| DELETE | `/api/v1/auth/twitter/disconnect` | Disconnect Twitter |
| POST | `/api/v1/auth/telegram/connect` | Send OTP code to Telegram |
| POST | `/api/v1/auth/telegram/verify` | Verify the Telegram OTP code |
| POST | `/api/v1/auth/telegram/verify-2fa` | Submit Telegram 2FA password |
| POST | `/api/v1/auth/telegram/reset-session` | Wipe an existing Telegram session |
| DELETE | `/api/v1/auth/telegram/disconnect` | Disconnect Telegram |
| POST | `/api/v1/auth/whatsapp/connect` | Start a WhatsApp link-device flow |
| GET | `/api/v1/auth/whatsapp/qr` | Fetch the current WhatsApp QR payload |
| GET | `/api/v1/auth/whatsapp/status` | WhatsApp session status |
| DELETE | `/api/v1/auth/whatsapp/disconnect` | Tear down the WhatsApp session |

---

## Contacts

### CRUD and listing

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/contacts` | List contacts (paginated, searchable, filterable) |
| POST | `/api/v1/contacts` | Create a new contact |
| GET | `/api/v1/contacts/ids` | Bulk contact IDs for select-all |
| GET | `/api/v1/contacts/stats` | Dashboard contact stats |
| GET | `/api/v1/contacts/birthdays` | Upcoming birthdays |
| GET | `/api/v1/contacts/overdue` | Overdue follow-up contacts |
| GET | `/api/v1/contacts/map` | Contacts within a viewport (`bbox` query) |
| POST | `/api/v1/contacts/bulk-update` | Bulk update tags, priority, and other fields |
| POST | `/api/v1/contacts/reconcile-last-interaction` | Recompute `last_interaction_at` for all contacts |
| POST | `/api/v1/contacts/scores/recalculate` | Trigger relationship-score recompute |
| GET | `/api/v1/contacts/{contact_id}` | Get a contact |
| PUT | `/api/v1/contacts/{contact_id}` | Update a contact |
| DELETE | `/api/v1/contacts/{contact_id}` | Delete a contact |
| GET | `/api/v1/contacts/{contact_id}/activity` | Activity feed for a contact |
| GET | `/api/v1/contacts/{contact_id}/related` | Related contacts (same org, etc.) |
| GET | `/api/v1/contacts/{contact_id}/duplicates` | Duplicate candidates for a contact |

### 2nd-tier (Telegram group members)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/contacts/2nd-tier/count` | Count of 2nd-tier contacts |
| DELETE | `/api/v1/contacts/2nd-tier` | Delete all 2nd-tier contacts |
| POST | `/api/v1/contacts/{contact_id}/promote` | Promote 2nd-tier contact to 1st-tier |

### Enrichment, AI, messaging

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/contacts/{contact_id}/enrich` | Enrich via Apollo |
| POST | `/api/v1/contacts/{contact_id}/extract-bio` | AI-extract structured fields from bios |
| POST | `/api/v1/contacts/{contact_id}/auto-tag` | Apply AI taxonomy tags to one contact |
| POST | `/api/v1/contacts/{contact_id}/refresh-avatar` | Re-download avatar from connected platforms |
| POST | `/api/v1/contacts/{contact_id}/refresh-bios` | Re-fetch Twitter/Telegram bios |
| POST | `/api/v1/contacts/{contact_id}/compose` | Generate an AI-drafted message |
| POST | `/api/v1/contacts/{contact_id}/send-message` | Send a message via channel (email, Telegram, Twitter, LinkedIn) |

### Identity / merging

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/contacts/{contact_id}/merge/{other_id}` | Merge two contacts directly |
| POST | `/api/v1/contacts/{contact_id}/dismiss-duplicate/{other_id}` | Dismiss a duplicate hint |

### Imports

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/contacts/import/csv` | Import from a CSV file |
| POST | `/api/v1/contacts/import/linkedin` | Import a LinkedIn `Connections.csv` export |
| POST | `/api/v1/contacts/import/linkedin-messages` | Import a LinkedIn message export |

### Per-contact background syncs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/contacts/{contact_id}/sync-emails` | Sync Gmail thread for a single contact |
| POST | `/api/v1/contacts/{contact_id}/sync-telegram` | Sync Telegram DM for a single contact |
| POST | `/api/v1/contacts/{contact_id}/sync-twitter` | Sync Twitter DM for a single contact |
| GET | `/api/v1/contacts/{contact_id}/telegram/common-groups` | Telegram groups shared with a contact |

### Account-wide background syncs

All return immediately; a notification fires when the task completes.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/contacts/sync/gmail` | Sync Gmail email threads |
| POST | `/api/v1/contacts/sync/google` | Import from Google Contacts |
| POST | `/api/v1/contacts/sync/google-calendar` | Sync Google Calendar events |
| POST | `/api/v1/contacts/sync/telegram` | Sync Telegram chats, groups, and bios |
| POST | `/api/v1/contacts/sync/twitter` | Sync Twitter DMs and mentions |
| POST | `/api/v1/contacts/sync/whatsapp` | Backfill WhatsApp messages |
| GET | `/api/v1/telegram/sync-progress` | Poll Telegram sync progress |

### Tag taxonomy

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/contacts/tags` | Flat list of in-use tags |
| GET | `/api/v1/contacts/tags/taxonomy` | Tag taxonomy structure |
| PUT | `/api/v1/contacts/tags/taxonomy` | Update taxonomy |
| POST | `/api/v1/contacts/tags/discover` | LLM-discover a draft taxonomy |
| POST | `/api/v1/contacts/tags/apply` | Apply taxonomy to contacts |

### Interactions (timeline)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/contacts/{contact_id}/interactions` | List interactions |
| POST | `/api/v1/contacts/{contact_id}/interactions` | Add a manual note |
| PATCH | `/api/v1/contacts/{contact_id}/interactions/{interaction_id}` | Update a note |
| DELETE | `/api/v1/contacts/{contact_id}/interactions/{interaction_id}` | Delete a note |

---

## Suggestions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/suggestions` | List follow-up suggestions |
| GET | `/api/v1/suggestions/digest` | Weekly digest of suggestions |
| POST | `/api/v1/suggestions/generate` | Generate new follow-up suggestions |
| PUT | `/api/v1/suggestions/{suggestion_id}` | Update suggestion status (snooze, dismiss, send) |
| POST | `/api/v1/suggestions/{suggestion_id}/regenerate` | Regenerate the AI-drafted message |

---

## Identity Resolution

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/identity/matches` | List pending identity matches |
| POST | `/api/v1/identity/scan` | Trigger an identity resolution scan |
| POST | `/api/v1/identity/matches/{match_id}/merge` | Confirm merge for a pair |
| POST | `/api/v1/identity/matches/{match_id}/reject` | Reject a match |

---

## Organizations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/organizations` | List organizations (excludes those with zero active contacts) |
| POST | `/api/v1/organizations` | Create an organization |
| POST | `/api/v1/organizations/merge` | Merge two or more organizations |
| POST | `/api/v1/organizations/backfill-logos` | Backfill favicon-derived logos for orgs missing one |
| GET | `/api/v1/organizations/{org_id}` | Get organization detail |
| PATCH | `/api/v1/organizations/{org_id}` | Update an organization |
| DELETE | `/api/v1/organizations/{org_id}` | Delete an organization |
| GET | `/api/v1/organizations/{org_id}/stats` | Per-organization stats from the materialized view |
| POST | `/api/v1/organizations/{org_id}/refresh-logo` | Re-fetch favicon for the org |

---

## Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/notifications` | List notifications |
| GET | `/api/v1/notifications/unread-count` | Unread count |
| PUT | `/api/v1/notifications/{notification_id}/read` | Mark a notification read |
| PUT | `/api/v1/notifications/read-all` | Mark all read |

---

## Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/settings/priority` | Follow-up intervals (high, medium, low) |
| PUT | `/api/v1/settings/priority` | Update follow-up intervals (7-365 days) |
| GET | `/api/v1/settings/sync` | Sync schedule preferences |
| PUT | `/api/v1/settings/sync` | Update sync schedule preferences |
| GET | `/api/v1/settings/telegram` | Telegram-specific settings (e.g., 2nd-tier toggle) |
| PUT | `/api/v1/settings/telegram` | Update Telegram settings |
| GET | `/api/v1/settings/suggestions` | Suggestion engine prefs |
| PUT | `/api/v1/settings/suggestions` | Update suggestion engine prefs |
| GET | `/api/v1/settings/mcp-key` | MCP API key status |
| POST | `/api/v1/settings/mcp-key` | Generate a new MCP API key (shown once) |
| DELETE | `/api/v1/settings/mcp-key` | Revoke the MCP API key |

---

## Activity

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/activity/recent` | Recent interactions (last 7 days, deduped per contact) |

---

## Sync History

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/sync-history` | Recent sync events with record counts |
| GET | `/api/v1/sync-history/stats` | Aggregate stats per platform |

---

## Map

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/map/config` | Public Mapbox token for the browser |

See also `GET /api/v1/contacts/map` above for the viewport query.

---

## LinkedIn (Chrome extension push)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/linkedin/push` | Push profiles and messages from the extension |

---

## Twitter (per-user cookies)

The Chrome extension uses these endpoints to keep per-user X cookies fresh; they are not called by the web app.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/integrations/twitter/cookies` | Status of stored cookies for the user |
| POST | `/api/v1/integrations/twitter/cookies` | Push fresh cookies (encrypted at rest) |
| DELETE | `/api/v1/integrations/twitter/cookies` | Clear stored cookies |

---

## Meta (Messenger / Instagram)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/meta/push` | Push Messenger / Instagram DM data from the extension |

---

## Extension Pairing

The pairing poll is unauthenticated; everything else requires the extension JWT.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/extension/pair` | Submit a pairing code from the extension popup |
| GET | `/api/v1/extension/pair` | Poll for token (unauthenticated, used by extension) |
| DELETE | `/api/v1/extension/pair` | Disconnect the extension |
| POST | `/api/v1/extension/refresh` | Silent token refresh (extension exchanges expiring JWT for a fresh 30-day one) |

---

## Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/webhooks/whatsapp` | WhatsApp sidecar webhook (HMAC-signed) |

---

## Diagnostics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Liveness probe |
| POST | `/api/v1/errors` | Frontend error reporting |
