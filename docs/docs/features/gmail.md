---
sidebar_position: 8
title: Gmail Integration
description: "PingCRM's Gmail integration syncs email threads, contacts, and calendar events via Google OAuth 2.0 to build a complete interaction history."
---

# Gmail Integration

PingCRM connects to Gmail through Google OAuth 2.0 and syncs email, contacts, and calendar events into each contact's interaction history.

## Authentication

The integration uses standard Google OAuth 2.0. After you grant access on the Google consent screen, PingCRM stores a refresh token so you do not have to sign in again. Connecting Google always attaches the Google account to the PingCRM user who is logged in, so you can link more than one Gmail address to the same user. Email sync, Contacts sync, and Calendar sync run against every linked account.

PingCRM requests these scopes: `userinfo.email`, `userinfo.profile`, `contacts.readonly`, `gmail.readonly`, `calendar.readonly`, and `gmail.send` (used only for meeting prep emails).

> **Setup note:** Publish the Google OAuth consent screen as **"In production."** In **"Testing"** mode Google expires refresh tokens after 7 days, which keeps breaking Gmail, Calendar, and Contacts sync.

![Gmail section in Settings](/img/screenshots/gmail/settings-section.png)

## Email Sync

Each email message is imported as an interaction. Sync looks at threads from the last year, in every linked Google account. Each message records:

- **Sender and recipients:** matched to existing contacts by email address (or BCC hash). Email sync does not create new contacts; messages with no matching contact are skipped.
- **Direction:** inbound (the contact wrote to you) or outbound (you wrote to the contact), per message.
- **Timestamp:** the message time, used to order the timeline.
- **Body snippet:** a preview of up to 500 characters. Full message bodies are not stored.

Messages are deduplicated by Gmail message ID, and each message in a thread becomes its own interaction, so the timeline shows the whole conversation.

**Schedule:** Email sync runs every 6 hours (`sync_gmail_all`).

![Gmail thread messages in a contact's interaction timeline](/img/screenshots/gmail/timeline-thread.png)

## BCC Email Logging

Each contact has a unique BCC address. BCC it on an email from any client (Gmail, Outlook, Apple Mail) and PingCRM logs the email to that contact's timeline.

**Format:** `yourname+{hash}@gmail.com`, which is your PingCRM login email with a `+hash` suffix.

**How it works:**
1. Find the BCC address on the contact detail page (copy button next to the hash).
2. When composing an email, add the BCC address.
3. Gmail delivers the email to your inbox (Gmail ignores the `+` suffix).
4. On the next sync, PingCRM finds the `+hash` in the headers and links the interaction to the right contact.

This needs no custom domain or email infrastructure, only Gmail's native `+` addressing.

![BCC address with copy button on the contact detail page](/img/screenshots/gmail/bcc-address.png)

## Google Contacts Sync

A one-way import pulls contacts from Google Contacts into PingCRM for every linked Google account. Imported fields are names, email addresses, phone numbers, and organization (company and title). Contacts are matched by Google resource name or email address; matches have only their empty fields filled, and unmatched contacts are created with source `google`. Contacts that were previously imported but no longer exist in Google are archived. The import is read-only and never writes back to Google. It runs when you start it from Settings (`POST /api/v1/contacts/sync/google`); there is no beat schedule for it.

## Google Calendar Sync

Calendar events from each account's primary calendar become meeting interactions, covering the past three years and the next 30 days. Cancelled events and events with no attendees other than you are skipped. Attendees are matched to existing contacts by email address, and attendees with no matching contact are created as new contacts. The event title is stored as the interaction preview.

**Schedule:** Calendar sync runs daily at 06:00 UTC.

## Pre-Meeting Prep Emails

About 30 minutes before a Google Calendar meeting, PingCRM emails you a prep brief with context on each attendee:

- **Attendee profiles:** name, title, company, and relationship score (Strong, Warm, or Cold).
- **Platform bios:** Twitter, LinkedIn, and Telegram bios when available.
- **Recent interactions:** up to the last 3 non-meeting interactions per attendee, across platforms.
- **AI talking points:** Claude Haiku writes 3-5 talking points from the attendee context.

The email is sent from your own Gmail account through the Gmail API (`gmail.send` scope). Accounts connected before that scope was added need to re-authorize Google.

**Schedule:** A background task (`scan_meeting_preps`) runs every 10 minutes and sends a prep email for meetings starting 30 to 40 minutes out. Redis dedup keys prevent duplicate sends.

**Settings:** The feature is on by default. To turn it off, set `meeting_prep_enabled` to `false` in the `gmail` object of `PUT /api/v1/settings/sync`. The Gmail Sync Settings dialog in the app only exposes the auto-sync toggle and schedule.

## Background Processing

Email, contacts, and calendar syncs and meeting prep emails all run as Celery background tasks, so the browser can stay closed. Contacts and calendar syncs create a notification when they complete or fail (including a re-authentication prompt when a Google token has expired). Gmail email sync records its result in sync history instead.
