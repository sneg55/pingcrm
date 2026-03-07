import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ContactsPage from "./page";
import apiClient from "@/lib/api";

// Mock apiClient
vi.mock("@/lib/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  __esModule: true,
}));

// Mock useContacts hook
const mockUseContacts = vi.fn();
vi.mock("@/hooks/use-contacts", () => ({
  useContacts: (...args: unknown[]) => mockUseContacts(...args),
}));

// Mock date-fns to avoid time-sensitive output
vi.mock("date-fns", () => ({
  formatDistanceToNow: () => "3 days ago",
}));

const mockPush = vi.fn();
const mockReplace = vi.fn();
let currentParams = new URLSearchParams();

vi.mock("next/navigation", async () => {
  return {
    useSearchParams: () => currentParams,
    useRouter: () => ({ push: mockPush, replace: mockReplace, back: vi.fn() }),
    usePathname: () => "/contacts",
    useParams: () => ({}),
  };
});

const mockedApiGet = vi.mocked(apiClient.get);

function makeContact(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    user_id: "u1",
    full_name: "Alice Smith",
    given_name: "Alice",
    family_name: "Smith",
    emails: ["alice@example.com"],
    phones: [],
    company: "Acme Inc",
    title: null,
    twitter_handle: null,
    twitter_bio: null,
    telegram_username: null,
    telegram_bio: null,
    tags: ["investor"],
    notes: null,
    relationship_score: 7,
    last_interaction_at: "2025-01-15T10:00:00Z",
    last_followup_at: null,
    priority_level: "normal",
    source: "google",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPage() {
  return render(<ContactsPage />, { wrapper });
}

describe("ContactsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentParams = new URLSearchParams();
    mockedApiGet.mockResolvedValue({ data: { data: [], error: null } } as never);
  });

  it("renders page title and Add Contact button", () => {
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    renderPage();
    expect(screen.getByText("Contacts")).toBeInTheDocument();
    expect(screen.getByText("Add Contact")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderPage();
    expect(screen.getByText("Loading contacts...")).toBeInTheDocument();
  });

  it("shows error state", () => {
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderPage();
    expect(screen.getByText(/Failed to load contacts/)).toBeInTheDocument();
  });

  it("shows empty state when no contacts", () => {
    mockUseContacts.mockReturnValue({
      data: { data: [], meta: { total: 0, page: 1, page_size: 20, total_pages: 0 } },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("No contacts found.")).toBeInTheDocument();
  });

  it("renders contacts table with data", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact(), makeContact({ id: "c2", full_name: "Bob Jones", company: "Corp" })],
        meta: { total: 2, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    expect(screen.getByText("Acme Inc")).toBeInTheDocument();
    expect(screen.getByText("2 total contacts")).toBeInTheDocument();
  });

  it("shows last interaction time", () => {
    mockUseContacts.mockReturnValue({
      data: { data: [makeContact()], meta: { total: 1, page: 1, page_size: 20, total_pages: 1 } },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("3 days ago")).toBeInTheDocument();
  });

  it("shows Never when no last interaction", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact({ last_interaction_at: null })],
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  it("calls router.replace when search changes (debounced)", () => {
    vi.useFakeTimers();
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    renderPage();
    const input = screen.getByPlaceholderText("Search by name or company...");
    fireEvent.change(input, { target: { value: "alice" } });
    // Should not fire immediately
    expect(mockReplace).not.toHaveBeenCalled();
    // After debounce delay
    vi.advanceTimersByTime(300);
    expect(mockReplace).toHaveBeenCalledWith(
      expect.stringContaining("q=alice"),
      expect.anything()
    );
    vi.useRealTimers();
  });

  describe("Filters", () => {
    beforeEach(() => {
      mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    });

    it("shows Filters button", () => {
      renderPage();
      expect(screen.getByText("Filters")).toBeInTheDocument();
    });

    it("toggles filter panel via URL param", () => {
      renderPage();
      expect(screen.queryByLabelText("Tag")).not.toBeInTheDocument();
      fireEvent.click(screen.getByText("Filters"));
      // Should call replace with filters=1
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining("filters=1"),
        expect.anything()
      );
    });

    it("shows filter panel when filters=1 in URL", () => {
      currentParams = new URLSearchParams("filters=1");
      renderPage();
      expect(screen.getByLabelText("Tag")).toBeInTheDocument();
      expect(screen.getByLabelText("Source")).toBeInTheDocument();
      expect(screen.getByLabelText("From")).toBeInTheDocument();
      expect(screen.getByLabelText("To")).toBeInTheDocument();
    });

    it("renders source dropdown options when panel open", () => {
      currentParams = new URLSearchParams("filters=1");
      renderPage();
      expect(screen.getByDisplayValue("All sources")).toBeInTheDocument();
    });

    it("calls replace with source param on selection", () => {
      currentParams = new URLSearchParams("filters=1");
      renderPage();
      fireEvent.change(screen.getByDisplayValue("All sources"), { target: { value: "gmail" } });
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining("source=gmail"),
        expect.anything()
      );
    });

    it("shows tag select in filter panel", () => {
      currentParams = new URLSearchParams("filters=1");
      renderPage();
      expect(screen.getByDisplayValue("All tags")).toBeInTheDocument();
    });

    it("shows source filter chip from URL", () => {
      currentParams = new URLSearchParams("source=gmail");
      renderPage();
      expect(screen.getByText(/Source: Gmail/)).toBeInTheDocument();
    });

    it("shows date filter chip from URL", () => {
      currentParams = new URLSearchParams("date_from=2025-01-01");
      renderPage();
      expect(screen.getByText(/Date:/)).toBeInTheDocument();
    });

    it("shows active filter count badge", () => {
      currentParams = new URLSearchParams("source=gmail&tag=investor");
      renderPage();
      expect(screen.getByText("2")).toBeInTheDocument();
    });

    it("shows Clear all button when filters active", () => {
      currentParams = new URLSearchParams("source=gmail");
      renderPage();
      expect(screen.getByText("Clear all")).toBeInTheDocument();
    });

    it("clears all filters on Clear all click", () => {
      currentParams = new URLSearchParams("source=gmail&tag=investor");
      renderPage();
      fireEvent.click(screen.getByText("Clear all"));
      expect(mockReplace).toHaveBeenCalledWith("/contacts", expect.anything());
    });

    it("removes individual source filter chip", () => {
      currentParams = new URLSearchParams("source=gmail");
      renderPage();
      const chip = screen.getByText(/Source: Gmail/).closest("span")!;
      const removeBtn = chip.querySelector("button")!;
      fireEvent.click(removeBtn);
      expect(mockReplace).toHaveBeenCalled();
      // The URL should not contain source=gmail
      const lastCall = mockReplace.mock.calls[mockReplace.mock.calls.length - 1][0] as string;
      expect(lastCall).not.toContain("source=gmail");
    });
  });

  describe("Score filter from URL", () => {
    it("shows score chip when score param in URL", () => {
      currentParams = new URLSearchParams("score=strong");
      mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
      renderPage();
      expect(screen.getByText(/Score: Strong/)).toBeInTheDocument();
    });

    it("passes score to useContacts from URL", () => {
      currentParams = new URLSearchParams("score=active");
      mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
      renderPage();
      expect(mockUseContacts).toHaveBeenCalledWith(
        expect.objectContaining({ score: "active" })
      );
    });
  });

  describe("Filter persistence via URL", () => {
    it("reads search from q param", () => {
      currentParams = new URLSearchParams("q=bob");
      mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
      renderPage();
      const input = screen.getByPlaceholderText("Search by name or company...") as HTMLInputElement;
      expect(input.value).toBe("bob");
      expect(mockUseContacts).toHaveBeenCalledWith(
        expect.objectContaining({ search: "bob" })
      );
    });

    it("reads all filters from URL params", () => {
      currentParams = new URLSearchParams("source=telegram&tag=vc&date_from=2025-01-01&date_to=2025-06-01");
      mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
      renderPage();
      expect(mockUseContacts).toHaveBeenCalledWith(
        expect.objectContaining({
          source: "telegram",
          tag: "vc",
          date_from: "2025-01-01",
          date_to: "2025-06-01",
        })
      );
    });
  });

  describe("Pagination", () => {
    it("shows pagination when multiple pages", () => {
      mockUseContacts.mockReturnValue({
        data: {
          data: [makeContact()],
          meta: { total: 40, page: 1, page_size: 20, total_pages: 2 },
        },
        isLoading: false,
        isError: false,
      });
      renderPage();
      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
      expect(screen.getByText("Previous")).toBeDisabled();
      expect(screen.getByText("Next")).not.toBeDisabled();
    });

    it("does not show pagination for single page", () => {
      mockUseContacts.mockReturnValue({
        data: {
          data: [makeContact()],
          meta: { total: 5, page: 1, page_size: 20, total_pages: 1 },
        },
        isLoading: false,
        isError: false,
      });
      renderPage();
      expect(screen.queryByText(/Page/)).not.toBeInTheDocument();
    });

    it("navigates to next page via URL", () => {
      mockUseContacts.mockReturnValue({
        data: {
          data: [makeContact()],
          meta: { total: 40, page: 1, page_size: 20, total_pages: 2 },
        },
        isLoading: false,
        isError: false,
      });
      renderPage();
      fireEvent.click(screen.getByText("Next"));
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining("page=2"),
        expect.anything()
      );
    });
  });
});
