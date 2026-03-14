---
sidebar_position: 20
title: API Reference
---

# API Reference

All endpoints are prefixed with `/api/v1`. Every response uses a standard envelope:

```json
{
  "data": {},
  "error": null,
  "meta": {}
}
```

All endpoints except registration, login, and OAuth URL generation require authentication via Bearer token.

---

## Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register a new account with email and password |
| POST | `/api/v1/auth/login` | Login with email and password |
| GET | `/api/v1/auth/me` | Get the current authenticated user |
| GET | `/api/v1/auth/google/url` | Get the Google OAuth authorization URL |
| POST | `/api/v1/auth/google/callback` | Handle Google OAuth callback |
| GET | `/api/v1/auth/google/accounts` | List connected Google accounts |
| DELETE | `/api/v1/auth/google/accounts/{id}` | Remove a connected Google account |
| GET | `/api/v1/auth/twitter/url` | Get the Twitter OAuth authorization URL |
| POST | `/api/v1/auth/twitter/callback` | Handle Twitter OAuth callback |

---

## Contacts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/contacts` | List contacts (paginated, searchable, filterable) |
| POST | `/api/v1/contacts` | Create a new contact |
| GET | `/api/v1/contacts/tags` | Get all unique tags across contacts |
| GET | `/api/v1/contacts/stats` | Get dashboard statistics |
| GET | `/api/v1/contacts/{id}` | Get contact detail |
| PUT | `/api/v1/contacts/{id}` | Update a contact |
| DELETE | `/api/v1/contacts/{id}` | Delete a contact |
| GET | `/api/v1/contacts/{id}/duplicates` | Find potential duplicate contacts |
| POST | `/api/v1/contacts/{id}/merge/{other_id}` | Merge two contacts |
| POST | `/api/v1/contacts/{id}/refresh-bios` | Refresh social bios for a contact |
| POST | `/api/v1/contacts/{id}/send-message` | Send a message to a contact (returns 429 on rate limit) |
| POST | `/api/v1/contacts/import/csv` | Import contacts from a CSV file |
| POST | `/api/v1/contacts/scores/recalculate` | Recalculate relationship scores for all contacts |

---

## Sync (Background Tasks)

All sync endpoints return immediately. A notification is created upon completion.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/contacts/sync/google` | Sync Google Contacts |
| POST | `/api/v1/contacts/sync/google-calendar` | Sync Google Calendar events |
| POST | `/api/v1/contacts/sync/telegram` | Sync Telegram chats, groups, and bios |
| POST | `/api/v1/contacts/sync/twitter` | Sync Twitter DMs, mentions, and bios |

---

## Telegram Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/telegram/connect` | Send OTP code to Telegram |
| POST | `/api/v1/auth/telegram/verify` | Verify the Telegram OTP code |
| POST | `/api/v1/auth/telegram/verify-2fa` | Submit Telegram 2FA password |
| GET | `/api/v1/contacts/{id}/telegram/common-groups` | Get shared Telegram groups with a contact |

---

## Interactions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/contacts/{id}/interactions` | Get interaction timeline for a contact |
| POST | `/api/v1/contacts/{id}/interactions` | Add a note interaction for a contact |

---

## Suggestions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/suggestions` | List follow-up suggestions |
| PUT | `/api/v1/suggestions/{id}` | Update suggestion status |
| POST | `/api/v1/suggestions/generate` | Generate new follow-up suggestions |
| POST | `/api/v1/suggestions/{id}/regenerate` | Regenerate the AI-drafted message for a suggestion |

---

## Identity Resolution

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/identity/matches` | List potential identity matches |
| POST | `/api/v1/identity/scan` | Trigger an identity resolution scan |
| POST | `/api/v1/identity/matches/{id}/merge` | Merge a matched identity pair |
| POST | `/api/v1/identity/matches/{id}/reject` | Reject a matched identity pair |

---

## Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/notifications` | List notifications |
| GET | `/api/v1/notifications/unread-count` | Get unread notification count |
| PUT | `/api/v1/notifications/{id}/read` | Mark a notification as read |
| PUT | `/api/v1/notifications/read-all` | Mark all notifications as read |

---

## Organizations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/organizations` | List organizations (excludes those with zero active contacts) |
| POST | `/api/v1/organizations/merge` | Merge two or more organizations |
| GET | `/api/v1/organizations/{id}` | Get organization detail |
| PATCH | `/api/v1/organizations/{id}` | Update an organization |
| DELETE | `/api/v1/organizations/{id}` | Delete an organization |
