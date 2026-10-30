---
sidebar_position: 9
title: Telegram Integration
description: "PingCRM connects to Telegram via the MTProto protocol (Telethon) to sync DMs, group memberships, and user bios into your contact timeline."
---

# Telegram Integration

PingCRM connects to Telegram over the MTProto protocol using the Telethon library. It reads your DMs, group memberships, and user bios.

![Telegram section in Settings](/img/screenshots/telegram/settings-section.png)

## Authentication

The Telegram auth flow has three steps:

1. **Phone number:** enter your phone number with country code.
2. **OTP:** enter the one-time code sent to your Telegram app.
3. **2FA password:** if two-step authentication is on for your account, enter your cloud password.

The session is saved after you authenticate, so syncs do not ask you to sign in again.

## What Gets Synced

| Data | Source | Frequency |
|------|--------|-----------|
| Direct messages | DM dialogs | Daily (03:00 UTC) + manual |
| Contact info | DM participants | During chat sync |
| Group members | Private groups / supergroups | First sync only; on-demand thereafter |
| User bios | Telegram "about" field | Periodic recheck on days 1, 4, 7, ... 28 of each month (3-day staleness); the first-sync bio step uses a 7-day staleness filter |
| Usernames | All synced users | During chat / group sync |
| Phone/video calls | DM call events | During chat sync (call_type + duration recorded) |
| Common groups | Shared group memberships | Cached 24 hours |

## Chat Sync

Chat sync imports direct messages as interactions.

### Schedule
- **Automatic:** Daily at 03:00 UTC via Celery beat.
- **Manual:** Trigger from Settings > Integrations > Telegram > "Sync now".

### How it works
1. Fetches your Telegram dialogs (conversations).
2. Skips dialogs whose latest message is already stored, which cuts API calls.
3. For each dialog with new messages, imports messages as interactions linked to the matching contact.

![Telegram messages with read-receipt indicators in the timeline](/img/screenshots/telegram/timeline-readreceipts.png)

### First sync vs incremental
- **First sync:** processes all dialogs in batches of 50 to stay within rate limits. Group and bio sync also run as part of the first-sync chain.
- **Incremental sync:** processes only the 100 most recent dialogs. Group member sync and bio sync run on their own (on demand or on their periodic schedule) and are not part of the daily chain.

### Contact resolution
For each DM participant, PingCRM tries to match an existing contact by:
1. `telegram_user_id` (numeric Telegram ID, the most reliable because it survives username changes)
2. `telegram_username` (@ handle)
3. Phone number

If no match is found, a new contact is created with `source: "telegram"`.

## Group Member Sync

Group member sync finds people in Telegram groups you share with them and creates **2nd Tier contacts** (see [2nd Tier Contacts](#2nd-tier-contacts) below).

### How it works
1. Iterates through your Telegram dialogs, filtering for private groups and supergroups only.
2. Public groups (those with a username/invite link) are skipped.
3. For each group, fetches up to 200 members.
4. Bots are excluded.
5. New members are created as contacts tagged **"2nd Tier"**.
6. Existing contacts that appear as members are checked for interactions. Those with none get the "2nd Tier" tag, and those with any have it removed.
7. Group sync is skipped when `sync_2nd_tier` is off or a FloodWait cooldown is active.

### Limits
- Maximum 20 groups scanned per sync.
- Maximum 200 members per group.

## 2nd Tier Contacts

### Definition
A **2nd Tier contact** is someone you found through a shared Telegram group and have never messaged directly. They carry the `"2nd Tier"` tag, which separates them from direct conversation contacts (1st Tier).

### Behavior
- Created during group member sync from private groups and supergroups.
- Promoted to 1st Tier automatically when the contact gains a direct interaction (DM, email, and so on). The tag is removed.
- Left out of follow-up suggestions, so they do not appear in your follow-up queue.
- Left out of AI auto-tagging, so taxonomy tags are not applied to them.
- Left out of the periodic bio recheck, which saves API calls.

### Configuring 2nd Tier sync
You can control 2nd Tier contact sync from **Settings > Integrations > Telegram**:

- **Import 2nd Tier contacts toggle** (`sync_2nd_tier`): when off, group syncs create no new 2nd Tier contacts.
- **Delete all:** removes every existing 2nd Tier contact at once.
- **Promote to 1st Tier:** on a 2nd Tier contact's detail page, this action removes the tag.

Turning the toggle off does not delete existing 2nd Tier contacts. Use "Delete all" for that.

## Bio Sync

PingCRM periodically checks user bios (the "about" field in Telegram profiles) for changes.

### Freshness filter
Bio sync skips contacts whose bio was checked within the staleness window, based on each contact's `telegram_bio_checked_at` timestamp (set only by bio sync). The window is 7 days for the first-sync bio step and 3 days for the periodic recheck.

### Periodic recheck
A background task (`recheck_telegram_bios_all`) runs at 05:00 UTC on days 1, 4, 7, 10, 13, 16, 19, 22, 25, and 28 of each month. It rechecks bios for non-2nd-Tier contacts whose `telegram_bio_checked_at` is older than 3 days or null.

### Bio change detection
A changed bio can signal a job change or a new venture, so PingCRM creates a notification when it detects one.

## Common Groups

For each contact, PingCRM identifies Telegram groups you both belong to.

- Results are cached for 24 hours per contact.
- The contact detail page shows them in the Common Telegram Groups card.
- You can force a refresh from the contact detail page.

![Common Telegram groups sidebar on the contact detail page](/img/screenshots/telegram/common-groups.png)

## Sync Chain Architecture

The chain differs between the first sync and incremental syncs.

### First sync
When `telegram_last_synced_at` is null (account never synced before):

```
Chat batches (all dialogs, 50 per batch) → Group members → Bios → Notify (release lock)
```

### Incremental sync (daily)
Later daily syncs process only messages in the chain. Group member sync and bio sync run separately, on their own schedules or on demand.

```
Chats (100 most recent dialogs) → Notify (release lock)
```

A sync lock prevents concurrent syncs for the same user. The lock has a 1-hour TTL and is cleaned up by an hourly watchdog task.

## Rate Limiting

Telegram enforces strict rate limits through FloodWait errors.

### How PingCRM handles rate limits
- A Redis key `tg_flood:{user_id}` tracks active cooldowns with a TTL.
- One cooldown covers all Telegram operations (chat sync, bio sync, group sync, sending), so every operation respects a cooldown set by any other.
- The send-message endpoint returns HTTP **429** with a `Retry-After` header while a cooldown is active, and creates a "Telegram rate limit" notification.

### Sync lock
- A Redis-based lock (`tg_sync_lock:{user_id}`) prevents overlapping syncs.
- The lock TTL is 1 hour.
- An hourly watchdog task (`cleanup_stale_telegram_locks`) removes stale locks left by crashed workers.
- A Lua compare-and-delete script lets only the lock owner release it.
