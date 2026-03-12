import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import IdentityPage from "./page";

// Mock api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}));

// Mutable state for hook overrides — mutated per test in beforeEach
const scanState = {
  isPending: false,
  isSuccess: false,
  isError: false,
  data: undefined as unknown,
};

const mockMergeMatchMutate = vi.fn();
const mockRejectMatchMutate = vi.fn();
const mockScanIdentityMutate = vi.fn();
const mockUseIdentityMatches = vi.fn();

vi.mock("@/hooks/use-identity", () => ({
  useIdentityMatches: () => mockUseIdentityMatches(),
  useMergeMatch: () => ({
    mutate: mockMergeMatchMutate,
    isPending: false,
  }),
  useRejectMatch: () => ({
    mutate: mockRejectMatchMutate,
    isPending: false,
  }),
  useScanIdentity: () => ({
    mutate: mockScanIdentityMutate,
    isPending: scanState.isPending,
    isSuccess: scanState.isSuccess,
    isError: scanState.isError,
    data: scanState.data,
  }),
}));

function makeContact(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    full_name: "Alice Smith",
    given_name: "Alice",
    family_name: "Smith",
    emails: ["alice@example.com"],
    phones: [],
    company: "Acme Inc",
    title: null,
    twitter_handle: null,
    telegram_username: null,
    linkedin_url: null,
    tags: [],
    notes: null,
    source: "google",
    ...overrides,
  };
}

