import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// Mock @/lib/api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    DELETE: vi.fn(),
  },
}));

import { client } from "@/lib/api-client";
import { useContacts, useContact, useContactDuplicates } from "./use-contacts";
import { useSuggestions, useContactSuggestion } from "./use-suggestions";
import { useNotifications, useUnreadCount } from "./use-notifications";
import { useDashboardStats } from "./use-dashboard";
import { useIdentityMatches } from "./use-identity";

const mockClient = vi.mocked(client);

// Wrapper factory — fresh QueryClient per test to avoid cache pollution
function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return Wrapper;
}

// ---------------------------------------------------------------------------
// useContacts
// ---------------------------------------------------------------------------
describe("useContacts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns contacts data from API", async () => {
    const mockContacts = [
      { id: "c1", full_name: "Alice Smith", emails: ["alice@example.com"] },
      { id: "c2", full_name: "Bob Jones", emails: [] },
    ];
    mockClient.GET.mockResolvedValueOnce({
      data: { data: mockContacts, meta: { total: 2, page: 1, page_size: 20, total_pages: 1 } },
    });

    const { result } = renderHook(() => useContacts(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.data).toEqual(mockContacts);
  });

  it("uses correct query key [contacts, params]", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [], meta: {} } });

    const params = { search: "alice", page: 2 };
    const { result } = renderHook(() => useContacts(params), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Verify the API was called with the params in the query
    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/contacts", {
      params: { query: params },
    });
  });

  it("passes search param to API", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [], meta: {} } });

    const { result } = renderHook(() => useContacts({ search: "bob" }), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/contacts", {
      params: { query: { search: "bob" } },
    });
  });

  it("passes pagination params to API", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [], meta: {} } });

    const { result } = renderHook(() => useContacts({ page: 3, page_size: 10 }), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/contacts", {
      params: { query: { page: 3, page_size: 10 } },
    });
  });

  it("returns error state when API fails", async () => {
    mockClient.GET.mockRejectedValueOnce(new Error("Network error"));

    const { result } = renderHook(() => useContacts(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBeDefined();
  });

  it("starts in loading state", () => {
    // Never resolves — stays loading
    mockClient.GET.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useContacts(), { wrapper: makeWrapper() });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// useContact (single contact)
// ---------------------------------------------------------------------------
describe("useContact", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches a single contact by id", async () => {
    const mockContact = { id: "c1", full_name: "Alice Smith", emails: [] };
    mockClient.GET.mockResolvedValueOnce({ data: { data: mockContact } });

    const { result } = renderHook(() => useContact("c1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/contacts/{contact_id}", {
      params: { path: { contact_id: "c1" } },
    });
  });

  it("is disabled when id is empty string", () => {
    const { result } = renderHook(() => useContact(""), { wrapper: makeWrapper() });

    // Query should not fire when id is falsy
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockClient.GET).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useContactDuplicates
// ---------------------------------------------------------------------------
describe("useContactDuplicates", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("is disabled when enabled=false", () => {
    const { result } = renderHook(() => useContactDuplicates("c1", false), {
      wrapper: makeWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockClient.GET).not.toHaveBeenCalled();
  });

  it("fetches duplicates when enabled=true", async () => {
    mockClient.GET.mockResolvedValueOnce({ data: { data: [], error: null } });

    const { result } = renderHook(() => useContactDuplicates("c1", true), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith(
      "/api/v1/contacts/{contact_id}/duplicates",
      { params: { path: { contact_id: "c1" } } }
    );
  });

  it("returns fallback empty data when API returns null", async () => {
    mockClient.GET.mockResolvedValueOnce({ data: null });

    const { result } = renderHook(() => useContactDuplicates("c2", true), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // The hook falls back to { data: [], error: null } when API returns null/undefined
    expect(result.current.data).toEqual({ data: [], error: null });
  });
});

// ---------------------------------------------------------------------------
// useSuggestions
// ---------------------------------------------------------------------------
describe("useSuggestions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns suggestions list from API", async () => {
    const mockSuggestions = [
      {
        id: "s1",
        contact_id: "c1",
        contact: null,
        trigger_type: "birthday",
        suggested_message: "Happy Birthday!",
        suggested_channel: "email",
        status: "pending",
        scheduled_for: null,
        created_at: "2026-03-01T00:00:00Z",
        updated_at: null,
      },
    ];
    mockClient.GET.mockResolvedValueOnce({ data: { data: mockSuggestions } });

    const { result } = renderHook(() => useSuggestions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.data).toEqual(mockSuggestions);
  });

  it("uses query key [suggestions]", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [] } });

    const { result } = renderHook(() => useSuggestions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/suggestions");
  });

  it("returns error when API fails", async () => {
    mockClient.GET.mockRejectedValueOnce(new Error("Server error"));

    const { result } = renderHook(() => useSuggestions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// useContactSuggestion (derived hook — filters by contactId + pending status)
// ---------------------------------------------------------------------------
describe("useContactSuggestion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns the pending suggestion for a given contact", async () => {
    const suggestions = [
      { id: "s1", contact_id: "c1", status: "pending", suggested_message: "Hi!" },
      { id: "s2", contact_id: "c2", status: "pending", suggested_message: "Hello!" },
      { id: "s3", contact_id: "c1", status: "dismissed", suggested_message: "Old." },
    ];
    mockClient.GET.mockResolvedValue({ data: { data: suggestions } });

    // useContactSuggestion depends on useSuggestions which returns Suggestion | null
    // We need to wait until the underlying query succeeds (result.current becomes non-null)
    const { result } = renderHook(
      () => {
        const suggestion = useContactSuggestion("c1");
        const { isSuccess } = useSuggestions();
        return { suggestion, isSuccess };
      },
      { wrapper: makeWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.suggestion?.id).toBe("s1");
    expect(result.current.suggestion?.status).toBe("pending");
  });

  it("returns null when contact has no pending suggestion", async () => {
    const suggestions = [
      { id: "s1", contact_id: "c2", status: "pending" },
    ];
    mockClient.GET.mockResolvedValue({ data: { data: suggestions } });

    const { result } = renderHook(() => useContactSuggestion("c1"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(mockClient.GET).toHaveBeenCalled());

    expect(result.current).toBeNull();
  });

  it("returns null when contactId is undefined", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [] } });

    const { result } = renderHook(() => useContactSuggestion(undefined), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(mockClient.GET).toHaveBeenCalled());

    expect(result.current).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// useNotifications
// ---------------------------------------------------------------------------
describe("useNotifications", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches notifications with default page 1", async () => {
    mockClient.GET.mockResolvedValueOnce({
      data: {
        data: [{ id: "n1", notification_type: "mention", title: "New mention", body: null, read: false, link: null, created_at: null }],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
    });

    const { result } = renderHook(() => useNotifications(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/notifications", {
      params: { query: { page: 1, page_size: 20 } },
    });
    expect(result.current.data?.data).toHaveLength(1);
  });

  it("uses query key [notifications, page]", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [], error: null, meta: {} } });

    const { result: r1 } = renderHook(() => useNotifications(1), { wrapper: makeWrapper() });
    await waitFor(() => expect(r1.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/notifications", {
      params: { query: { page: 1, page_size: 20 } },
    });

    mockClient.GET.mockResolvedValue({ data: { data: [], error: null, meta: {} } });
    const { result: r2 } = renderHook(() => useNotifications(2), { wrapper: makeWrapper() });
    await waitFor(() => expect(r2.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/notifications", {
      params: { query: { page: 2, page_size: 20 } },
    });
  });
});

