import { render, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useRouter, useSearchParams } from "next/navigation";
import GoogleCallbackPage from "./page";

import { client } from "@/lib/api-client";

// Mock api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    POST: vi.fn(),
  },
}));

const mockedClient = client as unknown as { POST: ReturnType<typeof vi.fn> };
const mockedUseRouter = useRouter as unknown as ReturnType<typeof vi.fn>;
const mockedUseSearchParams = useSearchParams as unknown as ReturnType<typeof vi.fn>;

describe("GoogleCallbackPage", () => {
  const mockReplace = vi.fn();
  const mockSetItem = vi.fn();
  const mockGetItem = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();

    // Provide a localStorage stub since jsdom localStorage may not be available
    vi.stubGlobal("localStorage", {
      setItem: mockSetItem,
      getItem: mockGetItem,
      removeItem: vi.fn(),
      clear: vi.fn(),
      length: 0,
      key: vi.fn(),
    });

    mockedUseRouter.mockReturnValue({
      push: vi.fn(),
      replace: mockReplace,
      back: vi.fn(),
    });

    mockedUseSearchParams.mockReturnValue({
      get: (key: string) => (key === "code" ? "auth-code-123" : null),
    });
  });

  it("stores JWT under the key 'access_token' (not 'token') on success", async () => {
    mockedClient.POST.mockResolvedValue({
      data: { data: { access_token: "test-jwt" } },
      error: undefined,
    });

    render(<GoogleCallbackPage />);

    await waitFor(() => {
      expect(mockSetItem).toHaveBeenCalledWith("access_token", "test-jwt");
    });

    // Confirm the old wrong key is NOT used
    const wrongKeyCall = mockSetItem.mock.calls.find((call) => call[0] === "token");
    expect(wrongKeyCall).toBeUndefined();
  });

  it("redirects to /settings?connected=google after storing the token", async () => {
    mockedClient.POST.mockResolvedValue({
      data: { data: { access_token: "test-jwt" } },
      error: undefined,
    });

    render(<GoogleCallbackPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/settings?connected=google");
    });
  });
});
