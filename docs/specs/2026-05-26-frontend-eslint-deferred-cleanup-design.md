# Frontend ESLint Deferred Cleanup — Design

**Issue:** [#79](https://github.com/sneg55/pingcrm/issues/79) — Frontend ESLint: deferred cleanup from strict-config rollout
**Date:** 2026-05-26
**Scope:** All three slices from #79, delivered as one bundled PR.

## Background

A strict ESLint flat config and per-edit lint hook (`.claude/hooks/lint-on-edit.sh`) were rolled out across `frontend/`, reducing errors from 1082 → 0 across 89 files with `tsc --noEmit` clean throughout. Three categories of work were deferred:

1. The plain `complexity` rule disabled because it overlapped (in spirit) with `sonarjs/cognitive-complexity` and flagged page-level components with wide-but-flat branching.
2. Five `body: X as any` casts in API hooks where frontend Input types diverge from generated body schemas on nullability and required fields.
3. Loose error-detail typing in `useUpdateContact`, which preserves raw merge-conflict payloads as `unknown` so the consumer can duck-type them.

This spec closes all three categories.

## Goals

- Re-enable the `complexity` ESLint rule at threshold 20.
- Remove all five `body: X as any` casts and their `eslint-disable-next-line` lines.
- Replace the duck-typed conflict error in `useUpdateContact` with a discriminated union.
- Reduce the `as any` count tracked by `frontend/scripts/check-as-any.sh`.

## Non-Goals

- Other ESLint rules currently disabled (`strict-boolean-expressions`, `no-unnecessary-condition`, `no-unnecessary-type-assertion`, `prefer-nullish-coalescing`, `import/no-unresolved`, `security/detect-object-injection`). They stay disabled with their existing rationale.
- The 11 sites with complexity 16–19 that pass at threshold 20.
- Issue [#78](https://github.com/sneg55/pingcrm/issues/78)'s structured `call_type` / `duration_seconds` schema change. The chat-timeline structural extraction in Slice 2 will isolate the call-rendering branch into a sub-component (making #78 a smaller follow-up), but the current `startsWith("Phone call")` parsing is kept.
- Backend changes.

## Design

### Slice 1 — Remove `body: X as any` casts (5 sites)

Five `// biome-ignore lint/suspicious/noExplicitAny ... body: X as any` sites currently bridge Input types and generated body schemas. Four are schema-divergence (Input nullability and required-field shape differ from the generated schema). One is openapi-fetch's typing limitation for form-encoded bodies. Each gets a different fix.

**Four mapper sites.** Add `frontend/src/lib/api-mappers.ts` with one mapper per Input → generated-schema pair. Each mapper explicitly:

- Converts `undefined` → `null` for nullable fields.
- Fills required-field defaults (e.g., `emails: input.emails ?? []`).

Hooks call the mapper instead of casting.

| Site | Mapper | Target schema |
|---|---|---|
| `hooks/use-contacts.ts:118` (`useCreateContact`) | `toContactCreateBody` | `components["schemas"]["ContactCreate"]` |
| `hooks/use-contacts.ts:197` (`useUpdateContact`) | `toContactUpdateBody` | `components["schemas"]["ContactUpdate"]` |
| `hooks/use-suggestions.ts:64` (`useUpdateSuggestion`) | `toSuggestionUpdateBody` | `components["schemas"]["SuggestionUpdateBody"]` |
| `app/organizations/[id]/page.tsx:98` (org update) | `toOrgUpdateBody` | `components["schemas"]["OrganizationUpdate"]` |

Each mapper gets a unit test asserting `undefined`→`null` for nullable fields and required-defaults for required arrays. Co-locate tests at `frontend/src/lib/api-mappers.test.ts`.

**One special case — login (`hooks/use-auth.tsx:69`).** This site is not a schema-divergence problem; it's openapi-fetch typing the body as the JSON shape (`Body_login_api_v1_auth_login_post`: `{ username, password, remember_me?, ... }`) while we pass a `URLSearchParams` because the endpoint is `application/x-www-form-urlencoded`. The runtime payload is already controlled by an explicit `bodySerializer: () => params` override.

Fix: pass a structurally-correct typed object for the `body` field (so the openapi-fetch generic resolves) and keep the `bodySerializer` override controlling the wire format:

```ts
const body = { username: email, password, ...(rememberMe ? { remember_me: "true" } : {}) };
const { data } = await client.POST("/api/v1/auth/login", {
  body,
  bodySerializer: () => params,
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
});
```

No cast, no `biome-ignore`. The `params` `URLSearchParams` object is still constructed and used by the serializer; only the type-system-facing `body` changes.

(`hooks/use-auth.tsx` `register` does *not* have an `as any` — it already passes a plain object.)

### Slice 2 — 16-site complexity refactor + re-enable rule

Verified failing set at threshold 20 (via `npx eslint --rule '{"complexity": ["error", 20]}'`):

| File:line | Function | Complexity |
|---|---|---|
| `app/contacts/[id]/_components/chat-timeline.tsx:226` | arrow fn (map callback) | 33 |
| `app/contacts/[id]/_components/header-card.tsx:132` | `HeaderCard` | 36 |
| `components/message-editor.tsx:51` | `MessageEditor` | 34 |
| `app/settings/_components/platform-cards/telegram-card.tsx:32` | `TelegramCard` | 33 |
| `components/tag-taxonomy-panel.tsx:49` | `TagTaxonomyPanel` | 30 |
| `app/contacts/_hooks/use-contacts-page.ts:9` | `useContactsPage` | 30 |
| `hooks/use-dashboard.ts:40` | `useDashboardStats` | 29 |
| `app/contacts/archive/page.tsx:57` | `ArchivedContactsInner` | 25 |
| `app/contacts/[id]/_components/message-composer-card.tsx:15` | `MessageComposerCard` | 24 |
| `app/dashboard/page.tsx:123` | `DashboardPage` | 24 |
| `app/identity/page.tsx:53` | `IdentityPageContent` | 23 |
| `app/settings/_components/shared.tsx:108` | `SyncResultPanel` | 23 |
| `app/identity/_components/match-card.tsx:34` | `ContactPanel` | 22 |
| `app/contacts/[id]/_components/duplicates-card.tsx:38` | `DuplicateRow` | 21 |
| `app/organizations/page.tsx:172` | `OrganizationsPageContent` | 21 |
| `app/settings/_components/platform-cards/google-card.tsx:28` | `GoogleCard` | 21 |

**Per-site strategy.** For each site, extract the most-branchy subtree(s) into a sub-component or sub-hook in the existing `_components/` or `_hooks/` folder until the parent drops below 20. Pick the smallest extraction that does the job — no gratuitous splitting. The 11 sites with complexity 16–19 stay as-is.

**Component sites.** Extract render branches into co-located sub-components. Example for `chat-timeline.tsx`: split the `.map()` callback into `<TimelineItem/>` (dispatcher) plus per-kind components `<MeetingBadge/>`, `<CallBadge/>`, `<EventBadge/>`, `<MessageBubble/>`. This is the issue's suggested split.

**Hook sites** (`useContactsPage`, `useDashboardStats`): extract per-concern slices into smaller hooks composed in the parent. Example for `useContactsPage`: `useContactsFilters`, `useContactsSelection`, etc. Exact slicing decided per-hook during implementation.

**chat-timeline.tsx and #78.** The extraction will isolate call rendering inside `<CallBadge/>`. The current `startsWith("Phone call")` / `startsWith("Video call")` parsing is preserved verbatim inside that component. Replacing it with structured `call_type` / `duration_seconds` fields requires a backend schema change and stays in #78.

**Config change.** In `frontend/eslint.config.mjs`:

```diff
- // Disabled: overlaps with sonarjs/cognitive-complexity. See GH #79.
- complexity: 'off',
+ complexity: ['error', 20],
```

### Slice 3 — Typed conflict error in `api-errors.ts`

`useUpdateContact` currently preserves the raw FastAPI `detail` payload as `unknown` because `contacts/[id]/page.tsx:83` reads `{ conflicting_contact: {...} }` when the backend rejects an update for merge-conflict reasons.

Add a discriminated union next to the existing `extractErrorMessage` helper:

```ts
// frontend/src/lib/api-errors.ts
export type ApiError =
  | { kind: 'plain'; message: string }
  | { kind: 'conflict'; message: string; conflictingContact: ConflictingContact };

export function extractApiError(err: unknown): ApiError | null { ... }
```

`ConflictingContact` is whatever shape the backend's conflict response uses — extract or import from the existing types in `contacts/[id]/page.tsx`.

`useUpdateContact` returns the typed `ApiError | null` instead of raw detail. `contacts/[id]/page.tsx:83` switches from duck-typing to `error.kind === 'conflict'`. `extractErrorMessage` stays exported (other callers) but is implemented in terms of `extractApiError`.

## File Manifest

**New files:**

- `frontend/src/lib/api-mappers.ts`
- `frontend/src/lib/api-mappers.test.ts`
- Per-site sub-components/hooks (exact paths decided during implementation, all co-located with their parent in existing `_components/` / `_hooks/` folders)

**Modified files:**

- `frontend/eslint.config.mjs` — re-enable `complexity` rule at 20
- `frontend/src/lib/api-errors.ts` — add `ApiError` union + `extractApiError`
- `frontend/src/hooks/use-auth.tsx` — typed `body` object for login + drop cast (no mapper)
- `frontend/src/hooks/use-contacts.ts` — use mappers + typed error
- `frontend/src/hooks/use-suggestions.ts` — use mapper
- `frontend/src/app/organizations/[id]/page.tsx` — use mapper
- `frontend/src/app/contacts/[id]/page.tsx` — consume `ApiError.kind`
- The 16 sites listed in Slice 2

## Verification

- `npx eslint 'src/**/*.{ts,tsx}'` clean with `complexity: ['error', 20]` enabled.
- `npx tsc --noEmit` clean.
- `bash scripts/check-as-any.sh` reports a lower count than baseline (5 casts removed; nothing introduced).
- `npm test` passes (new mapper tests plus existing suite).
- Manual smoke in browser using the real local account:
  - Create contact, update contact (both success and merge-conflict paths), register, login.
  - Compose suggestion, update organization.
  - Dashboard renders, contacts list renders, archive page renders, identity page renders.
  - Settings cards render (Telegram, Google), tag taxonomy editor works.

## Rollout

Single bundled PR. The lint re-enable can't land until all 16 refactors are done, so splitting forces a stacked sequence with the same total reviewer surface area for no benefit. Reviewer can pull commits in groups (mappers, error narrowing, refactors, config flip) if they prefer to step through.

## Risks

- **Refactor regressions.** Each extracted sub-component must preserve identical render output. Mitigation: manual smoke per affected page, plus the existing test suite.
- **Hook split changes referential identity of returned values.** Mitigation: keep parent hook's return shape identical; only the internal composition changes.
- **Mapper drift from generated schemas.** Future Pydantic field changes can break a mapper at type-check time, which is the intended safety net (vs. silent `as any`).
