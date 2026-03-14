---
sidebar_position: 2
title: Contact Management
---

# Contact Management

Contacts are the core entity in Ping CRM. The contact list and detail pages let you browse, search, edit, and interact with your professional network.

## Contact List

The `/contacts` page displays all contacts in a searchable, sortable, paginated table.

### Search and Filtering

- **Full-text search** across contact names, emails, companies, and notes.
- **Filter by tags** to narrow results to specific groups.
- **Filter by source** (Gmail, Telegram, Twitter, CSV import, manual entry).
- **Filter by relationship score** range.
- **Filter by priority level** (high, medium, low, archived).

### Sorting

The list can be sorted by:

- Name (alphabetical)
- Relationship score (highest or lowest first)
- Date added or last interaction date

### Pagination

Results are paginated to keep the interface responsive. Navigate between pages using the controls at the bottom of the list.

## Contact Detail

The `/contacts/[id]` page shows the full profile for a single contact.

### Inline Editing

Contact fields can be edited inline -- click a field to modify it. Fields include name, email, phone, company, title, tags, priority level, and notes.

### Company Autocomplete

When setting a contact's company, an autocomplete dropdown suggests existing organizations so you can link contacts to the correct org without creating duplicates.

### Priority Levels

Each contact can be assigned a priority:

- **High** -- key relationships that should never go cold.
- **Medium** -- important contacts to check in with periodically.
- **Low** -- casual connections.
- **Archived** -- contacts you no longer wish to receive suggestions for.

### Relationship Score Badge

A visual badge displays the contact's computed relationship score, giving you an at-a-glance sense of how strong the connection is.

### Message Composer

Send messages directly from the contact detail page. Supported channels:

- **Email** (via connected Gmail account)
- **Telegram**
- **Twitter DM**

The composer uses AI to draft context-aware messages based on the contact's profile and interaction history.

### Interaction Timeline

A chronological timeline of all interactions with the contact, including:

- Sent and received messages across all platforms.
- Manually added notes.
- Logged meetings.
- Bio change events (detected from Twitter).

### Telegram Common Groups

A sidebar card displays Telegram groups shared with the contact, providing additional context for your relationship.

### Duplicate Detection

The system detects potential duplicate contacts based on matching email addresses, names, and cross-platform identifiers. Duplicates can be reviewed and merged.

### Rate Limit Handling

If the API returns a 429 (rate limit) response, the UI displays a countdown timer indicating when the next request can be made.

## Importing Contacts

Three methods are available for adding contacts:

- **CSV Upload** -- bulk import from a CSV file with column mapping.
- **Google Contacts Sync** -- import contacts from your connected Google account.
- **Manual Entry** -- add contacts one at a time through the UI.
