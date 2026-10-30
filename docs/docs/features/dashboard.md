---
sidebar_position: 1
title: Dashboard
description: "The PingCRM dashboard: stat cards, pending follow-ups, recent activity, and a Needs Attention panel for high-priority contacts going quiet."
---

# Dashboard

The `/dashboard` page is the daily view. Stat cards sit at the top, follow-ups and recent activity fill the left column, and a Needs Attention panel runs down the right. The data refreshes every 5 minutes.

![Dashboard overview](/img/screenshots/dashboard/overview.png)

The subheading under the title summarizes the state, for example "You have 4 pending suggestions and 2 contacts need attention this week." It reads "Your networking overview" when there is nothing pending.

## Stat cards

The page shows these counters:

- **Total contacts**: every contact that is not archived.
- **Active relationships**: contacts in the `active` and `strong` score buckets (relationship score 4 and above). The trend arrow compares against the number of distinct contacts you interacted with in the previous 7 days.
- **Interactions this week**: interactions across all platforms in the last 7 days, compared with the 7 days before.

The two trend cards show a green up arrow or a pink down arrow. There is no arrow when the earlier value is zero or unchanged. Total contacts has no trend.

A new account with zero contacts sees an onboarding card instead, with shortcuts to Settings for Google, Telegram, Twitter/X, and LinkedIn, and a link to import a CSV file.

If the API cannot be reached, the dashboard shows a "Couldn't load your dashboard" message with a **Retry** button instead of an empty account.

## Pending Follow-ups

Up to five pending suggestions from the follow-up engine, each as an expandable card. Expanding a card shows the AI-drafted message, and from there you can:

- **Send** the message. Telegram messages are sent directly, and can be scheduled. For email and Twitter, the draft is copied to your clipboard (the Twitter profile also opens in a new tab) and the suggestion is marked sent.
- **Snooze** for 2 weeks, 1 month, or 3 months.
- **Dismiss** the suggestion.

A badge on each card shows what triggered it: `90+ days`, `New event`, `Scheduled`, or `Birthday`. **View all** opens the full `/suggestions` page. With nothing pending, the widget links to **Generate suggestions**.

![Follow-up card expanded with AI-drafted message](/img/screenshots/dashboard/followup-expanded.png)

## Recent Activity

The five most recent contacts you interacted with in the last 7 days. Each contact appears once, with their latest interaction and a preview of its content. The icon shows the platform, and a row opens the contact. **View all** opens the contacts list sorted by last interaction.

## Needs Attention

High-priority contacts whose last interaction is older than your high-priority threshold (30 days by default, adjustable under Follow-up Rules in [Settings](./settings.md)). Contacts with no interactions, and contacts tagged `2nd tier`, are left out. The panel lists up to five contacts, most overdue first, each with how long ago you last talked and a days-overdue label that turns red past five days. A pill in the header shows the count. When nobody is overdue, the panel reads "All caught up!". **View all** opens the contacts page sorted by overdue.

![Needs Attention panel](/img/screenshots/dashboard/needs-attention.png)
