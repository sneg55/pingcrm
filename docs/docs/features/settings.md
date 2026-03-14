---
sidebar_position: 7
title: Settings
---

# Settings

The **Settings** page (`/settings`) manages platform connections, data imports, and sync controls. Each integration displays a connection status badge (connected, disconnected, or error).

## Gmail

- **Connect / Disconnect** -- initiates or revokes the Google OAuth flow.
- **Connected email** -- displays the Gmail address currently linked.
- **Sync Contacts** -- triggers a one-way import of Google Contacts into Ping CRM.
- **Sync Calendar** -- imports Google Calendar events as meeting-type interactions.

## Telegram

- **Connect via phone** -- enter your phone number to start the Telegram authentication flow.
- **OTP verification** -- enter the one-time code sent to your Telegram app.
- **2FA support** -- if two-factor authentication is enabled on your Telegram account, you will be prompted for your password after OTP.
- **Sync Chats** -- imports Telegram DMs as interactions and discovers contacts from group memberships.

## Twitter / X

- **OAuth Connect / Disconnect** -- initiates or revokes the Twitter OAuth 2.0 PKCE flow.
- **Sync DMs and Mentions** -- imports direct message conversations and @mention interactions.

## CSV Import

- **Drag-and-drop upload** -- drop a CSV file onto the import area or click to browse.
- **LinkedIn CSV import** -- supports the export format from LinkedIn's "Download your data" feature. Columns are mapped automatically to Ping CRM contact fields.
- Imported contacts appear in the contacts list immediately and are eligible for identity resolution matching.

## Connection Status Badges

Each integration section shows a badge indicating its current state:

- **Connected** -- active and syncing on schedule.
- **Disconnected** -- no credentials stored; click Connect to set up.
- **Error** -- credentials expired or a sync failure occurred; reconnect to resolve.
