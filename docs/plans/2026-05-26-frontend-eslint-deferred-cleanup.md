# Frontend ESLint Deferred Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all three deferred categories from GitHub issue #79 in one bundled PR: remove five `body: X as any` casts, refactor 16 functions over ESLint complexity 20, re-enable the `complexity` rule at threshold 20, and replace the duck-typed merge-conflict error in `useUpdateContact` with a discriminated `ApiError` union.

**Architecture:** Three independent slices — typed-body mappers + a typed-body login fix; a discriminated `ApiError` type in `api-errors.ts`; per-site structural extraction of branchy subtrees into co-located sub-components/hooks until each parent drops below complexity 20. The lint rule flip lands last because it can't pass until all 16 sites are refactored.

**Tech Stack:** TypeScript, React 19, Vitest (`*.test.tsx` co-located), ESLint flat config in `frontend/eslint.config.mjs`, openapi-fetch (typed `client.POST/PUT/GET`), TanStack Query mutations.

**Spec:** `docs/specs/2026-05-26-frontend-eslint-deferred-cleanup-design.md`

**Working directory for all commands:** `frontend/` (run `cd frontend` once at the start of the session).

---

## Slice 1 — Remove `body: X as any` casts

### Task 1: Add `api-mappers.ts` module + `toContactCreateBody` mapper

**Files:**
- Create: `frontend/src/lib/api-mappers.ts`
- Create: `frontend/src/lib/api-mappers.test.ts`
- Modify: `frontend/src/hooks/use-contacts.ts:111-126` (`useCreateContact`)

**Context:**
- `ContactCreateInput` (in `use-contacts.ts:67-84`) has `emails?: string[]` and `phones?: string[]` (both optional).
- Generated `components["schemas"]["ContactCreate"]` requires `emails: string[]` and `phones: string[]`.
- Other fields are compatible (`Input` has `?: string`, schema has `?: string | null` — `undefined` is a structural subset of `string | null | undefined`).
- The cast bypasses the missing-required-fields error.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/api-mappers.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { ContactCreateInput } from "@/hooks/use-contacts";
import { toContactCreateBody } from "./api-mappers";

