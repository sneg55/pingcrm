---
sidebar_position: 10
title: Twitter/X Integration
description: "PingCRM connects to Twitter/X via OAuth 2.0 PKCE to sync DMs, mentions, and profiles into each contact's unified interaction timeline."
---

# Twitter / X Integration

PingCRM connects to Twitter (X) with OAuth 2.0 and PKCE for DMs, and with the `bird` CLI and your browser cookies for mentions, replies, and profiles.

## Authentication

Twitter uses the OAuth 2.0 Authorization Code flow with PKCE (Proof Key for Code Exchange). A client secret is optional: PingCRM sends `TWITTER_CLIENT_SECRET` only when you set it. After authorization, PingCRM stores a refresh token to keep access.

## Connecting your X account (bird CLI)

Mention, reply, and bio sync require the PingCRM Chrome extension. OAuth only covers DMs; the rest uses the `bird` CLI with your X browser cookies.

After installing the extension, open **Settings → Integrations**, find the Twitter card, and click **Connect X** on the X row. The extension reads your `x.com` cookies in the browser and sends them to PingCRM, which stores them encrypted at rest with Fernet.

Cookies refresh automatically whenever X rotates them, as long as you stay signed in to x.com in the same browser: the extension listens for cookie changes and pushes the new values silently. If you sign out of X or clear cookies, the row shows **X cookies expired** with a **Refresh** button. Click it and sign back in to x.com if prompted to reconnect.

![Twitter section in Settings](/img/screenshots/twitter/settings-section.png)

## DM Sync

Direct message conversations are imported as interactions, with participants, message content, and timestamps. Conversations are deduplicated by Twitter conversation ID. Per-contact sync uses the targeted `/dm_conversations/with/:participant_id/dm_events` endpoint.

DM sync uses **delta sync** via a `since_id` cursor stored on the user record (`twitter_dm_cursor`). After each sync, the cursor advances to the newest event ID, so subsequent runs only fetch new DMs. If the cursor goes stale (for example after re-authorization), the API returns 400. PingCRM then retries without the cursor, does a full fetch, and sets a fresh cursor.

### Handle Updates

When you change a contact's Twitter handle in the UI, PingCRM clears the old `twitter_user_id` and `twitter_bio`, which are now stale, and dispatches a background task that fetches the new profile's bio and avatar through the bird CLI.

## Mention & Reply Sync

Tweets that @mention you and your outbound replies are imported as interactions through the **bird CLI**, which makes no X API calls. Each sync stores a cursor (`twitter_mention_cursor` and `twitter_reply_cursor` in `sync_settings`), so later runs process only new tweets.

## Bio Monitoring

PingCRM periodically checks your contacts' Twitter bios. When a bio changes, it:

1. Creates a **notification**.
2. Adds a **timeline event** to the contact's interaction history with the new bio text.

A bio change can point to a career move or fundraising activity.

![Bio change event in the contact timeline](/img/screenshots/twitter/bio-change-timeline.png)

## Event Classification (On-Demand)

When it composes follow-up suggestions, PingCRM fetches recent tweets for that contact and has Claude classify events into these categories:

| Category | Example |
|---|---|
| Job change | "Joined @newcompany as VP Engineering" |
| Fundraising | "Excited to announce our Series A" |
| Product launch | "Launching our new platform today" |
| Promotion | "Thrilled to step into my new role as CTO" |
| Milestone | "10 years in the industry" |
| Event attendance | "Speaking at @conference next week" |

A daily cron does not fetch or classify tweets. They are fetched when the follow-up engine needs context for a specific contact, which avoids calls for contacts that need no suggestion. Fetched tweets are cached in Redis for 12 hours.

See [Follow-Up Suggestions](./suggestions.md) for the full suggestion algorithm, including how Twitter events feed into it.

## Bird CLI (`@steipete/bird`)

PingCRM uses the [Bird CLI](https://www.npmjs.com/package/@steipete/bird) (`@steipete/bird v0.8.0`) as the primary data source for Twitter/X. Bird authenticates with browser cookies instead of API keys, so X API rate limits and credits do not apply to it.

### What Bird CLI provides

| Feature | Bird command | OAuth fallback? |
|---|---|---|
| Tweet fetching | `bird user-tweets @handle -n 5` | No |
| Profile resolution (user ID) | `bird user-tweets @handle -n 1 --json-full` | No |
| Bio refresh (profile data) | `bird user-tweets @handle -n 1 --json-full` | No |
| **Mention sync** | `bird mentions -u @handle -n 50 --json` | No |
| **Reply sync** | `bird user-tweets @handle -n 50 --json` (filtered to replies) | No |
| **Handle → ID resolution** | `bird user-tweets @handle -n 1 --json-full` | No |

### Authentication

Bird authenticates with two cookies from an active x.com browser session, `auth_token` and `ct0`. They are per-user: each user's cookies are stored encrypted on their own account and passed to every `bird` call made on their behalf.

- The Chrome extension captures and refreshes them automatically. See [Connecting your X account](#connecting-your-x-account-bird-cli).
- Alternatively, push them yourself with `POST /api/v1/integrations/twitter/cookies` (body: `auth_token`, `ct0`).
- **Settings → Integrations** shows the connection status (connected or expired).

PingCRM does not read `AUTH_TOKEN` or `CT0` environment variables, so there is nothing to set in `.env`. If `bird whoami` succeeds by hand inside the container, that comes from bird's own environment fallback and does not mean the app is connected. Only the per-user cookies count.

### Error handling (no OAuth fallback)

Bird CLI is the only source for mentions, replies, bio polling, and handle resolution. When a bird call fails:

1. PingCRM logs the failure with `provider=twitter`.
2. It runs `bird whoami` with your stored cookies, at most once per user per sync run. If that check fails, the connection status flips to **expired** and PingCRM creates an "X cookies expired" notification linking to Settings. If the check passes, the failure is logged as transient and no notification is sent.
3. The sync returns zero results instead of crashing.

If the `bird` binary is not installed, mention and reply sync create a "Twitter mention sync unavailable" or "Twitter reply sync unavailable" notification.

OAuth is used only for **DM sync** (`/dm_events`) and the one-time user ID lookup (`/users/me`), which bird cannot do.

### Tweet caching

Tweets fetched through Bird are cached in Redis for 12 hours, which avoids repeated CLI calls and speeds up the message composer.

### Installation

```bash
npm install -g @steipete/bird@0.8.0
```

Verify installation:

```bash
bird --version
```

The backend checks at runtime that Bird is available with `shutil.which("bird")`. You need no configuration beyond the cookies.

---

## Sync Schedule

| Task | Schedule | What it does |
|---|---|---|
| Bio + profile polling | Daily at 04:00 UTC | Fetches profiles via Bird CLI, detects bio changes, updates location, downloads missing avatars |
| DM sync | Daily at 04:00 UTC | Imports DM conversations via Twitter OAuth |
| Mention and reply sync | Daily at 04:00 UTC, in the same task as DM sync | Imports @mentions and replies via bird CLI |
| Tweet fetching + classification | On-demand | Fetched when composing follow-up suggestions (12h Redis cache) |

The daily job queues only users who have connected Twitter through OAuth (a stored refresh token).