function makeMatch(overrides: Record<string, unknown> = {}) {
  return {
    id: "match-1",
    contact_a: makeContact({ id: "c1", full_name: "Alice Smith" }),
    contact_b: makeContact({ id: "c2", full_name: "Alice S.", emails: ["alice@corp.com"] }),
    match_score: 0.78,
    match_method: "probabilistic",
    status: "pending_review",
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPage() {
  return render(<IdentityPage />, { wrapper });
}

describe("IdentityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    scanState.isPending = false;
    scanState.isSuccess = false;
    scanState.isError = false;
    scanState.data = undefined;
    mockUseIdentityMatches.mockReturnValue({ data: undefined, isLoading: false });
  });

  describe("page structure", () => {
    it("renders page heading and description", () => {
      renderPage();
      expect(screen.getByText("Identity Resolution")).toBeInTheDocument();
      expect(screen.getByText("Review and merge duplicate contacts")).toBeInTheDocument();
    });

    it("renders Scan for duplicates button when not scanning", () => {
      renderPage();
      expect(screen.getByRole("button", { name: /Scan for duplicates/i })).toBeInTheDocument();
    });
  });

  describe("loading state", () => {
    it("shows skeleton loaders while matches are loading", () => {
      mockUseIdentityMatches.mockReturnValue({ data: undefined, isLoading: true });
      const { container } = renderPage();
      expect(container.querySelectorAll("[class*='animate-pulse']").length).toBeGreaterThan(0);
    });

    it("does not show match cards while loading", () => {
      mockUseIdentityMatches.mockReturnValue({ data: undefined, isLoading: true });
      renderPage();
      expect(screen.queryByText("vs")).not.toBeInTheDocument();
    });
  });

  describe("scan button", () => {
    it("calls scanIdentity.mutate when scan button is clicked", () => {
      renderPage();
      const scanBtn = screen.getByRole("button", { name: /Scan for duplicates/i });
      fireEvent.click(scanBtn);
      expect(mockScanIdentityMutate).toHaveBeenCalledTimes(1);
    });

    it("shows Scanning... label and disables button while scan is pending", () => {
      scanState.isPending = true;
      renderPage();
      const scanBtn = screen.getByRole("button", { name: /Scanning\.\.\./i });
      expect(scanBtn).toBeDisabled();
    });

    it("shows scan progress panel while scanning", () => {
      scanState.isPending = true;
      renderPage();
      expect(screen.getByText("Scanning contacts for duplicates...")).toBeInTheDocument();
    });

    it("shows scan error message when scan fails", () => {
      scanState.isError = true;
      renderPage();
      expect(screen.getByText("Scan failed. Please try again.")).toBeInTheDocument();
    });

    it("shows scan result banner after successful scan", () => {
      scanState.isSuccess = true;
      scanState.data = { data: { matches_found: 3, auto_merged: 1, pending_review: 2 } };
      renderPage();
      expect(screen.getByText(/Scan complete/)).toBeInTheDocument();
      expect(screen.getByText(/3 matches found/)).toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    it("shows No pending matches when there are no pending matches", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("No pending matches")).toBeInTheDocument();
    });

    it("shows prompt to run a scan in empty state", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Run a scan to detect potential duplicates")).toBeInTheDocument();
    });

    it("shows Scan now button in empty state", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByRole("button", { name: /Scan now/i })).toBeInTheDocument();
    });

    it("does not show empty state when pending matches exist", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch()] },
        isLoading: false,
      });
      renderPage();
      expect(screen.queryByText("No pending matches")).not.toBeInTheDocument();
    });

    it("shows empty state even when non-pending matches exist", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch({ status: "merged" })] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("No pending matches")).toBeInTheDocument();
    });
  });

  describe("duplicate pairs list", () => {
    it("renders contact names for each match", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch()] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Alice Smith")).toBeInTheDocument();
      expect(screen.getByText("Alice S.")).toBeInTheDocument();
    });

    it("renders multiple match cards when multiple pending matches exist", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [
            makeMatch({ id: "match-1" }),
            makeMatch({
              id: "match-2",
              contact_a: makeContact({ id: "c3", full_name: "Bob Jones" }),
              contact_b: makeContact({ id: "c4", full_name: "Bob J." }),
            }),
          ],
        },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Bob Jones")).toBeInTheDocument();
      expect(screen.getByText("Bob J.")).toBeInTheDocument();
    });

    it("only shows pending_review matches, not merged or rejected", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [
            makeMatch({ id: "match-1", status: "merged" }),
            makeMatch({
              id: "match-2",
              status: "pending_review",
              contact_a: makeContact({ id: "c3", full_name: "Carol White" }),
              contact_b: makeContact({ id: "c4", full_name: "Carol W." }),
            }),
          ],
        },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Carol White")).toBeInTheDocument();
      // merged match (Alice Smith) should not produce a card
      expect(screen.queryByText("No pending matches")).not.toBeInTheDocument();
    });

    it("shows match percentage in each card", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch({ match_score: 0.78 })] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("78% match")).toBeInTheDocument();
    });

    it("shows pending review badge count when matches exist", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch()] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("1 pending review")).toBeInTheDocument();
    });

    it("shows VS divider between contact panels", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch()] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("vs")).toBeInTheDocument();
    });

    it("shows Unnamed for contacts without a name", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [
            makeMatch({
              contact_a: makeContact({ id: "c1", full_name: null }),
              contact_b: makeContact({ id: "c2", full_name: "Alice S." }),
            }),
          ],
        },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Unnamed")).toBeInTheDocument();
    });
  });

  describe("match type labels", () => {
    it("shows Exact match label for deterministic method", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [makeMatch({ match_method: "deterministic", match_score: 0.9 })],
        },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Exact match")).toBeInTheDocument();
    });

    it("shows Possible match label for probabilistic method with mid-range score", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [makeMatch({ match_method: "probabilistic", match_score: 0.72 })],
        },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Possible match")).toBeInTheDocument();
    });

    it("shows Auto-merge ready badge for very high score matches", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [makeMatch({ match_method: "deterministic", match_score: 0.97 })],
        },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Auto-merge ready")).toBeInTheDocument();
    });

    it("shows low confidence message for low score matches", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [makeMatch({ match_method: "probabilistic", match_score: 0.55 })],
        },
        isLoading: false,
      });
      renderPage();
      expect(
        screen.getByText("Low confidence — manual review recommended")
      ).toBeInTheDocument();
    });
  });

  describe("merge action", () => {
    it("renders Merge button for each match card", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch()] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByRole("button", { name: /Merge/i })).toBeInTheDocument();
    });

    it("calls mergeMatch.mutate with the match id when Merge is clicked", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch({ id: "match-abc" })] },
        isLoading: false,
      });
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Merge/i }));
      expect(mockMergeMatchMutate).toHaveBeenCalledWith(
        "match-abc",
        expect.objectContaining({ onSuccess: expect.any(Function) })
      );
    });

    it("shows merged successfully toast after merge", async () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch({ id: "match-abc" })] },
        isLoading: false,
      });
      mockMergeMatchMutate.mockImplementation(
        (_id: string, opts: { onSuccess?: () => void }) => {
          opts?.onSuccess?.();
        }
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Merge/i }));
      await waitFor(() => {
        expect(screen.getByText("Contacts merged successfully")).toBeInTheDocument();
      });
    });
  });

  describe("dismiss (Not the same) action", () => {
    it("renders Not the same button for each match card", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch()] },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByRole("button", { name: /Not the same/i })).toBeInTheDocument();
    });

    it("calls rejectMatch.mutate with the match id when Not the same is clicked", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch({ id: "match-xyz" })] },
        isLoading: false,
      });
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Not the same/i }));
      expect(mockRejectMatchMutate).toHaveBeenCalledWith(
        "match-xyz",
        expect.objectContaining({ onSuccess: expect.any(Function) })
      );
    });

    it("shows rejection toast after dismissing", async () => {
      mockUseIdentityMatches.mockReturnValue({
        data: { data: [makeMatch({ id: "match-xyz" })] },
        isLoading: false,
      });
      mockRejectMatchMutate.mockImplementation(
        (_id: string, opts: { onSuccess?: () => void }) => {
          opts?.onSuccess?.();
        }
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Not the same/i }));
      await waitFor(() => {
        expect(screen.getByText("Marked as not the same")).toBeInTheDocument();
      });
    });
  });

  describe("contact panel details", () => {
    it("shows email address in contact panel", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [
            makeMatch({
              contact_a: makeContact({ id: "c1", full_name: "Alice Smith", emails: ["alice@example.com"] }),
              contact_b: makeContact({ id: "c2", full_name: "Alice S.", emails: ["alice@corp.com"] }),
            }),
          ],
        },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    });

    it("shows company name in contact panel", () => {
      mockUseIdentityMatches.mockReturnValue({
        data: {
          data: [
            makeMatch({
              contact_a: makeContact({ id: "c1", full_name: "Alice Smith", company: "Acme Corp" }),
              contact_b: makeContact({ id: "c2", full_name: "Alice S.", company: null }),
            }),
          ],
        },
        isLoading: false,
      });
      renderPage();
      expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    });
  });
});
