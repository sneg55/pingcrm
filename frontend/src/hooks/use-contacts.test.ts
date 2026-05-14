import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { client } from "@/lib/api-client";
import {
  useContacts,
  useContact,
  useContactDuplicates,
  useContactActivity,
  useCreateContact,
  useDeleteContact,
  useMergeContacts,
  useUpdateContact,
} from "./use-contacts";

// Mock @/lib/api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    DELETE: vi.fn(),
  },
}));

const mockClient = vi.mocked(client);

// Wrapper factory — fresh QueryClient per test, spy on invalidateQueries.
function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  const Wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { Wrapper, queryClient, invalidateSpy };
}

// ---------------------------------------------------------------------------
// useContacts — list query
// ---------------------------------------------------------------------------
describe("useContacts", () => {
  beforeEach(() => vi.clearAllMocks());

  it("starts in loading state with no data", () => {
    mockClient.GET.mockReturnValue(new Promise(() => {}));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContacts(), { wrapper: Wrapper });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("returns data on successful fetch", async () => {
    const contacts = [{ id: "c1", full_name: "Alice" }];
    mockClient.GET.mockResolvedValueOnce({
      data: { data: contacts, meta: { total: 1 } },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContacts(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.data).toEqual(contacts);
  });

  it("returns null when API returns nullish data", async () => {
    mockClient.GET.mockResolvedValueOnce({ data: undefined });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContacts(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });

  it("surfaces error when fetch throws", async () => {
    mockClient.GET.mockRejectedValueOnce(new Error("boom"));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContacts(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toBe("boom");
  });

  it("passes params through to the API call", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [], meta: {} } });
    const params = { page: 2, search: "ali", tag: "vip" };
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContacts(params), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/contacts", {
      params: { query: params },
    });
  });

  it("refetches when params change (query key includes params)", async () => {
    mockClient.GET.mockResolvedValue({ data: { data: [], meta: {} } });
    const { Wrapper } = makeWrapper();

    const { result, rerender } = renderHook(
      ({ p }: { p: { page: number } }) => useContacts(p),
      { wrapper: Wrapper, initialProps: { p: { page: 1 } } }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    rerender({ p: { page: 2 } });
    await waitFor(() =>
      expect(mockClient.GET).toHaveBeenLastCalledWith("/api/v1/contacts", {
        params: { query: { page: 2 } },
      })
    );
    // Initial + after param change
    expect(mockClient.GET).toHaveBeenCalledTimes(2);
  });
});

// ---------------------------------------------------------------------------
// useContact — single fetch
// ---------------------------------------------------------------------------
describe("useContact", () => {
  beforeEach(() => vi.clearAllMocks());

  it("does not fire when id is empty (enabled=false)", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContact(""), { wrapper: Wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockClient.GET).not.toHaveBeenCalled();
  });

  it("fetches a single contact when id is provided", async () => {
    mockClient.GET.mockResolvedValueOnce({
      data: { data: { id: "c1", full_name: "Alice" } },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContact("c1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockClient.GET).toHaveBeenCalledWith(
      "/api/v1/contacts/{contact_id}",
      { params: { path: { contact_id: "c1" } } }
    );
  });

  it("returns null when API returns nullish data", async () => {
    mockClient.GET.mockResolvedValueOnce({ data: undefined });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContact("c1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// useContactDuplicates
// ---------------------------------------------------------------------------
describe("useContactDuplicates", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is idle when enabled=false", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContactDuplicates("c1", false), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockClient.GET).not.toHaveBeenCalled();
  });

  it("is idle when id is empty (even if enabled=true)", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContactDuplicates("", true), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockClient.GET).not.toHaveBeenCalled();
  });

  it("fetches duplicates when enabled with valid id", async () => {
    mockClient.GET.mockResolvedValueOnce({
      data: { data: [{ id: "c2" }], error: null },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContactDuplicates("c1", true), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockClient.GET).toHaveBeenCalledWith(
      "/api/v1/contacts/{contact_id}/duplicates",
      { params: { path: { contact_id: "c1" } } }
    );
  });

  it("falls back to { data: [], error: null } when API returns nullish", async () => {
    mockClient.GET.mockResolvedValueOnce({ data: undefined });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContactDuplicates("c1", true), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ data: [], error: null });
  });
});

