---
sidebar_position: 1
title: Dashboard
---

# Dashboard

The `/dashboard` page provides a high-level overview of your networking activity and relationship health. All statistics are fetched via React Query hooks, ensuring data stays fresh with background refetching.

## Stats Overview

The top of the dashboard displays key metrics at a glance:

- **Total Contacts** -- the number of contacts in your CRM.
- **Pending Suggestions** -- follow-up suggestions awaiting your review.
- **Identity Matches** -- cross-platform identity matches detected across Gmail, Telegram, and Twitter.

## Reach Out This Week

This section surfaces the top 3 contacts you should reach out to. Each entry includes:

- The contact name and relationship score.
- A reason explaining why outreach is recommended (e.g., "No interaction in 90+ days", "Job change detected").
- An AI-drafted message you can review, edit, and send directly from the dashboard.

## Recent Activity

A chronological feed of the latest interactions across all connected platforms. This includes sent and received emails, Telegram messages, Twitter DMs, manually logged notes, and meeting records.

## Relationship Health

A breakdown of your contact base by relationship status:

- **Active** -- contacts with recent, regular interactions.
- **Warming** -- contacts where interaction frequency is increasing.
- **Going Cold** -- contacts where interaction frequency has dropped and attention may be needed.

This distribution helps you quickly identify whether your network is being maintained or if outreach is falling behind.
