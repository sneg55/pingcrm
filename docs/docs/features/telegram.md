---
sidebar_position: 9
title: Telegram Integration
---

# Telegram Integration

Ping CRM connects to Telegram using the MTProto protocol via the Telethon library, providing access to DMs, group memberships, and user bios.

## Authentication

The Telegram auth flow has three steps:

1. **Phone number** -- enter your phone number (with country code).
2. **OTP** -- enter the one-time code delivered to your Telegram app.
3. **2FA password** -- if two-factor authentication is enabled on your account, enter your cloud password.

Once authenticated, the session is persisted so you do not need to re-authenticate on each sync.

## Chat Sync

Chat sync imports direct messages as interactions. To minimize API usage, the sync skips dialogs that have not changed since the last sync, reducing API calls by approximately 80%.

**Schedule:** Daily at 03:00 UTC.

## Group Member Sync

Ping CRM discovers contacts from Telegram groups you share with other users. Members found through group sync are tagged as **"2nd Tier"** to distinguish them from direct conversation contacts.

## Bio Sync

User bios are periodically checked for changes. A 7-day freshness filter skips users whose bios were fetched recently, cutting API calls by approximately 70%. Bio changes can indicate job transitions or new ventures and are surfaced through the notification system.

## Common Groups

For each contact, Ping CRM identifies Telegram groups you both belong to. This data is cached for 24 hours and displayed in the contact sidebar as shared context.

## Rate Limiting

Telegram enforces strict rate limits (FloodWait errors). Ping CRM handles this with a coordinated rate gate:

- A Redis key `tg_flood:{user_id}` tracks active cooldowns with a TTL.
- FloodWait coordination spans all Telegram operations (chat sync, bio sync, group sync) so that one operation's cooldown is respected by all others.
- The send-message endpoint returns HTTP **429** with a `Retry-After` header when a cooldown is active. The frontend displays a countdown timer until the operation can be retried.