// ---------------------------------------------------------------------------
// useContactActivity
// ---------------------------------------------------------------------------
describe("useContactActivity", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is idle when id is empty", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContactActivity(""), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockClient.GET).not.toHaveBeenCalled();
  });

  it("returns unwrapped activity data on success", async () => {
    const activity = {
      score: 7,
      dimensions: {
        reciprocity: { value: 1, max: 2 },
        recency: { value: 2, max: 2 },
        frequency: { value: 1, max: 2 },
        breadth: { value: 1, max: 2 },
      },
      stats: {
        inbound_365d: 10,
        outbound_365d: 5,
        count_30d: 3,
        count_90d: 7,
        platforms: ["email"],
        interaction_count: 15,
        first_interaction_at: null,
      },
      monthly_trend: [],
    };
    mockClient.GET.mockResolvedValueOnce({ data: { data: activity } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContactActivity("c1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(activity);
    expect(mockClient.GET).toHaveBeenCalledWith(
      "/api/v1/contacts/{contact_id}/activity",
      { params: { path: { contact_id: "c1" } } }
    );
  });

  it("throws when API returns error envelope", async () => {
    mockClient.GET.mockResolvedValueOnce({
      data: null,
      error: { detail: "nope" },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContactActivity("c1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toBe(
      "Failed to fetch activity"
    );
  });

  it("throws when data envelope is empty", async () => {
    mockClient.GET.mockResolvedValueOnce({ data: { data: null } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useContactActivity("c1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toBe(
      "Failed to fetch activity"
    );
  });
});

// ---------------------------------------------------------------------------
// useCreateContact — mutation + cache invalidation
// ---------------------------------------------------------------------------
describe("useCreateContact", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs to /contacts with input body and returns created contact", async () => {
    const created = { id: "new", full_name: "Bob" };
    mockClient.POST.mockResolvedValueOnce({ data: created });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCreateContact(), {
      wrapper: Wrapper,
    });

    let returned: unknown;
    await act(async () => {
      returned = await result.current.mutateAsync({ full_name: "Bob" });
    });

    expect(mockClient.POST).toHaveBeenCalledWith("/api/v1/contacts", {
      body: { full_name: "Bob" },
    });
    expect(returned).toEqual(created);
  });

  it("invalidates [\"contacts\"] on success", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: { id: "x" } });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCreateContact(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({ full_name: "X" });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["contacts"] });
  });
});

// ---------------------------------------------------------------------------
// useDeleteContact
// ---------------------------------------------------------------------------
describe("useDeleteContact", () => {
  beforeEach(() => vi.clearAllMocks());

  it("DELETEs the correct contact endpoint", async () => {
    mockClient.DELETE.mockResolvedValueOnce({ data: { ok: true } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useDeleteContact(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync("c1");
    });

    expect(mockClient.DELETE).toHaveBeenCalledWith(
      "/api/v1/contacts/{contact_id}",
      { params: { path: { contact_id: "c1" } } }
    );
  });

  it("invalidates [\"contacts\"] on success", async () => {
    mockClient.DELETE.mockResolvedValueOnce({ data: {} });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useDeleteContact(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync("c1");
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["contacts"] });
  });
});

