# Plans - Ping CRM

> Phases 1-7 (101 tasks, all done) archived in [Plans-archive.md](Plans-archive.md)
> Phases 8-9 (all done) — Security fixes, AI auto-tagging, test coverage

---

## Phase 10: Maintenance & Polish

作成日: 2026-03-08

### 10.1 Commit In-Progress Work (High)

- [x] `cc:完了` Commit and push: Labels→Tags rename (#10), Contacts nav submenu with Archive page (#11)
- [x] `cc:完了` Close GitHub issues #10 and #11

### 10.2 Archive Page Suspense Wrapper (Medium)

- [x] `cc:完了` Wrap `/contacts/archive/page.tsx` in `<Suspense>` boundary (same pattern as contacts page) — required by Next.js App Router for `useSearchParams()`

### 10.3 TypeScript Errors Cleanup (Medium)

- [x] `cc:完了` Fix 4 pre-existing TS errors: `contacts/[id]/page.tsx` (2 errors — location/birthday fields), `settings/page.tsx` (1 error — POST call signature), `auth/google/callback/page.test.tsx` (1 error)

### 10.4 Follow-Up Engine v2 — Pool A/B Split (High)

- [x] `cc:完了` Add `pool` column to `follow_up_suggestions` model + schema + migration
- [x] `cc:完了` Add `revival_context` param to message composer with reconnect prompt
- [x] `cc:完了` Refactor engine: Pool A (active, 3 slots) + Pool B (dormant revival, 2 slots) with budget rollover
- [x] `cc:完了` Pool B triggers: B1 deep dormant, B2 mid-dormant, B3 event revival (overrides hard cap)
- [x] `cc:完了` API fix: remove `last_interaction_at IS NOT NULL` filter, pass `revival_context` on regenerate
- [x] `cc:完了` Tests: 52 total (31 existing updated + 18 new Pool B tests), all passing

### 10.5 Frontend Test Coverage Expansion (Medium)

- [x] `cc:完了` Add tests for nav component (dropdown rendering, active state, submenu links)
- [x] `cc:完了` Add tests for archive page (renders, search, unarchive button)
- [x] `cc:完了` Add tests for identity page (scan, merge flow)

### 10.6 PKCE Verifier Storage (Medium)

- [x] `cc:完了` Move Twitter PKCE verifiers from in-memory dict to Redis (required for multi-worker production deployment)

### 10.7 Celery Beat Schedule Review (Low)

- [x] `cc:完了` Verify Telegram sync interval (12h) is appropriate post-split into 3 sub-tasks
- [x] `cc:完了` Consider adding Google Calendar sync to beat schedule (currently manual-only)

### 10.8 Docker Deployment (Low)

- [x] `cc:完了` Create `docker-compose.yml` with PostgreSQL, Redis, backend, frontend, Celery worker, Celery beat
- [x] `cc:完了` Create `Dockerfile` for backend and frontend

### 10.9 OpenAPI Schema Regeneration (Low)

- [x] `cc:完了` Regenerate `backend/openapi.json` and `frontend` openapi-fetch types to include new `archived_only` param and any other recent API changes

---

## Phase 11: Mockup Improvements (from UX Report)

作成日: 2026-03-10

> Improve HTML mockups in `mockups/` to cover gaps found during critical review.
> Each task = update the relevant mockup HTML file. No backend/frontend code changes.

### 11.1 Dashboard — Missing Widgets (Medium)

| # | Task | Status | DoD | Depends |
|---|------|--------|-----|---------|
| 1 | Add "Birthdays this week" widget to `dashboard-v2.html` | `cc:完了` | Card shows upcoming birthdays (next 7d) with contact name, date, quick-action link | — |
| 2 | Add "New contacts with activity" widget to `dashboard-v2.html` | `cc:完了` | Card shows recently added contacts that already have interactions | — |

### 11.2 Contacts List — Bulk & Filters (Medium)

| # | Task | Status | DoD | Depends |
|---|------|--------|-----|---------|
| 3 | Add bulk selection + action bar to `contacts-v2.html` | `cc:完了` | Checkbox column, select-all, floating action bar (archive, tag, delete) | — |
| 4 | Add column resize/reorder handles to `contacts-v2.html` | `cc:完了` | Visual drag handles on column headers | — |
| 5 | Add saved/custom filters UI to `contacts-v2.html` | `cc:完了` | "Save filter" button + dropdown of saved filter presets | — |
| 6 | Add export contacts button to `contacts-v2.html` | `cc:完了` | Export button (CSV/vCard) in toolbar area | — |

### 11.3 Contact Detail — Enhancements (Medium)

| # | Task | Status | DoD | Depends |
|---|------|--------|-----|---------|
| 7 | Add avatar upload UI to `contact-detail.html` | `cc:完了` | Click avatar circle → file picker overlay, preview, remove option | — |
| 8 | Add "similar contacts" / relationship graph placeholder to `contact-detail.html` | `cc:完了` | Sidebar card showing related contacts with shared tags/company | — |
| 9 | Add structured interaction logging form to `contact-detail.html` | `cc:完了` | Modal/drawer with date, type, platform, summary fields | — |

### 11.4 Settings — Account & Data (High)

| # | Task | Status | DoD | Depends |
|---|------|--------|-----|---------|
| 10 | Add account/profile management section to `settings-redesign.html` | `cc:完了` | Name, email, password change, user photo upload, timezone | — |
| 11 | Add danger zone section to `settings-redesign.html` | `cc:完了` | Delete account (with confirmation modal), export all data button | 10 |
| 12 | Add import history/log section to `settings-redesign.html` | `cc:完了` | Table of past imports with date, file, counts, error details | — |
| 13 | Add sync-now visualization to `settings-redesign.html` | `cc:完了` | Last-synced timestamps, sync-now buttons, progress indicator per platform | — |

### 11.5 Cross-Cutting — Empty States (Low)

| # | Task | Status | DoD | Depends |
|---|------|--------|-----|---------|
| 14 | Add empty state variants for all mockups | `cc:完了` | Each page has a zero-data view with illustration + CTA | 1-13 |

---

## Phase 12: Twitter & Telegram Sync Hardening (from Code Review)

作成日: 2026-03-13

### 12.1 Telegram Critical Fixes (High)

| # | Task | DoD | Depends | Status |
|---|------|-----|---------|--------|
| 1 | Add FloodWaitError handling in all Telegram sync paths | `FloodWaitError` caught in `sync_telegram_chats`, `sync_telegram_chats_batch`, `sync_telegram_contact_messages`, `sync_telegram_group_members`, `sync_telegram_bios` — waits `e.seconds + 5` then retries | — | `cc:TODO` |
| 2 | Set `telegram_last_synced_at` at end of first-sync batch chain | `sync_telegram_notify` (final chain task) sets `user.telegram_last_synced_at = now()` | — | `cc:TODO` |
| 3 | Add Redis lock to prevent concurrent first-sync dispatch | `sync_telegram_for_user` acquires `tg_sync_lock:{user_id}` with 6h TTL, skips if locked | — | `cc:TODO` |
| 4 | Normalize message ID to numeric Telegram user ID in all paths | `sync_telegram_contact_messages` uses resolved numeric ID (not username) for `raw_reference_id` | — | `cc:TODO` |

### 12.2 Twitter Critical Fixes (High)

| # | Task | DoD | Depends | Status |
|---|------|-----|---------|--------|
| 5 | Batch dedup queries in Twitter sync loops | All 5 sync functions (`sync_twitter_dms`, `sync_twitter_contact_dms`, `sync_twitter_mentions`, `sync_twitter_replies`) use single `WHERE raw_reference_id IN (...)` query instead of per-event SELECT | — | `cc:TODO` |
| 6 | Guard `last_interaction_at` in mentions and replies | `sync_twitter_mentions` and `sync_twitter_replies` use same `if older` guard as DM path | 5 | `cc:TODO` |
| 7 | Delete dead Twitter code | Remove: `_build_oauth_header`, `build_twitter_client` (OAuth 1.0a), `sync_twitter_bios` (unused), `fetch_mentions_bird`, `fetch_user_replies_bird` (dead bird helpers), duplicate `hashlib` import | — | `cc:TODO` |

### 12.3 Telegram Reliability Fixes (Medium)

| # | Task | DoD | Depends | Status |
|---|------|-----|---------|--------|
| 8 | Fix `connect_telegram` missing disconnect on error | `connect_telegram` wrapped in `try/finally: await client.disconnect()` | — | `cc:TODO` |
| 9 | Fix `sync_telegram_bios` to include contacts with only `telegram_user_id` | Query uses `OR(telegram_username IS NOT NULL, telegram_user_id IS NOT NULL)` | — | `cc:TODO` |
| 10 | Add `notify_sync_failure` to batch task max retries | `sync_telegram_chats_batch_task` calls `notify_sync_failure.delay()` on final retry failure | — | `cc:TODO` |

---

## Backlog: Feature Exploration (from GitHub Issues)

| Issue | Title | Priority |
|-------|-------|----------|
| #7 | MCP Server integration | Explore |
| #6 | Pre-meeting prep notifications | Explore |
| #5 | Two-way device contact sync | Explore |
| #4 | Sync with WhatsApp, iMessage | Explore |