describe("toContactCreateBody", () => {
  it("defaults missing emails and phones to empty arrays", () => {
    const input: ContactCreateInput = { full_name: "Ada Lovelace" };
    const body = toContactCreateBody(input);
    expect(body.emails).toEqual([]);
    expect(body.phones).toEqual([]);
    expect(body.full_name).toBe("Ada Lovelace");
  });

  it("preserves provided emails and phones", () => {
    const input: ContactCreateInput = {
      emails: ["a@b.co"],
      phones: ["+1234"],
    };
    const body = toContactCreateBody(input);
    expect(body.emails).toEqual(["a@b.co"]);
    expect(body.phones).toEqual(["+1234"]);
  });

  it("passes through other optional fields unchanged", () => {
    const input: ContactCreateInput = {
      twitter_handle: "ada",
      title: "Mathematician",
    };
    const body = toContactCreateBody(input);
    expect(body.twitter_handle).toBe("ada");
    expect(body.title).toBe("Mathematician");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/lib/api-mappers.test.ts`
Expected: FAIL — `Cannot find module './api-mappers'` (file doesn't exist yet).

- [ ] **Step 3: Create the mapper**

Create `frontend/src/lib/api-mappers.ts`:

```ts
import type { components } from "./api-types";
import type { ContactCreateInput } from "@/hooks/use-contacts";

type Schemas = components["schemas"];

export function toContactCreateBody(
  input: ContactCreateInput
): Schemas["ContactCreate"] {
  return {
    ...input,
    emails: input.emails ?? [],
    phones: input.phones ?? [],
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/lib/api-mappers.test.ts`
Expected: PASS — 3 tests pass.

- [ ] **Step 5: Apply mapper in `useCreateContact`**

In `frontend/src/hooks/use-contacts.ts`, replace lines 111–126:

```ts
import { toContactCreateBody } from "@/lib/api-mappers";
// ...

export function useCreateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: ContactCreateInput) => {
      const { data } = await client.POST("/api/v1/contacts", {
        body: toContactCreateBody(input),
      });
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });
}
```

The two-line `biome-ignore` + `as any` comment block (lines 116–118) goes away.

- [ ] **Step 6: Verify typecheck and lint pass for the touched files**

Run: `npx tsc --noEmit`
Expected: clean — no errors.

Run: `npx eslint src/hooks/use-contacts.ts src/lib/api-mappers.ts src/lib/api-mappers.test.ts`
Expected: clean — no errors or warnings.

- [ ] **Step 7: Commit**

```bash
git add src/lib/api-mappers.ts src/lib/api-mappers.test.ts src/hooks/use-contacts.ts
git commit -m "refactor(frontend): replace useCreateContact as-any with toContactCreateBody mapper

Mapper defaults missing emails/phones to [] so the call typechecks
against the generated ContactCreate schema. Drops one biome-ignore.
Part of #79."
```

---

### Task 2: Add `toContactUpdateBody` mapper

**Files:**
- Modify: `frontend/src/lib/api-mappers.ts` (add export)
- Modify: `frontend/src/lib/api-mappers.test.ts` (add tests)
- Modify: `frontend/src/hooks/use-contacts.ts:183-227` (`useUpdateContact`)

**Context:**
- `useUpdateContact` accepts `input: Partial<ContactCreateInput>`.
- `ContactUpdate` schema is all-optional (`?: string | null` for every field). The cast was historical and may be removable as a plain pass-through, but a typed mapper is safer and self-documenting.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/lib/api-mappers.test.ts`:

```ts
import type { ContactCreateInput } from "@/hooks/use-contacts";
import { toContactUpdateBody } from "./api-mappers";

describe("toContactUpdateBody", () => {
  it("passes through a partial input unchanged", () => {
    const input: Partial<ContactCreateInput> = { full_name: "Ada Lovelace" };
    const body = toContactUpdateBody(input);
    expect(body).toEqual({ full_name: "Ada Lovelace" });
  });

  it("preserves empty array fields when explicitly provided", () => {
    const input: Partial<ContactCreateInput> = { emails: [], phones: [] };
    const body = toContactUpdateBody(input);
    expect(body.emails).toEqual([]);
    expect(body.phones).toEqual([]);
  });

  it("does not invent fields that were not provided", () => {
    const input: Partial<ContactCreateInput> = { priority_level: "high" };
    const body = toContactUpdateBody(input);
    expect("emails" in body).toBe(false);
    expect("phones" in body).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- src/lib/api-mappers.test.ts`
Expected: FAIL — `Cannot find name 'toContactUpdateBody'`.

- [ ] **Step 3: Add the mapper**

Append to `frontend/src/lib/api-mappers.ts`:

```ts
export function toContactUpdateBody(
  input: Partial<ContactCreateInput>
): Schemas["ContactUpdate"] {
  return { ...input };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- src/lib/api-mappers.test.ts`
Expected: PASS — 6 tests pass total.

- [ ] **Step 5: Apply mapper in `useUpdateContact`**

In `frontend/src/hooks/use-contacts.ts`, change lines 193–198:

```ts
const { data, error, response } = await client.PUT("/api/v1/contacts/{contact_id}", {
  params: { path: { contact_id: id } },
  body: toContactUpdateBody(input),
});
```

Add `toContactUpdateBody` to the existing import from `@/lib/api-mappers`.

The two-line `biome-ignore` + `as any` comment block goes away.

- [ ] **Step 6: Verify typecheck and lint pass**

Run: `npx tsc --noEmit`
Expected: clean.

Run: `npx eslint src/hooks/use-contacts.ts src/lib/api-mappers.ts src/lib/api-mappers.test.ts`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/lib/api-mappers.ts src/lib/api-mappers.test.ts src/hooks/use-contacts.ts
git commit -m "refactor(frontend): replace useUpdateContact as-any with toContactUpdateBody mapper

Drops one biome-ignore. Part of #79."
```

---

### Task 3: Add `toSuggestionUpdateBody` mapper

**Files:**
- Modify: `frontend/src/lib/api-mappers.ts` (add export)
- Modify: `frontend/src/lib/api-mappers.test.ts` (add tests)
- Modify: `frontend/src/hooks/use-suggestions.ts:48-75` (`useUpdateSuggestion`)

**Context:**
- `UpdateSuggestionInput` (in `use-suggestions.ts:31-36`) has `status?: ...` (optional).
- `SuggestionUpdateBody` schema requires `status: string`.
- The mapper must reject calls without `status`. Easiest: tighten the local input type to require `status`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/lib/api-mappers.test.ts`:

```ts
import { toSuggestionUpdateBody } from "./api-mappers";

describe("toSuggestionUpdateBody", () => {
  it("requires status (compile-time) and passes it through", () => {
    const body = toSuggestionUpdateBody({ status: "sent" });
    expect(body.status).toBe("sent");
  });

  it("preserves optional fields", () => {
    const body = toSuggestionUpdateBody({
      status: "snoozed",
      snooze_until: "2026-06-01T00:00:00Z",
      suggested_message: "Catch up soon?",
      suggested_channel: "email",
    });
    expect(body.snooze_until).toBe("2026-06-01T00:00:00Z");
    expect(body.suggested_message).toBe("Catch up soon?");
    expect(body.suggested_channel).toBe("email");
  });

  it("omits unset optional fields", () => {
    const body = toSuggestionUpdateBody({ status: "dismissed" });
    expect("snooze_until" in body).toBe(false);
    expect("suggested_message" in body).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- src/lib/api-mappers.test.ts`
Expected: FAIL — `Cannot find name 'toSuggestionUpdateBody'`.

- [ ] **Step 3: Add the mapper**

Append to `frontend/src/lib/api-mappers.ts`:

```ts
import type { UpdateSuggestionInput } from "@/hooks/use-suggestions";

export function toSuggestionUpdateBody(
  input: UpdateSuggestionInput & { status: NonNullable<UpdateSuggestionInput["status"]> }
): Schemas["SuggestionUpdateBody"] {
  return { ...input };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- src/lib/api-mappers.test.ts`
Expected: PASS — 9 tests pass total.

- [ ] **Step 5: Apply mapper in `useUpdateSuggestion`**

In `frontend/src/hooks/use-suggestions.ts`, change the mutation body to require `status` on `input` and call the mapper:

```ts
import { toSuggestionUpdateBody } from "@/lib/api-mappers";
// ...

export function useUpdateSuggestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      input,
    }: {
      id: string;
      input: UpdateSuggestionInput & { status: NonNullable<UpdateSuggestionInput["status"]> };
    }) => {
      const { data } = await client.PUT(
        "/api/v1/suggestions/{suggestion_id}",
        {
          params: { path: { suggestion_id: id } },
          body: toSuggestionUpdateBody(input),
        }
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["suggestions"] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", "overdue"] });
    },
  });
}
```

The two-line `biome-ignore` + `as any` comment block goes away.

- [ ] **Step 6: Verify typecheck and lint pass for the whole project**

Run: `npx tsc --noEmit`
Expected: clean. If any caller passes a status-less input, the type error will surface here — fix each caller to always pass `status` (it's already always passed in practice since the mutation only makes sense when changing status).

Run: `npx eslint src/hooks/use-suggestions.ts src/lib/api-mappers.ts`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/hooks/use-suggestions.ts src/lib/api-mappers.ts src/lib/api-mappers.test.ts
git commit -m "refactor(frontend): replace useUpdateSuggestion as-any with toSuggestionUpdateBody mapper

Tightens the input type to require status (matches generated schema).
Drops one biome-ignore. Part of #79."
```

---

### Task 4: Add `toOrgUpdateBody` mapper

**Files:**
- Modify: `frontend/src/lib/api-mappers.ts` (add export)
- Modify: `frontend/src/lib/api-mappers.test.ts` (add tests)
- Modify: `frontend/src/app/organizations/[id]/page.tsx:93-100, 155`

**Context:**
- `OrganizationData` (in `organizations/[id]/page.tsx:54`) has many read-only fields (`id`, `logo_url`, `contact_count`, `avg_relationship_score`, `total_interactions`, `last_interaction_at`, `contacts`) that don't exist in `OrganizationUpdate`.
- Mapper must whitelist only the updatable fields.

- [ ] **Step 1: Define an exported updatable-subset type**

In `frontend/src/app/organizations/[id]/page.tsx`, add (above the existing `type OrganizationData = ...`):

```ts
export type OrganizationUpdateInput = {
  name?: string | null;
  domain?: string | null;
  industry?: string | null;
  location?: string | null;
  website?: string | null;
  linkedin_url?: string | null;
  twitter_handle?: string | null;
  notes?: string | null;
};
```

- [ ] **Step 2: Write the failing tests**

Append to `frontend/src/lib/api-mappers.test.ts`:

```ts
import { toOrgUpdateBody } from "./api-mappers";
import type { OrganizationUpdateInput } from "@/app/organizations/[id]/page";

describe("toOrgUpdateBody", () => {
  it("passes through whitelisted fields", () => {
    const input: OrganizationUpdateInput = {
      name: "Acme",
      domain: "acme.com",
      notes: "Big customer",
    };
    const body = toOrgUpdateBody(input);
    expect(body).toEqual({ name: "Acme", domain: "acme.com", notes: "Big customer" });
  });

  it("preserves null values (clearing a field)", () => {
    const input: OrganizationUpdateInput = { website: null };
    const body = toOrgUpdateBody(input);
    expect(body.website).toBeNull();
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `npm test -- src/lib/api-mappers.test.ts`
Expected: FAIL — `Cannot find name 'toOrgUpdateBody'`.

- [ ] **Step 4: Add the mapper**

Append to `frontend/src/lib/api-mappers.ts`:

```ts
import type { OrganizationUpdateInput } from "@/app/organizations/[id]/page";

export function toOrgUpdateBody(
  input: OrganizationUpdateInput
): Schemas["OrganizationUpdate"] {
  return { ...input };
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- src/lib/api-mappers.test.ts`
Expected: PASS — 11 tests pass total.

- [ ] **Step 6: Apply mapper in the org-update mutation**

In `frontend/src/app/organizations/[id]/page.tsx`, locate the mutation around lines 92–100 and change to:

```ts
import { toOrgUpdateBody } from "@/lib/api-mappers";
// ...

mutationFn: async (updates: OrganizationUpdateInput) => {
  // ...existing call shape...
  body: toOrgUpdateBody(updates),
  // ...
},
```

Also update line 155 (`updateMutation.mutate({ [field]: value } as Partial<OrganizationData>);`) to drop the cast — typed as `OrganizationUpdateInput` now:

```ts
updateMutation.mutate({ [field]: value } as OrganizationUpdateInput);
```

(If the inline-call sites pass fields that aren't in `OrganizationUpdateInput`, the typechecker will flag them — fix them by either widening `OrganizationUpdateInput` or restricting the call.)

The `biome-ignore` + `as any` block at lines 97–98 goes away.

- [ ] **Step 7: Verify typecheck and lint pass**

Run: `npx tsc --noEmit`
Expected: clean.

Run: `npx eslint 'src/app/organizations/[id]/page.tsx' src/lib/api-mappers.ts`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add 'src/app/organizations/[id]/page.tsx' src/lib/api-mappers.ts src/lib/api-mappers.test.ts
git commit -m "refactor(frontend): replace org update as-any with toOrgUpdateBody mapper

Adds explicit OrganizationUpdateInput whitelisting updatable fields.
Drops one biome-ignore. Part of #79."
```

---

### Task 5: Fix login body typing (no mapper)

**Files:**
- Modify: `frontend/src/hooks/use-auth.tsx:60-83` (`login`)

**Context:**
- This is not a schema-divergence problem; openapi-fetch types the `body` field as the JSON shape `Body_login_api_v1_auth_login_post: { username, password, remember_me? }` even though the endpoint is `application/x-www-form-urlencoded`.
- The actual wire payload is already controlled by an explicit `bodySerializer: () => params` override using a `URLSearchParams` instance.
- Fix: pass a structurally-correct typed object for `body` so the openapi-fetch generic resolves; keep the `bodySerializer` override.

- [ ] **Step 1: Replace the login body**

In `frontend/src/hooks/use-auth.tsx`, change lines 60–72:

```ts
const login = useCallback(async (email: string, password: string, rememberMe?: boolean) => {
  const params = new URLSearchParams();
  params.set("username", email);
  params.set("password", password);
  if (rememberMe) params.set("remember_me", "true");

  const { data } = await client.POST("/api/v1/auth/login", {
    body: {
      username: email,
      password,
      ...(rememberMe ? { remember_me: "true" } : {}),
    },
    bodySerializer: () => params,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  // ...rest of function unchanged...
```

The `biome-ignore` + `as any` (lines 68–69) goes away. The `URLSearchParams` instance still exists and is what gets sent on the wire via `bodySerializer`.

- [ ] **Step 2: Verify typecheck and lint pass**

Run: `npx tsc --noEmit`
Expected: clean — the openapi-fetch generic should accept the structurally-correct object.

Run: `npx eslint src/hooks/use-auth.tsx`
Expected: clean.

- [ ] **Step 3: Smoke-test login manually**

Start dev server (`npm run dev` in a separate terminal) and log in at http://localhost:3000/auth/login with the local test credentials (see `CLAUDE.local.md`). Confirm:

- Login succeeds and you land on the dashboard.
- "Remember me" checkbox round-trip works (toggle on, log in, log out, log back in).

- [ ] **Step 4: Verify the `as any` count dropped**

Run: `bash scripts/check-as-any.sh`
Expected: count dropped by 5 from baseline (one per Task 1–5).

- [ ] **Step 5: Commit**

```bash
git add src/hooks/use-auth.tsx
git commit -m "refactor(frontend): type the form-encoded login body explicitly

Pass a JSON-shaped body that satisfies openapi-fetch's typing; keep
the bodySerializer override controlling the wire format. Drops the
last biome-ignore from the as-any cleanup. Closes the as-any portion
of #79."
```

---

## Slice 3 — Typed `ApiError` discriminated union

### Task 6: Add `ApiError` union + `extractApiError` to `api-errors.ts`

**Files:**
- Modify: `frontend/src/lib/api-errors.ts`
- Create: `frontend/src/lib/api-errors.test.ts`

**Context:**
- `extractErrorMessage` currently extracts a display string from FastAPI's `detail: string | ValidationError[]` shape.
- `useUpdateContact` separately preserves the raw `detail` so a downstream consumer at `app/contacts/[id]/page.tsx` can read `{ conflicting_contact: {...} }` on merge-conflict errors.
- We add a typed discriminator so the consumer can switch on `kind` instead of duck-typing `detail`.

- [ ] **Step 1: Read the existing api-errors.ts**

Run: `cat src/lib/api-errors.ts`

Understand the current `extractErrorMessage` shape so the new code keeps the existing export working.

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/lib/api-errors.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { extractApiError, type ConflictingContact } from "./api-errors";

describe("extractApiError", () => {
  it("returns null for nullish input", () => {
    expect(extractApiError(null)).toBeNull();
    expect(extractApiError(undefined)).toBeNull();
  });

  it("returns a plain error for FastAPI string detail", () => {
    const result = extractApiError({ detail: "Contact not found" });
    expect(result).toEqual({ kind: "plain", message: "Contact not found" });
  });

  it("returns a plain error for FastAPI validation detail", () => {
    const result = extractApiError({
      detail: [{ loc: ["body", "emails"], msg: "field required", type: "value_error.missing" }],
    });
    expect(result?.kind).toBe("plain");
    expect(result?.message).toContain("field required");
  });

  it("returns a conflict error when detail includes conflicting_contact", () => {
    const conflictingContact: ConflictingContact = {
      id: "abc-123",
      full_name: "Ada Lovelace",
    };
    const result = extractApiError({
      detail: {
        message: "Email already used by another contact",
        conflicting_contact: conflictingContact,
      },
    });
    expect(result).toEqual({
      kind: "conflict",
      message: "Email already used by another contact",
      conflictingContact,
    });
  });

  it("returns a plain error for unknown error shapes", () => {
    const result = extractApiError({ some: "weird shape" });
    expect(result?.kind).toBe("plain");
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `npm test -- src/lib/api-errors.test.ts`
Expected: FAIL — `extractApiError` / `ConflictingContact` not exported.

- [ ] **Step 4: Implement the types and function**

Modify `frontend/src/lib/api-errors.ts`. Add:

```ts
export type ConflictingContact = {
  id: string;
  full_name?: string | null;
  given_name?: string | null;
  family_name?: string | null;
  emails?: string[] | null;
};

export type ApiError =
  | { kind: "plain"; message: string }
  | { kind: "conflict"; message: string; conflictingContact: ConflictingContact };

export function extractApiError(err: unknown): ApiError | null {
  if (err == null) return null;

  // FastAPI envelope: { detail: ... }
  if (typeof err === "object" && "detail" in err) {
    const detail = (err as { detail: unknown }).detail;

    // Structured conflict: { detail: { message, conflicting_contact } }
    if (
      detail != null &&
      typeof detail === "object" &&
      !Array.isArray(detail) &&
      "conflicting_contact" in detail
    ) {
      const d = detail as {
        message?: unknown;
        conflicting_contact: ConflictingContact;
      };
      return {
        kind: "conflict",
        message: typeof d.message === "string" ? d.message : "Conflict",
        conflictingContact: d.conflicting_contact,
      };
    }

    // String detail
    if (typeof detail === "string") {
      return { kind: "plain", message: detail };
    }

    // Validation array
    if (Array.isArray(detail)) {
      const msg = detail
        .map((item) =>
          item != null && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : String(item)
        )
        .join("; ");
      return { kind: "plain", message: msg };
    }
  }

  // Generic Error
  if (err instanceof Error) {
    return { kind: "plain", message: err.message };
  }

  return { kind: "plain", message: "An unexpected error occurred" };
}
```

Keep `extractErrorMessage` exported. Replace its body with:

```ts
export function extractErrorMessage(err: unknown): string | undefined {
  const apiError = extractApiError(err);
  return apiError?.message;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- src/lib/api-errors.test.ts`
Expected: PASS — 5 tests pass.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `npm test`
Expected: all tests pass (existing `extractErrorMessage` callers continue to work).

- [ ] **Step 7: Verify typecheck and lint pass**

Run: `npx tsc --noEmit`
Expected: clean.

Run: `npx eslint src/lib/api-errors.ts src/lib/api-errors.test.ts`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/lib/api-errors.ts src/lib/api-errors.test.ts
git commit -m "feat(frontend): add typed ApiError discriminated union to api-errors

Adds extractApiError() returning a 'plain' | 'conflict' union so
consumers can switch on kind instead of duck-typing the FastAPI
detail payload. extractErrorMessage is preserved as a thin wrapper.
Part of #79."
```

---

### Task 7: Switch `useUpdateContact` + `contacts/[id]/page.tsx` to typed `ApiError`

**Files:**
- Modify: `frontend/src/hooks/use-contacts.ts:183-227` (`useUpdateContact`)
- Modify: `frontend/src/app/contacts/[id]/page.tsx` (existing consumer around line 83 per spec — verify exact line)

**Context:**
- `useUpdateContact` currently throws an `Error` decorated with `status` and `detail: unknown`. The caller duck-types `detail.conflicting_contact`.
- After this task, the thrown error carries a typed `ApiError` instead.

- [ ] **Step 1: Locate the existing consumer in `contacts/[id]/page.tsx`**

Run: `grep -n "conflicting_contact\|detail" src/app/contacts/\[id\]/page.tsx`

Note the line range that reads `detail.conflicting_contact`. The spec referenced line 83, but lines may have shifted.

- [ ] **Step 2: Update `useUpdateContact` to throw a typed error**

In `frontend/src/hooks/use-contacts.ts`, replace lines 199–205 (inside `useUpdateContact`):

```ts
import { extractApiError, type ApiError } from "@/lib/api-errors";
// ...

if (error) {
  const apiError = extractApiError(error) ?? { kind: "plain" as const, message: "Update failed" };
  const err = new Error(apiError.message) as Error & {
    status?: number;
    apiError: ApiError;
  };
  err.status = response.status;
  err.apiError = apiError;
  throw err;
}
```

(Remove the `detail` field; keep `status`. The `apiError` property carries the typed payload.)

- [ ] **Step 3: Update the consumer in `contacts/[id]/page.tsx`**

Change the duck-type check from reading `detail.conflicting_contact` to switching on `apiError.kind`. Example shape (adjust to fit existing surrounding code):

```ts
import type { ApiError } from "@/lib/api-errors";

// In the mutation onError or catch handler:
const apiError = (err as Error & { apiError?: ApiError }).apiError;
if (apiError?.kind === "conflict") {
  // existing merge-flow UI using apiError.conflictingContact
  setMergeCandidate(apiError.conflictingContact);
} else {
  toast.error(apiError?.message ?? "Update failed");
}
```

(The exact branch shape depends on the existing code — adjust accordingly. The key is reading `apiError.conflictingContact` instead of casting `detail`.)

- [ ] **Step 4: Verify typecheck passes**

Run: `npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Run the full test suite**

Run: `npm test`
Expected: all tests pass.

- [ ] **Step 6: Smoke-test the merge-conflict flow manually**

Start dev server. Create two contacts with overlapping emails (or use existing test data). Edit one to reuse the other's email and confirm:

- The merge-prompt UI appears (was previously triggered by the duck-typed `conflicting_contact` read).
- Cancelling and confirming both work.
- Plain validation errors (e.g., invalid email format) show a toast and don't trigger the merge UI.

- [ ] **Step 7: Verify lint passes**

Run: `npx eslint src/hooks/use-contacts.ts 'src/app/contacts/[id]/page.tsx'`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/hooks/use-contacts.ts 'src/app/contacts/[id]/page.tsx'
git commit -m "refactor(frontend): consume typed ApiError in useUpdateContact + merge flow

Throws an Error decorated with apiError: ApiError instead of raw
detail: unknown. Merge-conflict UI now reads apiError.conflictingContact
via the discriminator instead of duck-typing. Part of #79."
```

---

## Slice 2 — 16-site complexity refactor

**Common pattern for every refactor task in this slice:**

1. Read the parent function and locate the most-branchy subtree(s) — usually a render branch with many conditionals, a kebab/dropdown menu, or a list of cards with per-item state.
2. Extract that subtree into a co-located sub-component (in the existing `_components/` folder) or sub-hook (in `_hooks/`), with a typed props interface.
3. Replace the subtree in the parent with a `<SubComponent {...props}/>` call.
4. Verify the parent's complexity dropped below 20.
5. Verify `tsc --noEmit` clean.
6. Run `npm test` to confirm any existing component tests still pass.
7. Manually smoke the affected page.
8. Commit.

**Per-site verification command** (substitute `<path>` with the file path):

```bash
npx eslint --rule '{"complexity": ["error", 20]}' <path>
```

Expected: clean (the parent's `complexity` error is gone). Other files may still fail this check — that's fine; they get fixed in later tasks. The rule won't be re-enabled in `eslint.config.mjs` until Task 24.

---

### Task 8: Refactor `HeaderCard` (complexity 36)

**Files:**
- Modify: `frontend/src/app/contacts/[id]/_components/header-card.tsx` (the `HeaderCard` function starting line 132)
- Create: `frontend/src/app/contacts/[id]/_components/header-actions-menu.tsx`
- Create: `frontend/src/app/contacts/[id]/_components/avatar-modal.tsx`

**Extraction plan:**
- `<HeaderActionsMenu/>` — the kebab dropdown subtree (lines ~333–407): contains 5 conditional menu items (Refresh, Enrich, Auto-tag, Promote-if-2nd-tier, Delete), the click-outside effect, and the `menuOpen` state.
- `<AvatarModal/>` — the portal modal subtree (lines ~412–438): contains `showAvatarModal` state, the Escape-key effect (lines 168–175), and the portal JSX.

Both extractions hoist their state and effects into the sub-component. The parent passes `contact` and any callbacks it needs.

- [ ] **Step 1: Create `header-actions-menu.tsx`**

Create `frontend/src/app/contacts/[id]/_components/header-actions-menu.tsx`. Move the kebab menu JSX and its supporting state/effect into it. Props:

```ts
type HeaderActionsMenuProps = {
  contact: Contact;
  isRefreshing: boolean;
  isEnriching: boolean;
  isAutoTagging: boolean;
  is2ndTier: boolean;
  isPromoting?: boolean;
  onRefreshDetails: () => void;
  onEnrich: () => void;
  onAutoTag: () => void;
  onShowDeleteConfirm: () => void;
  onPromote?: () => void;
};
```

(Import `Contact` from `@/hooks/use-contacts` or wherever it lives.)

- [ ] **Step 2: Create `avatar-modal.tsx`**

Create `frontend/src/app/contacts/[id]/_components/avatar-modal.tsx`. Move the portal modal JSX, the `showAvatarModal` state, and the Escape-key effect. Props:

```ts
type AvatarModalProps = {
  avatarUrl: string;
  displayName: string;
};
```

Internally manage `open` state via an exposed `<AvatarThumbnail/>` trigger button, or accept `open` + `onClose` as props. Pick whichever leaves the parent simpler.

- [ ] **Step 3: Wire the sub-components into `HeaderCard`**

In `header-card.tsx`:
- Remove the kebab menu JSX + `menuOpen` state + click-outside effect; replace with `<HeaderActionsMenu .../>`.
- Remove the portal modal JSX + `showAvatarModal` state + Escape effect; replace the avatar `<button>` + portal with `<AvatarModal avatarUrl={contact.avatar_url ?? undefined} displayName={displayName}/>` (or the chosen API).

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' 'src/app/contacts/[id]/_components/header-card.tsx'`
Expected: no `complexity` error on `HeaderCard`.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit`
Expected: clean.

Run: `npm test`
Expected: all tests pass.

- [ ] **Step 6: Smoke-test the contact detail page**

Start dev server. Open a contact detail page. Confirm:
- Avatar click opens the full-size modal; Escape closes it; click outside closes it.
- Kebab menu opens and closes; click outside closes it.
- Refresh, Enrich, Auto-tag, Promote (for 2nd-tier contacts), Delete all still work.

- [ ] **Step 7: Commit**

```bash
git add 'src/app/contacts/[id]/_components/header-card.tsx' 'src/app/contacts/[id]/_components/header-actions-menu.tsx' 'src/app/contacts/[id]/_components/avatar-modal.tsx'
git commit -m "refactor(frontend): split HeaderCard into HeaderActionsMenu + AvatarModal

Extracts the kebab dropdown and the portal modal into sub-components,
each owning its local state and effects. Drops HeaderCard complexity
below 20. Part of #79."
```

---

### Task 9: Refactor `MessageEditor` (complexity 34)

**Files:**
- Modify: `frontend/src/components/message-editor.tsx` (`MessageEditor` starting line 51)
- Create: 1–2 sub-components in `frontend/src/components/message-editor-parts/` (folder name your choice — e.g., `message-editor-toolbar.tsx`, `message-editor-channel-picker.tsx`)

**Extraction plan:**
- Read the file (`cat src/components/message-editor.tsx`) and identify the largest branchy subtree. Common candidates in message editors: a channel/tone picker dropdown, a toolbar with many conditional buttons (preview, send, schedule, draft), or per-channel input rendering (email subject vs. telegram-only vs. twitter).
- Extract one or two of these into co-located sub-components.

- [ ] **Step 1: Read the file and identify extraction target**

Run: `cat src/components/message-editor.tsx | head -200`

Pick the most branch-dense subtree(s) (typically the largest conditional JSX block or a per-channel switch).

- [ ] **Step 2: Create sub-component(s)**

Create the chosen sub-component file(s) in `frontend/src/components/` (e.g., `message-editor-toolbar.tsx`). Move the JSX and any local state/effects that only that subtree uses. Define a typed props interface.

- [ ] **Step 3: Wire sub-component(s) into `MessageEditor`**

Replace the moved JSX in `message-editor.tsx` with the sub-component call(s).

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/components/message-editor.tsx`
Expected: no `complexity` error on `MessageEditor`.

- [ ] **Step 5: Verify typecheck and existing test pass**

Run: `npx tsc --noEmit`
Expected: clean.

Run: `npm test -- src/components/message-editor.test.tsx`
Expected: PASS — existing tests cover the extracted behavior.

Run: `npm test`
Expected: all tests pass.

- [ ] **Step 6: Smoke-test message composition**

Start dev server. Open a contact detail page. Use the message composer to compose a draft, switch channels, edit tone if available, send/save. Confirm parity with previous behavior.

- [ ] **Step 7: Commit**

```bash
git add src/components/message-editor.tsx src/components/message-editor-*.tsx
git commit -m "refactor(frontend): split MessageEditor into sub-components

Drops MessageEditor complexity below 20. Existing test coverage in
message-editor.test.tsx still passes. Part of #79."
```

---

### Task 10: Refactor `chat-timeline.tsx` map callback (complexity 33)

**Files:**
- Modify: `frontend/src/app/contacts/[id]/_components/chat-timeline.tsx` (the `.map()` arrow at line 226)
- Create: `frontend/src/app/contacts/[id]/_components/timeline-item.tsx`

**Extraction plan (per spec):**
- Extract the entire `.map()` arrow body into a `<TimelineItem/>` component that takes one `item` and the surrounding callbacks.
- Inside `<TimelineItem/>`, split call rendering into `<CallBadge/>` (preserving the current `startsWith("Phone call")` parsing verbatim — #78 will replace it later).
- Optionally further split into `<MeetingBadge/>`, `<EventBadge/>`, `<MessageBubble/>` if `<TimelineItem/>` is still above 20.

- [ ] **Step 1: Read the map callback**

Run: `sed -n '220,310p' 'src/app/contacts/[id]/_components/chat-timeline.tsx'`

Understand the dispatcher logic (`isCall`, `isMeeting`, `isEvent`, etc.).

- [ ] **Step 2: Create `<TimelineItem/>`**

Create `frontend/src/app/contacts/[id]/_components/timeline-item.tsx`. Move the map callback body inside a function component. Props are the `item` plus any callbacks the body references (e.g., `onEdit`, `onDelete`, etc.).

- [ ] **Step 3: If `<TimelineItem/>` is still above complexity 20, split further**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' 'src/app/contacts/[id]/_components/timeline-item.tsx'`

If it fails, extract `<CallBadge/>` (keeps the `startsWith` parsing), `<MeetingBadge/>`, `<EventBadge/>`, `<MessageBubble/>` into the same folder. Each takes the relevant slice of `item` as props.

- [ ] **Step 4: Replace the map callback in `chat-timeline.tsx`**

```tsx
{items.map((item) => (
  <TimelineItem key={item.id} item={item} /* ...callbacks... */ />
))}
```

- [ ] **Step 5: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' 'src/app/contacts/[id]/_components/chat-timeline.tsx' 'src/app/contacts/[id]/_components/timeline-item.tsx'`
Expected: clean.

- [ ] **Step 6: Verify typecheck and tests pass**

Run: `npx tsc --noEmit`
Expected: clean.

Run: `npm test -- src/components/timeline.test.tsx`
Expected: PASS (existing timeline tests).

Run: `npm test`
Expected: all tests pass.

- [ ] **Step 7: Smoke-test the contact detail page timeline**

Start dev server. Open a contact with a varied history (messages, meetings, calls, events). Confirm all item types render identically: call duration display, meeting attendees, event tags, message bubbles inbound vs. outbound.

- [ ] **Step 8: Commit**

```bash
git add 'src/app/contacts/[id]/_components/chat-timeline.tsx' 'src/app/contacts/[id]/_components/timeline-item.tsx' 'src/app/contacts/[id]/_components/'*.tsx
git commit -m "refactor(frontend): extract TimelineItem from chat-timeline map callback

Splits the inline map callback into TimelineItem (and optionally
CallBadge/MeetingBadge/EventBadge/MessageBubble). Preserves the
existing startsWith() call-type parsing inside CallBadge for #78
to replace later. Part of #79."
```

---

### Task 11: Refactor `TelegramCard` (complexity 33)

**Files:**
- Modify: `frontend/src/app/settings/_components/platform-cards/telegram-card.tsx` (`TelegramCard` starting line 32)
- Create: 1–2 sub-components in the same folder (e.g., `telegram-card-auth-flow.tsx`, `telegram-card-status.tsx`)

**Extraction plan:**
- Read the file. Identify the largest branchy subtree(s) — typically the auth flow (phone → code → 2FA), the connected-status panel, or the sync-result rendering.
- Extract one branch (probably the auth flow) into a sub-component.

- [ ] **Step 1: Read the file**

Run: `cat 'src/app/settings/_components/platform-cards/telegram-card.tsx'`

- [ ] **Step 2: Create sub-component(s)**

Create the sub-component file(s) in the same folder. Move the JSX and any local state for that branch.

- [ ] **Step 3: Wire sub-component(s) into `TelegramCard`**

Replace the moved JSX with the sub-component call(s).

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' 'src/app/settings/_components/platform-cards/telegram-card.tsx'`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all tests pass.

- [ ] **Step 6: Smoke-test settings → Telegram**

Start dev server. Open Settings page. Open Telegram card. Confirm: connected status renders, disconnect button works, reconnect / pair flow renders the right step (without actually disconnecting).

- [ ] **Step 7: Commit**

```bash
git add 'src/app/settings/_components/platform-cards/telegram-card.tsx' 'src/app/settings/_components/platform-cards/telegram-card-'*.tsx
git commit -m "refactor(frontend): split TelegramCard into sub-components

Drops TelegramCard complexity below 20. Part of #79."
```

---

### Task 12: Refactor `TagTaxonomyPanel` (complexity 30)

**Files:**
- Modify: `frontend/src/components/tag-taxonomy-panel.tsx` (`TagTaxonomyPanel` starting line 49)
- Create: 1–2 sub-components in `frontend/src/components/` (e.g., `tag-taxonomy-row.tsx`)

**Extraction plan:**
- Read the file. Identify the most-branchy subtree (typically per-tag row with inline edit/delete/rename state, or the create-new-tag input row).
- Extract that subtree.

- [ ] **Step 1: Read the file**

Run: `cat src/components/tag-taxonomy-panel.tsx`

- [ ] **Step 2: Create sub-component(s)**

Create the sub-component file(s) in `frontend/src/components/`. Move JSX and local state.

- [ ] **Step 3: Wire sub-component(s) into `TagTaxonomyPanel`**

Replace the moved JSX with the sub-component call(s).

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/components/tag-taxonomy-panel.tsx`
Expected: clean.

- [ ] **Step 5: Verify typecheck and existing test pass**

Run: `npx tsc --noEmit`
Expected: clean.

Run: `npm test -- src/components/tag-taxonomy-panel.test.tsx`
Expected: PASS (existing tests).

Run: `npm test`
Expected: all pass.

- [ ] **Step 6: Smoke-test the tag taxonomy editor**

Start dev server. Find the tag taxonomy editor (Settings or a contact detail page — check existing routing). Add a tag, rename a tag, delete a tag. Confirm behavior.

- [ ] **Step 7: Commit**

```bash
git add src/components/tag-taxonomy-panel.tsx src/components/tag-taxonomy-*.tsx
git commit -m "refactor(frontend): split TagTaxonomyPanel into sub-components

Drops TagTaxonomyPanel complexity below 20. Existing test coverage
in tag-taxonomy-panel.test.tsx still passes. Part of #79."
```

---

### Task 13: Refactor `useContactsPage` (complexity 30, hook)

**Files:**
- Modify: `frontend/src/app/contacts/_hooks/use-contacts-page.ts` (`useContactsPage` starting line 9)
- Create: 1–2 sub-hooks in the same folder (e.g., `use-contacts-filters.ts`, `use-contacts-selection.ts`)

**Extraction plan:**
- Read the hook. Identify groups of related state/effects (filters, selection, pagination, etc.).
- Extract one group into a sub-hook that returns the same shape used by the parent.

- [ ] **Step 1: Read the hook**

Run: `cat src/app/contacts/_hooks/use-contacts-page.ts`

- [ ] **Step 2: Create sub-hook(s)**

Create the sub-hook file(s) in the same folder. Move the related state/effects/handlers. Each sub-hook returns an object that the parent destructures.

- [ ] **Step 3: Compose sub-hook(s) into `useContactsPage`**

Replace the moved code with `const { ... } = useContactsFilters(...);` (etc.). The parent's external return shape stays identical.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/app/contacts/_hooks/use-contacts-page.ts`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all tests pass.

- [ ] **Step 6: Smoke-test the contacts page**

Start dev server. Open /contacts. Confirm: search, filters (tag, source, priority, score, date), sort, pagination, selection (single + bulk), bulk actions all work.

- [ ] **Step 7: Commit**

```bash
git add src/app/contacts/_hooks/
git commit -m "refactor(frontend): split useContactsPage into focused sub-hooks

Decomposes useContactsPage into smaller hooks composed together so the
parent stays under complexity 20. External return shape unchanged.
Part of #79."
```

---

### Task 14: Refactor `useDashboardStats` (complexity 29, hook)

**Files:**
- Modify: `frontend/src/hooks/use-dashboard.ts` (`useDashboardStats` starting line 40)
- Create: 1–2 sub-hooks in the same folder (e.g., `use-dashboard-aggregates.ts`)

**Extraction plan:**
- Read the hook. Identify groups of related queries / derived state.
- Extract one group into a sub-hook.

- [ ] **Step 1: Read the hook**

Run: `cat src/hooks/use-dashboard.ts`

- [ ] **Step 2: Create sub-hook(s)**

Create sub-hook file(s) in `frontend/src/hooks/`. Move related queries / state.

- [ ] **Step 3: Compose sub-hook(s) into `useDashboardStats`**

Replace moved code with sub-hook calls. Return shape stays identical.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/hooks/use-dashboard.ts`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test the dashboard**

Start dev server. Open /dashboard. Confirm: all widgets render with stats (contact count, interactions, suggestions, etc.), no console errors.

- [ ] **Step 7: Commit**

```bash
git add src/hooks/use-dashboard.ts src/hooks/use-dashboard-*.ts
git commit -m "refactor(frontend): split useDashboardStats into focused sub-hooks

Drops useDashboardStats complexity below 20. External return shape
unchanged. Part of #79."
```

---

### Task 15: Refactor `ArchivedContactsInner` (complexity 25)

**Files:**
- Modify: `frontend/src/app/contacts/archive/page.tsx` (`ArchivedContactsInner` starting line 57)
- Create: 1 sub-component in `frontend/src/app/contacts/archive/_components/` (create folder if absent)

**Extraction plan:**
- Read the function. Identify the branchy subtree (typically a table row component or per-contact card with inline restore/delete state).
- Extract it.

- [ ] **Step 1: Read the file**

Run: `cat src/app/contacts/archive/page.tsx`

- [ ] **Step 2: Create the sub-component**

Create `frontend/src/app/contacts/archive/_components/<name>.tsx`. Move the chosen subtree.

- [ ] **Step 3: Wire sub-component into `ArchivedContactsInner`**

Replace the moved JSX with the sub-component call.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/app/contacts/archive/page.tsx`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test the archive page**

Start dev server. Open /contacts/archive. Confirm: archived contacts listed, restore button works, permanent delete works.

- [ ] **Step 7: Commit**

```bash
git add src/app/contacts/archive/
git commit -m "refactor(frontend): split ArchivedContactsInner into a sub-component

Drops complexity below 20. Part of #79."
```

---

### Task 16: Refactor `MessageComposerCard` (complexity 24)

**Files:**
- Modify: `frontend/src/app/contacts/[id]/_components/message-composer-card.tsx` (`MessageComposerCard` starting line 15)
- Create: 1 sub-component in the same folder

**Extraction plan:**
- Read the file. Identify the branchy subtree (likely the AI-suggestion preview / channel-selector / tone-selector subtree).
- Extract it.

- [ ] **Step 1: Read the file**

Run: `cat 'src/app/contacts/[id]/_components/message-composer-card.tsx'`

- [ ] **Step 2: Create the sub-component**

Create the sub-component file in the same folder. Move the chosen subtree.

- [ ] **Step 3: Wire sub-component into `MessageComposerCard`**

Replace the moved JSX with the sub-component call.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' 'src/app/contacts/[id]/_components/message-composer-card.tsx'`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test the composer on a contact detail page**

Start dev server. Open a contact detail page. Compose a message, switch channel, regenerate AI suggestion if available. Confirm parity.

- [ ] **Step 7: Commit**

```bash
git add 'src/app/contacts/[id]/_components/'
git commit -m "refactor(frontend): split MessageComposerCard into a sub-component

Drops complexity below 20. Part of #79."
```

---

### Task 17: Refactor `DashboardPage` (complexity 24)

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx` (`DashboardPage` starting line 123)
- Create: 1–2 sub-components in `frontend/src/app/dashboard/_components/` (create folder if absent)

**Extraction plan:**
- Read the page. Identify the most branchy widget(s) (typically a per-category section with conditional empty/loading/error states).
- Extract one widget into a sub-component.

- [ ] **Step 1: Read the file**

Run: `cat src/app/dashboard/page.tsx`

- [ ] **Step 2: Create the sub-component(s)**

Create sub-component file(s) under `frontend/src/app/dashboard/_components/`. Move the chosen JSX.

- [ ] **Step 3: Wire sub-component(s) into `DashboardPage`**

Replace the moved JSX with the sub-component call(s).

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/app/dashboard/page.tsx`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test the dashboard**

Start dev server. Open /dashboard. Confirm all widgets render identically.

- [ ] **Step 7: Commit**

```bash
git add src/app/dashboard/
git commit -m "refactor(frontend): split DashboardPage into widget sub-components

Drops complexity below 20. Part of #79."
```

---

### Task 18: Refactor `IdentityPageContent` (complexity 23)

**Files:**
- Modify: `frontend/src/app/identity/page.tsx` (`IdentityPageContent` starting line 53)
- Create: 1 sub-component in `frontend/src/app/identity/_components/`

**Extraction plan:**
- Read the function. Pick the branchy subtree (typically the merge-candidate panel or the per-contact match card).
- Extract it.

- [ ] **Step 1: Read the file**

Run: `cat src/app/identity/page.tsx`

- [ ] **Step 2: Create the sub-component**

Create the sub-component file in `_components/`. Move the chosen subtree.

- [ ] **Step 3: Wire sub-component into `IdentityPageContent`**

Replace moved JSX with the sub-component call.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/app/identity/page.tsx`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test the identity page**

Start dev server. Open /identity. Confirm merge candidates list renders, accept/reject buttons work, empty state renders.

- [ ] **Step 7: Commit**

```bash
git add src/app/identity/
git commit -m "refactor(frontend): split IdentityPageContent into a sub-component

Drops complexity below 20. Part of #79."
```

---

### Task 19: Refactor `SyncResultPanel` in settings (complexity 23)

**Files:**
- Modify: `frontend/src/app/settings/_components/shared.tsx` (`SyncResultPanel` starting line 108)
- Create: 1 sub-component in the same folder

**Extraction plan:**
- Read the file around `SyncResultPanel`. Identify the per-result-type branching (success / error / partial / empty).
- Extract one branch (e.g., a `<SyncErrorList/>` or per-platform-result subtree).

- [ ] **Step 1: Read the relevant section**

Run: `sed -n '95,200p' src/app/settings/_components/shared.tsx`

- [ ] **Step 2: Create the sub-component**

Create the sub-component file in `frontend/src/app/settings/_components/`. Move the chosen subtree.

- [ ] **Step 3: Wire sub-component into `SyncResultPanel`**

Replace moved JSX with the sub-component call.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/app/settings/_components/shared.tsx`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test a sync trigger from settings**

Start dev server. Open Settings → trigger a sync (Gmail, Telegram, or Twitter). Confirm the sync result panel renders success/error/details correctly.

- [ ] **Step 7: Commit**

```bash
git add src/app/settings/_components/
git commit -m "refactor(frontend): split SyncResultPanel into a sub-component

Drops complexity below 20. Part of #79."
```

---

### Task 20: Refactor `ContactPanel` in identity match card (complexity 22)

**Files:**
- Modify: `frontend/src/app/identity/_components/match-card.tsx` (`ContactPanel` starting line 34)
- Create: 1 sub-component in the same folder

**Extraction plan:**
- Read the file. Pick the branchy subtree (typically the per-field comparison row with merge-direction controls).
- Extract it.

- [ ] **Step 1: Read the file**

Run: `cat src/app/identity/_components/match-card.tsx`

- [ ] **Step 2: Create the sub-component**

Create the sub-component file in the same folder. Move the chosen subtree.

- [ ] **Step 3: Wire sub-component into `ContactPanel`**

Replace moved JSX with the sub-component call.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/app/identity/_components/match-card.tsx`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test the identity merge UI**

Start dev server. Open /identity. Pick a candidate, inspect the match card field-by-field, perform the merge. Confirm parity.

- [ ] **Step 7: Commit**

```bash
git add src/app/identity/_components/
git commit -m "refactor(frontend): split ContactPanel match card into a sub-component

Drops complexity below 20. Part of #79."
```

---

### Task 21: Refactor `DuplicateRow` (complexity 21)

**Files:**
- Modify: `frontend/src/app/contacts/[id]/_components/duplicates-card.tsx` (`DuplicateRow` starting line 38)
- Create: 1 sub-component in the same folder

**Extraction plan:**
- Read the file. Pick the branchy subtree (likely the per-field-difference detail or the merge-action buttons).
- Extract it.

- [ ] **Step 1: Read the file**

Run: `cat 'src/app/contacts/[id]/_components/duplicates-card.tsx'`

- [ ] **Step 2: Create the sub-component**

Create the sub-component file in the same folder. Move the chosen subtree.

- [ ] **Step 3: Wire sub-component into `DuplicateRow`**

Replace moved JSX with the sub-component call.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' 'src/app/contacts/[id]/_components/duplicates-card.tsx'`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test the duplicates card**

Start dev server. Open a contact with known duplicates (or create one). Confirm the duplicates card renders, per-duplicate diff shows, merge button works.

- [ ] **Step 7: Commit**

```bash
git add 'src/app/contacts/[id]/_components/'
git commit -m "refactor(frontend): split DuplicateRow into a sub-component

Drops complexity below 20. Part of #79."
```

---

### Task 22: Refactor `OrganizationsPageContent` (complexity 21)

**Files:**
- Modify: `frontend/src/app/organizations/page.tsx` (`OrganizationsPageContent` starting line 172)
- Create: 1 sub-component in `frontend/src/app/organizations/_components/` (create folder if absent)

**Extraction plan:**
- Read the function. Pick the branchy subtree (typically the org card grid item with conditional logo / contact-count badges).
- Extract it.

- [ ] **Step 1: Read the file**

Run: `cat src/app/organizations/page.tsx`

- [ ] **Step 2: Create the sub-component**

Create the sub-component file under `_components/`. Move the chosen subtree.

- [ ] **Step 3: Wire sub-component into `OrganizationsPageContent`**

Replace moved JSX with the sub-component call.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' src/app/organizations/page.tsx`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test the organizations index**

Start dev server. Open /organizations. Confirm grid renders, click-through to detail works, search/sort works.

- [ ] **Step 7: Commit**

```bash
git add src/app/organizations/
git commit -m "refactor(frontend): split OrganizationsPageContent into a sub-component

Drops complexity below 20. Part of #79."
```

---

### Task 23: Refactor `GoogleCard` (complexity 21)

**Files:**
- Modify: `frontend/src/app/settings/_components/platform-cards/google-card.tsx` (`GoogleCard` starting line 28)
- Create: 1 sub-component in the same folder

**Extraction plan:**
- Read the file. Pick the branchy subtree (typically the OAuth-flow CTA conditional, or the per-scope sync-toggles row).
- Extract it.

- [ ] **Step 1: Read the file**

Run: `cat 'src/app/settings/_components/platform-cards/google-card.tsx'`

- [ ] **Step 2: Create the sub-component**

Create the sub-component file in the same folder. Move the chosen subtree.

- [ ] **Step 3: Wire sub-component into `GoogleCard`**

Replace moved JSX with the sub-component call.

- [ ] **Step 4: Verify complexity drop**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' 'src/app/settings/_components/platform-cards/google-card.tsx'`
Expected: clean.

- [ ] **Step 5: Verify typecheck and tests pass**

Run: `npx tsc --noEmit && npm test`
Expected: clean and all pass.

- [ ] **Step 6: Smoke-test settings → Google**

Start dev server. Open Settings. Open Google card. Confirm: connected status renders, toggle each sub-sync (Gmail, Contacts, Calendar) — without actually disconnecting.

- [ ] **Step 7: Commit**

```bash
git add 'src/app/settings/_components/platform-cards/'
git commit -m "refactor(frontend): split GoogleCard into a sub-component

Drops complexity below 20. Part of #79."
```

---

## Final Slice — Re-enable rule + full verification

### Task 24: Re-enable `complexity` rule + run all verifications

**Files:**
- Modify: `frontend/eslint.config.mjs:134-135`

- [ ] **Step 1: Confirm all 16 sites pass the per-file check**

Run: `npx eslint --rule '{"complexity": ["error", 20]}' 'src/**/*.{ts,tsx}'`
Expected: clean — no `complexity` errors anywhere.

If any site still fails, return to the corresponding task and do further extraction.

- [ ] **Step 2: Flip the rule in the ESLint config**

In `frontend/eslint.config.mjs`, replace lines 134–135:

```js
complexity: ['error', 20],
```

(Delete the existing `// Disabled: overlaps with sonarjs/cognitive-complexity. See GH #79.` comment line above it.)

- [ ] **Step 3: Run full lint with the new config**

Run: `npx eslint 'src/**/*.{ts,tsx}'`
Expected: clean — no errors, no warnings.

- [ ] **Step 4: Run typecheck**

Run: `npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Run full test suite**

Run: `npm test`
Expected: all tests pass (including the new mapper and api-errors tests).

- [ ] **Step 6: Verify the `as any` count dropped from baseline**

Run: `bash scripts/check-as-any.sh`
Expected: count decreased by 5 vs. baseline (no `as any` introduced; 5 removed).

- [ ] **Step 7: Final manual smoke pass**

Start dev server. Walk through each affected surface end-to-end using the local test account (see `CLAUDE.local.md`):

- /auth/login + /auth/register → login, register, logout
- /dashboard → all widgets render
- /contacts → list, filter, sort, paginate, select, bulk actions
- /contacts/archive → list, restore, delete
- /contacts/[id] → header (menu, avatar modal), timeline (calls, meetings, events, messages), composer, duplicates card
- /identity → match card, merge flow
- /organizations → list, detail, inline edit
- /settings → Google card, Telegram card (no actual disconnect), trigger a sync (Gmail or Telegram) and verify result panel
- Tag taxonomy editor — add, rename, delete a tag
- Suggestion update flow — mark a suggestion as sent, snooze, dismiss

Watch the browser console and the dev server for errors.

- [ ] **Step 8: Commit**

```bash
git add eslint.config.mjs
git commit -m "chore(frontend): re-enable complexity rule at threshold 20

All 16 sites that previously exceeded the threshold have been
refactored into smaller sub-components and sub-hooks (see prior
commits). Closes the complexity portion of #79.

Closes #79."
```

- [ ] **Step 9: Push and open PR**

Push the branch. Open a PR titled `frontend: close #79 (ESLint deferred cleanup)`. Body summarizes the three slices and links to the spec:

```markdown
## Summary
- Removed five body:as-any casts: 4 via typed mappers in `src/lib/api-mappers.ts`, 1 via typed-body for form-encoded login.
- Refactored 16 components/hooks exceeding ESLint complexity 20 into smaller sub-components/sub-hooks.
- Re-enabled the `complexity` rule at threshold 20.
- Added `ApiError` discriminated union to `src/lib/api-errors.ts`; merge-conflict flow consumes it instead of duck-typing `detail`.

Spec: `docs/specs/2026-05-26-frontend-eslint-deferred-cleanup-design.md`

Closes #79.

## Test plan
- [x] `npm test` passes
- [x] `npx tsc --noEmit` clean
- [x] `npx eslint 'src/**/*.{ts,tsx}'` clean (with complexity rule re-enabled)
- [x] `bash scripts/check-as-any.sh` count decreased by 5
- [x] Manual smoke of all affected surfaces (see commit `chore(frontend): re-enable complexity...`)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```