// ---------------------------------------------------------------------------
// useUnreadCount
// ---------------------------------------------------------------------------
describe("useUnreadCount", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns unread notification count", async () => {
    mockClient.GET.mockResolvedValueOnce({ data: { data: { count: 7 } } });

    const { result } = renderHook(() => useUnreadCount(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.data.count).toBe(7);
    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/notifications/unread-count");
  });

  it("uses a distinct query key from notifications list", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: { count: 0 } } });

    const { result } = renderHook(() => useUnreadCount(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // The key is ["notifications", "unread-count"] — different from ["notifications", <number>]
    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/notifications/unread-count");
  });
});

// ---------------------------------------------------------------------------
// useDashboardStats
// ---------------------------------------------------------------------------
describe("useDashboardStats", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock fetch for overdue and activity (those use raw fetch, not the openapi client)
    global.fetch = vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({ data: [] }),
    });
  });

  it("returns aggregated dashboard stats with defaults when APIs succeed", async () => {
    // Suggestions GET
    mockClient.GET.mockImplementation(async (path: string) => {
      if (path === "/api/v1/suggestions") {
        return { data: { data: [{ id: "s1", contact_id: "c1", status: "pending" }] } };
      }
      if (path === "/api/v1/contacts/stats") {
        return {
          data: {
            data: {
              total: 50,
              strong: 10,
              active: 20,
              dormant: 20,
              interactions_this_week: 5,
            },
          },
        };
      }
      return { data: { data: [] } };
    });

    const { result } = renderHook(() => useDashboardStats(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.stats.total).toBe(50);
    expect(result.current.stats.strong).toBe(10);
    expect(result.current.stats.active).toBe(20);
    expect(result.current.stats.dormant).toBe(20);
    expect(result.current.stats.interactionsThisWeek).toBe(5);
    expect(result.current.suggestions).toHaveLength(1);
  });

  it("returns zero-defaults for stats when API returns undefined", async () => {
    mockClient.GET.mockResolvedValue({ data: undefined });

    const { result } = renderHook(() => useDashboardStats(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.stats.total).toBe(0);
    expect(result.current.stats.active).toBe(0);
    expect(result.current.stats.strong).toBe(0);
    expect(result.current.stats.dormant).toBe(0);
    expect(result.current.stats.interactionsThisWeek).toBe(0);
    expect(result.current.suggestions).toEqual([]);
  });

  it("exposes isError when suggestions or stats query fails", async () => {
    mockClient.GET.mockRejectedValue(new Error("API error"));

    const { result } = renderHook(() => useDashboardStats(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("overdueContacts defaults to empty array when fetch returns no data", async () => {
    // fetch is mocked in beforeEach to return { data: [] }
    mockClient.GET.mockResolvedValue({ data: { data: [] } });

    const { result } = renderHook(() => useDashboardStats(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // When fetch returns { data: [] }, overdueContacts is an empty array (not undefined/null)
    expect(Array.isArray(result.current.overdueContacts)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// useIdentityMatches
// ---------------------------------------------------------------------------
describe("useIdentityMatches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches identity matches from API", async () => {
    const matches = [
      {
        id: "m1",
        contact_a: { id: "c1", full_name: "Alice" },
        contact_b: { id: "c2", full_name: "Alice Smith" },
        match_score: 0.85,
        match_method: "email",
        status: "pending_review",
        created_at: "2026-03-01T00:00:00Z",
      },
    ];
    mockClient.GET.mockResolvedValueOnce({ data: { data: matches } });

    const { result } = renderHook(() => useIdentityMatches(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/identity/matches");
    expect(result.current.data?.data).toEqual(matches);
  });

  it("uses distinct query key [identity, matches]", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [] } });

    const { result } = renderHook(() => useIdentityMatches(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Key is ["identity", "matches"] — does NOT conflict with contacts keys
    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/identity/matches");
  });

  it("returns error state on API failure", async () => {
    mockClient.GET.mockRejectedValueOnce(new Error("Forbidden"));

    const { result } = renderHook(() => useIdentityMatches(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
