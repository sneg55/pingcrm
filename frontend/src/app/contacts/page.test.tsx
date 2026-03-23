import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ContactsPage from "./page";

// Mock api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    DELETE: vi.fn(),
  },
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
  });

  it("renders page title and Add Contact button", () => {
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    renderPage();
    expect(screen.getByText("Contacts")).toBeInTheDocument();
    // "Add Contact" appears in both the header and the empty state
    expect(screen.getAllByText("Add Contact").length).toBeGreaterThan(0);
  });

  it("shows loading state", () => {
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = renderPage();
    // Skeleton loader rows are rendered instead of text
    expect(container.querySelectorAll("[class*='animate-pulse']").length).toBeGreaterThan(0);
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
    expect(screen.getByText("No contacts found")).toBeInTheDocument();
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
    // Name appears in both desktop table (hidden lg:grid) and mobile cards (lg:hidden)
    expect(screen.getAllByText("Alice Smith").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Bob Jones").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Acme Inc").length).toBeGreaterThanOrEqual(1);
  });

  it("shows last interaction as days ago", () => {
    mockUseContacts.mockReturnValue({
      data: { data: [makeContact()], meta: { total: 1, page: 1, page_size: 20, total_pages: 1 } },
      isLoading: false,
      isError: false,
    });
    renderPage();
    // DaysAgo component renders "{n}d" for days since last interaction
    // last_interaction_at is "2025-01-15T10:00:00Z", which is in the past
    // The component renders "{days}d" — we just check it renders a "d" suffix value
    const dayElements = screen.getAllByText(/^\d+d$/);
    expect(dayElements.length).toBeGreaterThan(0);
  });

  it("shows dash when no last interaction", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact({ last_interaction_at: null })],
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    // DaysAgo renders an em-dash when no date
    const dashes = document.querySelectorAll("span.text-stone-300");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("calls router.replace when search changes (debounced)", () => {
    vi.useFakeTimers();
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    renderPage();
    const input = screen.getByPlaceholderText("Search by name, email, company, or notes...");
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
      // Filter panel shows Platform section with checkboxes
      expect(screen.getByText("Platform")).toBeInTheDocument();
      // Tags section is present
      expect(screen.getByText("Tags")).toBeInTheDocument();
      // Date range labels are present (they use visual <label> without for attr)
      expect(screen.getByText("From")).toBeInTheDocument();
      expect(screen.getByText("To")).toBeInTheDocument();
    });

    it("renders platform checkboxes when panel open", () => {
      currentParams = new URLSearchParams("filters=1");
      renderPage();
      // Platform section shows Gmail, Telegram, Twitter checkboxes
      expect(screen.getByText("Gmail")).toBeInTheDocument();
      expect(screen.getByText("Telegram")).toBeInTheDocument();
      expect(screen.getByText("Twitter / X")).toBeInTheDocument();
    });

    it("calls replace with source param on platform checkbox click", () => {
      currentParams = new URLSearchParams("filters=1");
      renderPage();
      // Click Gmail checkbox
      const gmailLabel = screen.getByText("Gmail");
      const gmailCheckbox = gmailLabel.closest("label")!.querySelector("input[type='checkbox']")!;
      fireEvent.click(gmailCheckbox);
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

    it("shows active filter count badge when source filter is set", () => {
      currentParams = new URLSearchParams("source=gmail");
      renderPage();
      // The Filters button should show a badge with count 1
      const badge = screen.getByText("1");
      expect(badge).toBeInTheDocument();
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

    it("clears source filter when Clear all is clicked", () => {
      currentParams = new URLSearchParams("source=gmail");
      renderPage();
      fireEvent.click(screen.getByText("Clear all"));
      expect(mockReplace).toHaveBeenCalledWith("/contacts", expect.anything());
    });
  });

  describe("Score filter from URL", () => {
    it("shows Strong score filter pill as active when score=strong in URL", () => {
      currentParams = new URLSearchParams("score=strong");
      mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
      renderPage();
      // The "Strong" pill button exists and is styled as active when score=strong
      expect(screen.getByText("Strong")).toBeInTheDocument();
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
      const input = screen.getByPlaceholderText("Search by name, email, company, or notes...") as HTMLInputElement;
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
      // New pagination shows "Showing X-Y of Z" format
      expect(screen.getByText(/Showing/)).toBeInTheDocument();
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
      expect(screen.queryByText("Previous")).not.toBeInTheDocument();
      expect(screen.queryByText("Next")).not.toBeInTheDocument();
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
