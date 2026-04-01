# Global Search Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add functional "All | Contacts | Companies" tabs to the global search dropdown so users can search across both contacts and organizations.

**Architecture:** Frontend-only change to `NavSearch` in `nav.tsx`. Two parallel React Query calls on the "All" tab (contacts + orgs), single call on each specific tab. Organizations API already supports `?search=`. No backend changes.

**Tech Stack:** React, React Query, TypeScript, Tailwind CSS, Vitest

---

### Task 1: Add organization search types and query hook

**Files:**
- Modify: `frontend/src/components/nav.tsx:141-268`
- Test: `frontend/src/components/nav.test.tsx`

- [ ] **Step 1: Write failing test — organizations query fires on "Companies" tab**

Add to `nav.test.tsx`. First, update the mock setup to also mock the `client` module for org queries:

```typescript
// Add at top with other mocks
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn().mockResolvedValue({ data: { data: [], meta: { total: 0 } } }),
  },
}));

import { client } from "@/lib/api-client";
const mockedClient = vi.mocked(client);
```

Then add the test:

```typescript
it("shows tab bar with All, Contacts, Companies when search is active", () => {
  setupMocks();
  render(<Nav />);
  // Open search
  fireEvent.click(screen.getByText("Search contacts"));
  const input = screen.getByPlaceholderText("Search...");
  fireEvent.change(input, { target: { value: "rise" } });
  expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Contacts" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Companies" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/components/nav.test.tsx`
Expected: FAIL — no tab buttons exist yet

- [ ] **Step 3: Add tab state and tab UI to NavSearch**

In `nav.tsx`, inside `NavSearch`, add state and the org search type:

```typescript
// Add at top of NavSearch function, after existing state
const [tab, setTab] = useState<"all" | "contacts" | "companies">("all");
```

Add a type for org results at the top of the file (outside NavSearch):

```typescript
interface OrgSearchResult {
  id: string;
  name: string;
  contact_count: number;
}
```

Add the org query inside NavSearch (after the existing `useContacts` call):

```typescript
const orgQuery = useQuery({
  queryKey: ["organizations", "nav-search", query],
  queryFn: async () => {
    const { data } = await client.GET("/api/v1/organizations" as any, {
      params: { query: { search: query, page_size: tab === "all" ? "4" : "6" } },
    });
    return (data as any)?.data as OrgSearchResult[] ?? [];
  },
  enabled: query.length >= 2 && tab !== "contacts",
});
const orgResults = query.length >= 2 ? (orgQuery.data ?? []) : [];
```

Update the contacts query `page_size` to be tab-aware:

```typescript
const { data } = useContacts({
  search: query || undefined,
  page_size: tab === "all" ? 4 : 6,
});
```

Add tab bar rendering inside the dropdown, before the results `<div className="max-h-72 ...">`:

```tsx
{/* Tab bar */}
<div className="flex items-center gap-1 px-3 pt-2 pb-1 border-b border-stone-100 dark:border-stone-800">
  {(["all", "contacts", "companies"] as const).map((t) => (
    <button
      key={t}
      role="button"
      aria-label={t === "all" ? "All" : t === "contacts" ? "Contacts" : "Companies"}
      onClick={() => setTab(t)}
      className={cn(
        "px-2 py-1 text-xs font-medium rounded transition-colors",
        tab === t
          ? "text-teal-700 dark:text-teal-400 bg-teal-50 dark:bg-teal-950"
          : "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300"
      )}
    >
      {t === "all" ? "All" : t === "contacts" ? "Contacts" : "Companies"}
    </button>
  ))}
</div>
```

Add `useQuery` to the imports:

```typescript
import { useQuery } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
```

Reset tab when dropdown closes or query clears — update the Escape handler and outside-click handler:

```typescript
// In Escape handler:
if (e.key === "Escape") {
  setOpen(false);
  setQuery("");
  setTab("all");
}

// In outside-click handler:
setOpen(false);
setQuery("");
setTab("all");

// In the navigate callback:
const navigate = useCallback((path: string) => {
  setOpen(false);
  setQuery("");
  setTab("all");
  router.push(path);
}, [router]);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/components/nav.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/nav.tsx frontend/src/components/nav.test.tsx
git commit -m "feat: add tab state and org query to global search"
```

---

### Task 2: Render mixed results with type indicators

**Files:**
- Modify: `frontend/src/components/nav.tsx`
- Test: `frontend/src/components/nav.test.tsx`

- [ ] **Step 1: Write failing test — org results show Building icon and contact count**

