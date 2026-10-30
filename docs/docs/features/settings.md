---
sidebar_position: 7
title: Settings
description: "PingCRM settings: manage platform connections, data imports, follow-up rules, tags, and your account, with a connection badge for each integration."
---

# Settings

The **Settings** page (`/settings`) has five tabs: **Integrations**, **Import**, **Follow-up Rules**, **Tags**, and **Account**. The active tab is stored in the URL (`/settings?tab=tags`), so you can link straight to one.

![Settings page overview](/img/screenshots/settings/overview.png)

![Connected accounts at a glance](/img/screenshots/settings/connected-accounts.png)

## Integrations

Each platform has its own card with a **Connected** or **Not connected** badge. Most connected cards offer **Sync now** and a menu with **Sync settings**, **Sync history**, and a disconnect action. Sync settings has an auto-sync toggle and a schedule: Manual only, Every 6 hours, Every 12 hours, or Once daily. Defaults are daily for Telegram and Twitter, every 6 hours for Gmail, and manual for LinkedIn. Sync history lists past runs with record counts and error details.

### Gmail

- **Connect** starts the Google OAuth flow and attaches the Google account to the account you are logged in with. Connecting does not switch you to a different PingCRM user.
- **Multiple accounts**: each linked Google account is listed with its address and a remove button. **Sync now** pulls Google Contacts, Gmail threads, and Calendar events for every linked account.
- **Re-authorize** in the menu repeats the OAuth flow if Google credentials expire.
- **Disconnect Gmail** removes the first linked account and keeps emails already synced. Use the remove button next to an address to drop a specific account.

### Telegram

- **Connect** asks for your phone number, then the one-time code Telegram sends to your app. If two-factor authentication is on, it then asks for your password.
- **Sync now** imports Telegram DMs as interactions and discovers contacts from group memberships. A progress indicator shows while it runs.
- **Sync settings** also has an **Import 2nd Tier contacts** toggle. When 2nd-tier contacts exist, you can delete them all from there.
- **Reset session** clears the stored Telegram session so you can reconnect. **Disconnect Telegram** removes the connection.

### Twitter / X

X has separate cards for DMs and for mentions and bios:

- **Twitter / X, DMs** uses the OAuth 2.0 PKCE flow to sync direct messages. It has **Sync now**, **Re-authorize**, sync settings, history, and **Disconnect Twitter**.
- **X (Twitter), mentions and bios** relies on cookies that the PingCRM Chrome extension sends from your logged-in X session. The cookies are stored per user, so there is no instance-wide X login to configure. The badge shows **Connected**, or **Expired** when X rejects the cookies, and Refresh reconnects. If the extension is missing, **Connect X** shows an install prompt.

### LinkedIn Extension

Install the Chrome extension, generate a pairing code in its popup, and enter the code in Settings. The card shows when the extension was paired. It also has **Sync now**, sync settings, history, and **Disconnect LinkedIn**, which revokes the extension token.

See [LinkedIn Integration](./linkedin.md) for the extension, Voyager sync, and suggestion buttons.

### WhatsApp

Connect shows a QR code. On your phone, open WhatsApp, go to Settings, then Linked Devices, then Link a Device, and scan it. Once linked, the card shows the phone number and offers **Sync now**, **Sync history**, and **Disconnect WhatsApp**.

### Meta

The Meta card syncs Facebook Messenger and Instagram DMs through the Chrome extension. Its menu has separate sync history for Messenger and Instagram.

## Import

- **CSV Import** accepts a CSV by drag and drop or file picker and supports the Google Contacts export format. Each row is saved independently, so a bad row shows up in the list of errors without stopping the rest.
- **LinkedIn** has two uploads: `Connections.csv` from LinkedIn's "Download your data" export, and `messages.csv` for message history.

Imported contacts appear in the contacts list and take part in identity resolution matching.

![CSV import dropzone](/img/screenshots/settings/csv-import.png)

## Follow-up Rules

**Priority Thresholds** set how many days can pass before the suggestion engine recommends reaching out to a contact at each priority level. The defaults are 30 days for high, 60 for medium, and 180 for low. The API accepts 7 to 365 days for each, while the sliders in the UI cap high priority at 30 days and medium at 90.

**Suggestion Preferences** control generation:

- **Max suggestions per batch**: 5, 10, 15, or 20.
- **Include dormant revival (Pool B)**: suggest contacts you have not spoken to in a while.
- **Active window (days)**: how recent a contact must be to count as active (Pool A). Options run from 6 months to 10 years, with 1 year as the default. Older contacts fall into Pool B.
- **Birthday reminders**: generate suggestions for upcoming birthdays.
- **Preferred channel**: Auto-detect, Email, Telegram, or Twitter.

![Follow-up interval settings per priority level](/img/screenshots/settings/followup-rules.png)

## Tags

Manage the tag taxonomy used to organize contacts. An LLM can draft a taxonomy from your contacts and apply it, or you can edit tags by hand. The taxonomy supports hierarchical categories.

![Tag taxonomy management](/img/screenshots/settings/tags.png)

## Account

- **Profile** and **Change Password** forms.
- **MCP Access** manages the API key for the [MCP Server](./mcp.md), which lets AI clients such as Claude Desktop and Cursor query your CRM. **Generate key** shows the key once, so copy it then. Only an HMAC-SHA256 hash is stored. **Regenerate** replaces the key and **Revoke** invalidates it immediately. The status line shows whether a key is active.
- **Danger Zone** has **Delete account**, which permanently removes your account and all data. The **Export all data** button is a placeholder that shows a "coming soon" notice.
