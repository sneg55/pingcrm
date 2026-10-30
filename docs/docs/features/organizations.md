---
sidebar_position: 4
title: Organizations
description: "Organizations in PingCRM group contacts by company so you can track companies across your network and see relationships at the org level."
---

# Organizations

Organizations group contacts by company or institution. The organization pages show which companies appear in your network and how strong your relationships are at the company level.

## Organization List

The `/organizations` page lists organizations in a searchable, sortable table, 50 per page.

![Organizations list](/img/screenshots/organizations/list.png)

### Table Columns

Each row shows:

- **Organization**: the name, with a logo or a favicon fetched from the organization's domain.
- **Contacts**: the number of linked contacts.
- **Avg Score**: the average relationship score across the organization's contacts.
- **Interactions**: the total interaction count.
- **Last Activity**: the date of the most recent interaction with anyone at the organization.

### Search

A search field filters organizations by name.

### Sorting

Click a column header to sort the loaded page by that column. Name sorts A to Z. The numeric columns and Last Activity sort highest or most recent first. The server returns organizations ordered by name, so sorting only reorders the current page.

### Auto-Hiding

Organizations with no active contacts are hidden from the list. Archived contacts do not count as active.

### Actions

Select one or more rows to open the action bar:

- **Merge**: available once two or more organizations are selected. A dialog asks which one to keep, and all linked contacts move to it.
- **Delete**: removes the selected organizations after a confirmation.

Each row also has its own delete button.

![Selecting multiple organizations for merge](/img/screenshots/organizations/merge-selection.png)

## Organization Detail

The `/organizations/[id]` page shows the full profile for a single organization.

![Organization detail page](/img/screenshots/organizations/detail.png)

### Inline Editing

You can edit these fields in place:

- **Name**. Renaming updates the company field on every linked contact.
- **Website**, which falls back to the domain when no full URL is set.
- **Location**
- **LinkedIn URL**
- **Twitter handle**
- **Notes**: free text for additional context.

Changing the website or domain downloads a fresh logo.

### Organization Stats

The stat cards show total contacts, average relationship score, total interactions, and the most recent activity date. The numbers come from a materialized view that Celery refreshes hourly, at 30 minutes past the hour.

### Contacts Table

The table lists every contact linked to the organization, with columns for Name, Title, Score, and Last Interaction. You can sort by Score, Name, or Recent. Archived contacts appear after active ones, in muted text.

### External Links

Website, LinkedIn, and Twitter values are clickable and open in a new tab.

### Deleting an Organization

Deleting an organization unlinks its contacts but does not delete them. The contacts stay in your CRM without an organization.
