# Ping CRM Frontend — Test Coverage Plan

Created: 2026-03-11
Completed: 2026-03-11

---

## Current State

- **Framework:** Vitest + @testing-library/react + jsdom
- **Test files:** 27 files, 477 tests (all passing)
- **All 5 phases complete**

---

## Phase 1: Fix Broken Tests

| Task | Description | DoD | Depends | Status |
|------|-------------|-----|---------|--------|
| 1.1 | Update lucide-react mock in `setup.ts` — add all missing icons (`SlidersHorizontal`, `ArrowDown`, `ArrowUpDown`, `Filter`, etc.) | `contacts/page.test.tsx` renders without icon errors | - | cc:完了 |
| 1.2 | Fix `contacts/page.test.tsx` — update selectors for redesigned table (new column names, grid layout, select-all checkbox, stats header) | All 26 contacts page tests pass | 1.1 | cc:完了 |
| 1.3 | Fix `settings/page.test.tsx` — diagnose import error, update mocks/selectors for any redesigned UI | All 41 settings tests pass | 1.1 | cc:完了 |
| 1.4 | Fix `message-editor.test.tsx` — update `onSend` callback test to match current signature | `onSend` test passes | - | cc:完了 |

---

## Phase 2: Cover Redesigned Components

| Task | Description | DoD | Depends | Status |
|------|-------------|-----|---------|--------|
| 2.1 | Test `InlineField` (contact detail) — default state shows value/link, hover shows pencil, click pencil opens edit mode, Cancel/Save buttons, Enter/Escape keys | ≥8 tests (18 written) | Phase 1 | cc:完了 |
| 2.2 | Test `InlineListField` — same patterns as InlineField but for arrays (emails, phones), displays "+N" for multiple values | ≥6 tests (13 written) | Phase 1 | cc:完了 |
| 2.3 | Test `nav.tsx` — hover dropdown opens/closes with delay, links render correctly, search opens command palette, notification badge | ≥8 tests (14 written) | Phase 1 | cc:完了 |
| 2.4 | Test `contact-avatar.tsx` — renders image when `avatar_url` exists, renders initials fallback, color mapping | ≥4 tests (18 written) | Phase 1 | cc:完了 |

---

## Phase 3: Cover Untested Pages (High Priority)

| Task | Description | DoD | Depends | Status |
|------|-------------|-----|---------|--------|
| 3.1 | Test `dashboard/page.tsx` — stat cards render with loading/data states, pending follow-ups section, recent activity, empty state | ≥10 tests (25 written) | Phase 2 | cc:完了 |
| 3.2 | Test `contacts/[id]/page.tsx` — header with name/avatar/tags, detail fields section, activity breakdown, kebab menu actions, duplicate card | ≥12 tests (36 written) | 2.1, 2.2 | cc:完了 |
| 3.3 | Test `suggestions/page.tsx` — suggestion cards render, snooze/dismiss/send actions, scheduled message state | ≥8 tests (21 written) | Phase 2 | cc:完了 |
| 3.4 | Test `contacts/archive/page.tsx` — loads archived contacts, unarchive button works, bulk select/unarchive, empty state | ≥6 tests (16 written) | Phase 2 | cc:完了 |

---

## Phase 4: Cover Untested Pages (Medium Priority)

| Task | Description | DoD | Depends | Status |
|------|-------------|-----|---------|--------|
| 4.1 | Test `identity/page.tsx` — scan button, duplicate pairs list, merge/dismiss actions | ≥6 tests (33 written) | Phase 3 | cc:完了 |
| 4.2 | Test `organizations/page.tsx` — org list renders, search, create org | ≥5 tests (19 written) | Phase 3 | cc:完了 |
| 4.3 | Test `notifications/page.tsx` — notification list, mark read, empty state | ≥5 tests (17 written) | Phase 3 | cc:完了 |
| 4.4 | Test `auth/register/page.tsx` — form validation, submit, redirect | ≥5 tests (8 written) | Phase 3 | cc:完了 |
| 4.5 | Test `contacts/new/page.tsx` — form fields, submit creates contact, validation | ≥5 tests (10 written) | Phase 3 | cc:完了 |

---

## Phase 5: Cover Remaining Components & Utilities

| Task | Description | DoD | Depends | Status |
|------|-------------|-----|---------|--------|
| 5.1 | Test `activity-breakdown.tsx` — score dimensions render, monthly trend chart, stats section | ≥5 tests (25 written) | Phase 4 | cc:完了 |
| 5.2 | Test `csv-import.tsx` — file upload, preview table, column mapping, submit | ≥6 tests (12 written) | Phase 4 | cc:完了 |
| 5.3 | Test `tag-taxonomy-panel.tsx` — tag list, add/remove/rename, category grouping | ≥5 tests (14 written) | Phase 4 | cc:完了 |
| 5.4 | Test hooks (`use-contacts`, `use-dashboard`, `use-suggestions`) — query key correctness, data transformation, error states | ≥8 tests (28 written) | Phase 4 | cc:完了 |

---

## Notes

- **Testing approach:** Behavior-driven (no snapshots), user-centric selectors (roles, labels), async-aware
- **Mock strategy:** Mock API client at module level, mock hooks for page-level tests, test components in isolation
- **Final result:** 27 test files, 477 tests, 0 failures
- **New tests added:** 327 (from 150 baseline after Phase 1 fixes)
