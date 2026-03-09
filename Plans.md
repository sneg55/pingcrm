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

- [ ] `cc:TODO` Add tests for nav component (dropdown rendering, active state, submenu links)
- [ ] `cc:TODO` Add tests for archive page (renders, search, unarchive button)
- [ ] `cc:TODO` Add tests for identity page (scan, merge flow)

### 10.6 PKCE Verifier Storage (Medium)

- [ ] `cc:TODO` Move Twitter PKCE verifiers from in-memory dict to Redis (required for multi-worker production deployment)

### 10.7 Celery Beat Schedule Review (Low)

- [ ] `cc:TODO` Verify Telegram sync interval (12h) is appropriate post-split into 3 sub-tasks
- [ ] `cc:TODO` Consider adding Google Calendar sync to beat schedule (currently manual-only)

### 10.8 Docker Deployment (Low)

- [ ] `cc:TODO` Create `docker-compose.yml` with PostgreSQL, Redis, backend, frontend, Celery worker, Celery beat
- [ ] `cc:TODO` Create `Dockerfile` for backend and frontend

### 10.9 OpenAPI Schema Regeneration (Low)

- [ ] `cc:TODO` Regenerate `backend/openapi.json` and `frontend` openapi-fetch types to include new `archived_only` param and any other recent API changes

---

## Backlog: Feature Exploration (from GitHub Issues)

| Issue | Title | Priority |
|-------|-------|----------|
| #7 | MCP Server integration | Explore |
| #6 | Pre-meeting prep notifications | Explore |
| #5 | Two-way device contact sync | Explore |
| #4 | Sync with WhatsApp, iMessage | Explore |
