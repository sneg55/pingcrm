# Global Search: Multi-Type Tabs (All | Contacts | Companies)

**Date:** 2026-04-01
**Status:** Approved

## Summary

Add functional tabs to the global search dropdown in the navbar. Currently the dropdown only searches contacts. This adds "All | Contacts | Companies" tabs that filter results by type, with organizations fetched from the existing API.

## Architecture

**Approach:** Frontend-only change. Two parallel API calls on the "All" tab, one call on each specific tab. No new backend endpoints — reuses `GET /api/v1/contacts` and `GET /api/v1/organizations`.

**Changed files:**
- `frontend/src/components/nav.tsx` — `NavSearch` component

## Tab UI & State

- New state: `tab: "all" | "contacts" | "companies"` (default: `"all"`)
- Three tab buttons render above the results list as inline text links with active underline
- Tab state resets to `"all"` when the dropdown closes or query is cleared

## Data Fetching

When `query.length >= 2`:

| Tab | API Calls | Results |
|-----|-----------|---------|
| **All** | `GET /api/v1/contacts?search={q}&page_size=4` + `GET /api/v1/organizations?search={q}&page_size=4` (parallel) | Interleaved by alternation (contact, org, contact, org...), capped at 6 total |
| **Contacts** | `GET /api/v1/contacts?search={q}&page_size=6` | Up to 6 contacts |
| **Companies** | `GET /api/v1/organizations?search={q}&page_size=6` | Up to 6 organizations |

React Query caches results so switching tabs doesn't re-fetch if the query hasn't changed.

## Result Rendering

| Type | Avatar | Primary text | Secondary text |
|------|--------|-------------|---------------|
| **Contact** | Initials circle or avatar image | Full name | Company |
| **Organization** | Building icon in circle | Org name | Contact count (e.g., "12 contacts") |

On the "All" tab, each row has a subtle type indicator (icon or label) to distinguish contacts from organizations.

- Clicking a contact navigates to `/contacts/{id}`
- Clicking an organization navigates to `/organizations/{id}`

## "View All Results" Link

Tab-aware navigation:

| Tab | Link destination |
|-----|-----------------|
| **All** | `/contacts?q={q}` |
| **Contacts** | `/contacts?q={q}` |
| **Companies** | `/organizations?q={q}` |

## Out of Scope

- Backend changes (no new endpoints)
- Organization detail page changes
- Contacts list page filter changes
- Keyboard navigation between tabs
- Persisting selected tab across sessions
