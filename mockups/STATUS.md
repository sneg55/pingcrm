# Mockup Status Report

Last updated: 2026-03-10

## Files

| File | Page | Status |
|------|------|--------|
| `dashboard-v2.html` | Dashboard | Complete |
| `contacts-v2.html` | Contacts List | Complete |
| `contact-detail.html` | Contact Detail | Complete |
| `settings-redesign.html` | Settings | Complete |

---

## What's Implemented in Mockups

### Dashboard (`dashboard-v2.html`)
- Stat cards (4): Total contacts, Active relationships, Interactions this week, Pending suggestions
- Pending Follow-ups with expandable suggestion cards (3 cards: active, birthday, dormant revival)
- Snooze dropdown with duration options (2w/1m/3m) on each suggestion card
- Weekly Activity bar chart (inbound/outbound)
- Birthdays This Week widget (3 upcoming)
- New & Active widget (recently added contacts with interactions)
- Needs Attention widget (overdue contacts)
- Recent Activity feed
- Relationship Health distribution bars
- Empty state (zero contacts welcome screen)

### Contacts List (`contacts-v2.html`)
- Search + filter bar with quick filter chips (Priority, Score)
- Expanded filter panel: Platform checkboxes, Tag search, Last Contact date range + presets (7d/30d/3mo/6mo/12mo) + Overdue toggle
- Saved filters: Save filter button + dropdown with preset list
- Export button (CSV/vCard) in toolbar
- Sortable columns: Contact, Company, Score, Priority, Activity, Last
- Column resize handles on Contact/Company headers
- Activity sparkline bars + count per row
- Per-row kebab menu (Row 1 shown): View profile, Edit contact, Send message, Manage tags, Archive, Delete
- Bulk action bar: Add Tag, Remove Tag, Merge, Archive, Delete
- Add Contact modal
- Pagination
- Empty state (no results)

### Contact Detail (`contact-detail.html`)
- Header: Avatar with upload overlay, inline-editable name/title/company/location/birthday
- Bios: Twitter + Telegram bios prominently displayed
- Contact channels: Email, Telegram, Twitter, LinkedIn, Phone
- Tags with add button
- Priority toggle: segmented 3-button (High/Medium/Low)
- Archive button
- Kebab menu: Refresh details, Enrich with Apollo, Auto-tag with AI, Send message, Log interaction, Show duplicates, Archive, Delete
- Follow-up suggestion card (expandable, same pattern as dashboard)
- Snooze dropdown with durations on suggestion card
- Add note input (expandable textarea)
- Chat-like timeline: inbound/outbound messages, notes (amber left-border), system events, date separators
- Notes: hover-to-reveal edit/delete buttons
- Details tab: Phone, LinkedIn URL, Additional emails, Website
- Relationship Health sidebar: Score (5/10), dimension bars (Reciprocity/Recency/Frequency/Breadth), stats (last contacted, total interactions, since), 6-month trend
- Possible Duplicates sidebar: match score, field comparison, merge/reject actions
- Related Contacts sidebar: shared tags/company/co-mentions
- Log Interaction modal: date, type, platform, summary, key takeaways
- Empty state (zero interactions)

### Settings (`settings-redesign.html`)
- Tab bar: Integrations, Import, Follow-up Rules, Tags, Account
- **Integrations tab**: Gmail (connected, stats, sync progress bar, kebab: Sync settings/Re-authorize/Sync history/Disconnect), Telegram (connected, stats, kebab: Sync settings/Reset session/Sync history/Disconnect), Twitter (not connected), Sync Schedule settings
- **Import tab**: CSV upload, LinkedIn export instructions + upload, Import History table (file, rows, success, errors, details link)
- **Follow-up Rules tab**: Priority thresholds with range sliders (High/Medium/Low), Suggestion preferences (batch size, Pool B toggle, birthday reminders, preferred channel)
- **Tags tab**: Tag taxonomy by category (Relationship, Industry, Context), AI auto-tagging toggle
- **Account tab**: Profile (name, email, photo upload, timezone, locale), Change Password, Danger Zone (export all data, delete account)
- Toast notifications (sync started, sync complete)

---

## Outstanding / Not Yet Mocked Up

### Missing Pages (no mockup exists)
1. **Suggestions page** — dedicated page for suggestion digest generation + management (code exists at `/suggestions/page.tsx`)
2. **Archive page** — list of archived contacts with Unarchive action (code exists at `/contacts/archive/page.tsx`)
3. **Identity/Duplicates page** — full duplicate resolution interface with match pairs (code exists at `/identity/page.tsx`)
4. **Notifications page** — notification list with expand/collapse and mark-all-read (code exists at `/notifications/page.tsx`)

### Design Decisions Pending
5. **Per-row kebab vs bulk-only** — mockup shows per-row kebab menus on contacts list, but code only has bulk actions. Need to decide: implement per-row kebabs in code, or remove from mockup?
6. **"Show duplicates" trigger** — mockup has sidebar card + kebab item, code has kebab-only modal. Confirm sidebar card approach is the target.

### Features in Mockup but Not in Code
7. **Log Interaction modal** — contact detail modal for structured interaction logging (date/type/platform/summary)
8. **Related Contacts sidebar** — showing contacts with shared tags/company
9. **Import History table** — showing past imports with status/error counts
10. **Sync settings / Sync history** — kebab menu items on integration cards
11. **Account management** — profile editing, password change, timezone/locale
12. **Danger Zone** — delete account, export all data
13. **Avatar upload** — contact photos and user profile photos
14. **Saved filters** — save/load filter presets on contacts page
15. **Column resize** — drag handles on table columns
16. **Birthdays This Week** widget — dashboard birthday reminders
17. **New & Active** widget — recently added contacts with interactions

### Features in Code but Not in Mockup
18. **Enrich with Apollo** — contact detail kebab action (in mockup now, but no enrichment result UI)
19. **Auto-tag with AI** — contact detail kebab action (in mockup now, but no progress/result UI)
20. **User menu** — top-right user dropdown with sign-out (nav has user name but no dropdown in mockups)

---

## GitHub Issues (Pending Creation)

See `mockups/github-issues.md` — 5 issues ready to create once `gh auth login` is completed:
1. Contact photo/avatar upload
2. Account/profile management
3. Danger zone (delete account, export data)
4. Import history/log
5. Sync-now visualization