```typescript
it("shows organization results with building icon on Companies tab", () => {
  setupMocks();
  mockedClient.GET.mockResolvedValue({
    data: { data: [{ id: "org-1", name: "Fireblocks", contact_count: 5 }], meta: { total: 1 } },
  } as any);
  render(<Nav />);
  fireEvent.click(screen.getByText("Search contacts"));
  const input = screen.getByPlaceholderText("Search...");
  fireEvent.change(input, { target: { value: "fire" } });
  // Switch to Companies tab
  fireEvent.click(screen.getByRole("button", { name: "Companies" }));
  // Should show org name and contact count
  expect(screen.getByText("Fireblocks")).toBeInTheDocument();
  expect(screen.getByText("5 contacts")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/components/nav.test.tsx`
Expected: FAIL — org results not rendered yet

- [ ] **Step 3: Build the combined results list and render org rows**

Replace the existing results rendering in the dropdown with a unified approach. Create a discriminated union type for results:

```typescript
type SearchResult =
  | { type: "contact"; id: string; name: string; subtitle: string | null; avatarInitial: string }
  | { type: "org"; id: string; name: string; subtitle: string };
```

Build the combined list based on active tab, inside the component (after the queries):

```typescript
const combinedResults: SearchResult[] = (() => {
  if (tab === "contacts") {
    return results.map((c) => ({
      type: "contact" as const,
      id: c.id,
      name: c.full_name || c.emails?.[0] || "Unnamed",
      subtitle: c.company || null,
      avatarInitial: (c.full_name || c.emails?.[0] || "?")[0].toUpperCase(),
    }));
  }
  if (tab === "companies") {
    return orgResults.map((o) => ({
      type: "org" as const,
      id: o.id,
      name: o.name,
      subtitle: `${o.contact_count} contact${o.contact_count !== 1 ? "s" : ""}`,
    }));
  }
  // "all" tab: interleave contacts and orgs
  const merged: SearchResult[] = [];
  const contacts = results.map((c) => ({
    type: "contact" as const,
    id: c.id,
    name: c.full_name || c.emails?.[0] || "Unnamed",
    subtitle: c.company || null,
    avatarInitial: (c.full_name || c.emails?.[0] || "?")[0].toUpperCase(),
  }));
  const orgs = orgResults.map((o) => ({
    type: "org" as const,
    id: o.id,
    name: o.name,
    subtitle: `${o.contact_count} contact${o.contact_count !== 1 ? "s" : ""}`,
  }));
  const maxLen = Math.max(contacts.length, orgs.length);
  for (let i = 0; i < maxLen && merged.length < 6; i++) {
    if (i < contacts.length) merged.push(contacts[i]);
    if (i < orgs.length && merged.length < 6) merged.push(orgs[i]);
  }
  return merged;
})();
```

Replace the results `<div className="max-h-72 ...">` contents:

```tsx
<div className="max-h-72 overflow-auto">
  {combinedResults.length === 0 ? (
    <p className="px-3 py-4 text-sm text-stone-400 dark:text-stone-500 text-center">
      {tab === "companies" ? "No companies found" : tab === "contacts" ? "No contacts found" : "No results found"}
    </p>
  ) : (
    combinedResults.map((r) => (
      <button
        key={`${r.type}-${r.id}`}
        onClick={() => navigate(r.type === "contact" ? `/contacts/${r.id}` : `/organizations/${r.id}`)}
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
      >
        {r.type === "contact" ? (
          <div className="w-8 h-8 rounded-full bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-300 flex items-center justify-center text-xs font-medium shrink-0">
            {r.avatarInitial}
          </div>
        ) : (
          <div className="w-8 h-8 rounded-full bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 flex items-center justify-center shrink-0">
            <Building2 className="w-4 h-4" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
            {r.name}
          </p>
          {r.subtitle && (
            <p className="text-xs text-stone-400 dark:text-stone-500 truncate">{r.subtitle}</p>
          )}
        </div>
        {tab === "all" && (
          <span className="text-[10px] text-stone-400 dark:text-stone-500 shrink-0">
            {r.type === "contact" ? "Contact" : "Company"}
          </span>
        )}
      </button>
    ))
  )}
</div>
```

Update the `navigate` callback to accept a path string instead of just an id:

```typescript
const navigate = useCallback((path: string) => {
  setOpen(false);
  setQuery("");
  setTab("all");
  router.push(path);
}, [router]);
```

And update the Enter key handler:

```typescript
onKeyDown={(e) => {
  if (e.key === "Enter" && combinedResults.length > 0) {
    const first = combinedResults[0];
    navigate(first.type === "contact" ? `/contacts/${first.id}` : `/organizations/${first.id}`);
  }
}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/components/nav.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/nav.tsx frontend/src/components/nav.test.tsx
git commit -m "feat: render mixed contact/org results with type indicators"
```

---

### Task 3: Tab-aware "View all results" link

**Files:**
- Modify: `frontend/src/components/nav.tsx`
- Test: `frontend/src/components/nav.test.tsx`

- [ ] **Step 1: Write failing test — Companies tab links to /organizations**

```typescript
it("View all results links to /organizations when Companies tab is active", () => {
  setupMocks();
  render(<Nav />);
  fireEvent.click(screen.getByText("Search contacts"));
  const input = screen.getByPlaceholderText("Search...");
  fireEvent.change(input, { target: { value: "fire" } });
  fireEvent.click(screen.getByRole("button", { name: "Companies" }));
  const viewAll = screen.getByText(/View all results/);
  fireEvent.click(viewAll);
  // router.push should have been called with /organizations?q=fire
  expect(vi.mocked(require("next/navigation").useRouter)().push).toHaveBeenCalledWith(
    "/organizations?q=fire"
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/components/nav.test.tsx`
Expected: FAIL — currently always links to /contacts

- [ ] **Step 3: Update the "View all results" button to be tab-aware**

Replace the existing "View all results" button:

```tsx
{query && (
  <button
    onClick={() => {
      const dest = tab === "companies"
        ? `/organizations?q=${encodeURIComponent(query)}`
        : `/contacts?q=${encodeURIComponent(query)}`;
      navigate(dest);
    }}
    className="shrink-0 w-full px-3 py-2 text-xs text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 border-t border-stone-100 dark:border-stone-800 transition-colors rounded-b-lg"
  >
    View all results for &ldquo;{query}&rdquo;
  </button>
)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/components/nav.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/nav.tsx frontend/src/components/nav.test.tsx
git commit -m "feat: tab-aware View all results link in global search"
```

---

### Task 4: Update placeholder text and button label

**Files:**
- Modify: `frontend/src/components/nav.tsx`
- Test: `frontend/src/components/nav.test.tsx`

- [ ] **Step 1: Update the search button and input placeholder**

Change the closed-state button text from "Search contacts" to "Search" (now searches both types):

```tsx
<span className="hidden sm:inline">Search</span>
```

Change the input placeholder from "Search contacts..." to "Search...":

```tsx
placeholder="Search..."
```

- [ ] **Step 2: Update the existing test that checks for "Search contacts"**

In `nav.test.tsx`, update the test:

```typescript
it("search button renders with Search text", () => {
  render(<Nav />);
  expect(screen.getByText("Search")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run all nav tests**

Run: `cd frontend && npm test -- --run src/components/nav.test.tsx`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/nav.tsx frontend/src/components/nav.test.tsx
git commit -m "feat: update search placeholder for multi-type search"
```

---

### Task 5: Final integration test and cleanup

**Files:**
- Test: `frontend/src/components/nav.test.tsx`

- [ ] **Step 1: Write integration test — full flow across tabs**

```typescript
it("full search flow: type query, switch tabs, navigate", () => {
  setupMocks();
  // Mock contacts
  mockedUseContacts.mockReturnValue({
    data: {
      data: [
        { id: "c1", full_name: "Marius Smith", company: "Ethereum Foundation", emails: [] },
      ],
    },
  } as unknown as ReturnType<typeof useContacts>);
  // Mock orgs
  mockedClient.GET.mockResolvedValue({
    data: { data: [{ id: "org-1", name: "SKYRISE.", contact_count: 3 }], meta: { total: 1 } },
  } as any);

  render(<Nav />);
  fireEvent.click(screen.getByText("Search"));
  const input = screen.getByPlaceholderText("Search...");
  fireEvent.change(input, { target: { value: "rise" } });

  // Default "All" tab — both types shown
  expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();

  // Switch to Contacts tab
  fireEvent.click(screen.getByRole("button", { name: "Contacts" }));
  expect(screen.getByText("Marius Smith")).toBeInTheDocument();

  // Switch to Companies tab
  fireEvent.click(screen.getByRole("button", { name: "Companies" }));
});
```

- [ ] **Step 2: Run full test suite**

Run: `cd frontend && npm test -- --run src/components/nav.test.tsx`
Expected: All PASS

- [ ] **Step 3: Run full frontend test suite to check for regressions**

Run: `cd frontend && npm test`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/nav.test.tsx
git commit -m "test: add integration test for multi-type search tabs"
```
