---
sidebar_position: 8
title: Gmail Integration
---

# Gmail Integration

Ping CRM connects to Gmail via OAuth 2.0 with Google, syncing email threads, contacts, and calendar events to build a complete interaction history.

## Authentication

The Gmail integration uses standard Google OAuth 2.0. After granting access on the Google consent screen, Ping CRM stores a refresh token to maintain access without repeated sign-in. Multi-account support allows connecting more than one Gmail address.

## Email Sync

Email threads are imported as interactions. Each synced thread captures:

- **Sender and recipients** -- mapped to existing contacts or used to create new ones.
- **Subject line** -- stored as the interaction title.
- **Timestamps** -- sent and received times for accurate timeline ordering.
- **Body snippets** -- a preview of the email content for context without storing full message bodies.

Threads are deduplicated by Gmail thread ID, so re-syncing does not create duplicate interactions.

**Schedule:** Email sync runs automatically every 6 hours.

## Google Contacts Sync

A one-way import pulls contacts from Google Contacts into Ping CRM. Contact records include names, email addresses, phone numbers, and organization fields. This import does not write back to Google -- it is read-only.

## Google Calendar Sync

Calendar events are imported as meeting-type interactions. Event attendees are matched to existing contacts by email address. Events include title, start/end times, and attendee lists.

**Schedule:** Calendar sync runs daily at 06:00 UTC.

## Background Processing

All Gmail syncs (email, contacts, calendar) run as Celery background tasks. You do not need to keep the browser open. A notification is delivered when each sync completes or fails.
