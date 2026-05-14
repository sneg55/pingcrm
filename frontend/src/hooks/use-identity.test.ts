import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { client } from "@/lib/api-client";
import {
  useIdentityMatches,
  useMergeMatch,
  useRejectMatch,
  useScanIdentity,
} from "./use-identity";

vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    DELETE: vi.fn(),
  },
}));

const mockClient = vi.mocked(client);

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
// useIdentityMatches — list query
// ---------------------------------------------------------------------------
describe("useIdentityMatches", () => {
  beforeEach(() => vi.clearAllMocks());

  it("starts in loading state with no data", () => {
    mockClient.GET.mockReturnValue(new Promise(() => {}));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useIdentityMatches(), {
      wrapper: Wrapper,
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("returns match list on successful fetch", async () => {
    const matches = [
      {
        id: "m1",
        contact_a: { id: "a", full_name: "Alice" },
        contact_b: { id: "b", full_name: "Alice S." },
        match_score: 0.92,
        match_method: "email",
        status: "pending_review",
        created_at: "2026-03-01T00:00:00Z",
      },
    ];
    mockClient.GET.mockResolvedValueOnce({ data: { data: matches } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useIdentityMatches(), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockClient.GET).toHaveBeenCalledWith("/api/v1/identity/matches", {});
    expect(result.current.data?.data).toEqual(matches);
  });

  it("surfaces error when fetch rejects", async () => {
    mockClient.GET.mockRejectedValueOnce(new Error("403 forbidden"));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useIdentityMatches(), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toBe("403 forbidden");
  });
});

// ---------------------------------------------------------------------------
// useMergeMatch — invalidates ["identity"] AND ["contacts"]
// ---------------------------------------------------------------------------
describe("useMergeMatch", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs to merge endpoint with match id", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: { ok: true } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMergeMatch(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync("m1");
    });

    expect(mockClient.POST).toHaveBeenCalledWith(
      "/api/v1/identity/matches/{match_id}/merge",
      { params: { path: { match_id: "m1" } } }
    );
  });

  it("invalidates BOTH [\"identity\"] and [\"contacts\"] on success", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: { ok: true } });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useMergeMatch(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync("m1");
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["identity"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["contacts"] });
  });

  it("throws with detail from error envelope", async () => {
    mockClient.POST.mockResolvedValueOnce({
      data: null,
      error: { detail: "Already merged" },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMergeMatch(), { wrapper: Wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync("m1");
      })
    ).rejects.toThrow("Already merged");
  });

  it("falls back to 'Merge failed' when error envelope has no detail", async () => {
    mockClient.POST.mockResolvedValueOnce({
      data: null,
      error: {},
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMergeMatch(), { wrapper: Wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync("m1");
      })
    ).rejects.toThrow("Merge failed");
  });

  it("does NOT invalidate when mutation fails", async () => {
    mockClient.POST.mockResolvedValueOnce({
      data: null,
      error: { detail: "boom" },
    });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useMergeMatch(), { wrapper: Wrapper });

    await act(async () => {
      await result.current
        .mutateAsync("m1")
        .catch(() => undefined);
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useRejectMatch — invalidates ONLY ["identity"] (asymmetry vs merge)
// ---------------------------------------------------------------------------
describe("useRejectMatch", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs to reject endpoint with match id", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: { ok: true } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRejectMatch(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync("m1");
    });

    expect(mockClient.POST).toHaveBeenCalledWith(
      "/api/v1/identity/matches/{match_id}/reject",
      { params: { path: { match_id: "m1" } } }
    );
  });

  it("invalidates ONLY [\"identity\"] on success — NOT [\"contacts\"]", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: { ok: true } });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useRejectMatch(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync("m1");
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["identity"] });
    // Pinning the intentional asymmetry — rejecting does not touch contact list
    const calls = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(calls).not.toContainEqual(["contacts"]);
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
  });

  it("throws with detail from error envelope", async () => {
    mockClient.POST.mockResolvedValueOnce({
      data: null,
      error: { detail: "Already rejected" },
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRejectMatch(), { wrapper: Wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync("m1");
      })
    ).rejects.toThrow("Already rejected");
  });

  it("falls back to 'Reject failed' when error envelope has no detail", async () => {
    mockClient.POST.mockResolvedValueOnce({
      data: null,
      error: {},
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRejectMatch(), { wrapper: Wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync("m1");
      })
    ).rejects.toThrow("Reject failed");
  });
});

// ---------------------------------------------------------------------------
// useScanIdentity
// ---------------------------------------------------------------------------
describe("useScanIdentity", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs to scan endpoint with no params", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: { scanned: 10 } });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useScanIdentity(), {
      wrapper: Wrapper,
    });

    let returned: unknown;
    await act(async () => {
      returned = await result.current.mutateAsync();
    });

    expect(mockClient.POST).toHaveBeenCalledWith("/api/v1/identity/scan");
    expect(returned).toEqual({ scanned: 10 });
  });

  it("invalidates [\"identity\"] on success", async () => {
    mockClient.POST.mockResolvedValueOnce({ data: {} });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useScanIdentity(), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["identity"] });
    // Does NOT touch contacts cache
    const calls = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(calls).not.toContainEqual(["contacts"]);
  });
});