// ---------------------------------------------------------------------------
// useMergeContacts
// ---------------------------------------------------------------------------
describe("useMergeContacts", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs to merge endpoint with both ids", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: { ok: true } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMergeContacts(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({ contactId: "a", otherId: "b" });
    });

    expect(mockClient.POST).toHaveBeenCalledWith(
      "/api/v1/contacts/{contact_id}/merge/{other_id}",
      { params: { path: { contact_id: "a", other_id: "b" } } }
    );
  });

  it("invalidates BOTH [\"contacts\"] and [\"contact-duplicates\"] on success", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: { ok: true } });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useMergeContacts(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({ contactId: "a", otherId: "b" });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["contacts"] });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["contact-duplicates"],
    });
  });

  it("throws extracted detail message when API returns error envelope", async () => {
    mockClient.POST.mockResolvedValueOnce({
      data: null,
      error: { detail: "Cannot merge same contact" },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMergeContacts(), {
      wrapper: Wrapper,
    });

    await expect(
      act(async () => {
        await result.current.mutateAsync({ contactId: "a", otherId: "b" });
      })
    ).rejects.toThrow("Cannot merge same contact");
  });

  it("falls back to 'Merge failed' when detail is missing", async () => {
    mockClient.POST.mockResolvedValueOnce({
      data: null,
      error: {},
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMergeContacts(), {
      wrapper: Wrapper,
    });

    await expect(
      act(async () => {
        await result.current.mutateAsync({ contactId: "a", otherId: "b" });
      })
    ).rejects.toThrow("Merge failed");
  });
});

// ---------------------------------------------------------------------------
// useUpdateContact — invalidation matrix is the asymmetry the prior run pinned
// ---------------------------------------------------------------------------
describe("useUpdateContact", () => {
  beforeEach(() => vi.clearAllMocks());

  it("PUTs with id path param and body, returns updated contact", async () => {
    const updated = { id: "c1", full_name: "Alice II" };
    mockClient.PUT.mockResolvedValueOnce({ data: updated });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateContact(), {
      wrapper: Wrapper,
    });

    let returned: unknown;
    await act(async () => {
      returned = await result.current.mutateAsync({
        id: "c1",
        input: { full_name: "Alice II" },
      });
    });

    expect(mockClient.PUT).toHaveBeenCalledWith(
      "/api/v1/contacts/{contact_id}",
      {
        params: { path: { contact_id: "c1" } },
        body: { full_name: "Alice II" },
      }
    );
    expect(returned).toEqual(updated);
  });

  it("invalidates [\"contacts\"] and [\"contacts\", id] on success (always)", async () => {
    mockClient.PUT.mockResolvedValueOnce({ data: { id: "c1" } });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useUpdateContact(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        id: "c1",
        input: { full_name: "Just a name" },
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["contacts"] });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["contacts", "c1"],
    });
    // No telegram or twitter keys when those fields aren't touched
    const calls = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(calls).not.toContainEqual(["sync-telegram", "c1"]);
    expect(calls).not.toContainEqual(["refresh-bios", "c1"]);
  });

  it("ALSO invalidates [\"sync-telegram\", id] only when telegram_username is in input", async () => {
    mockClient.PUT.mockResolvedValueOnce({ data: { id: "c1" } });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useUpdateContact(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        id: "c1",
        input: { telegram_username: "newhandle" },
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["sync-telegram", "c1"],
    });
    // No twitter
    const calls = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(calls).not.toContainEqual(["refresh-bios", "c1"]);
  });

  it("ALSO invalidates [\"refresh-bios\", id] only when twitter_handle is in input", async () => {
    mockClient.PUT.mockResolvedValueOnce({ data: { id: "c1" } });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useUpdateContact(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        id: "c1",
        input: { twitter_handle: "newx" },
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["refresh-bios", "c1"],
    });
    const calls = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(calls).not.toContainEqual(["sync-telegram", "c1"]);
  });

  it("invalidates BOTH sync-telegram and refresh-bios when both fields change", async () => {
    mockClient.PUT.mockResolvedValueOnce({ data: { id: "c1" } });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useUpdateContact(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        id: "c1",
        input: { telegram_username: "tg", twitter_handle: "tw" },
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["sync-telegram", "c1"],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["refresh-bios", "c1"],
    });
  });

  it("throws structured error with status + detail when API returns error envelope", async () => {
    mockClient.PUT.mockResolvedValueOnce({
      data: null,
      error: { detail: { conflicting_contact: { id: "other" } } },
      response: { status: 409 } as Response,
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateContact(), {
      wrapper: Wrapper,
    });

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({
          id: "c1",
          input: { twitter_handle: "dup" },
        });
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(Error);
    const err = caught as Error & { status?: number; detail?: unknown };
    expect(err.message).toBe("Update failed");
    expect(err.status).toBe(409);
    expect(err.detail).toEqual({ conflicting_contact: { id: "other" } });
  });
});
