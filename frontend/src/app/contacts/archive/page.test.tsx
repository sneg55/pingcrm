import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ArchivedContactsPage from "./page";

// Mock api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    DELETE: vi.fn(),
  },
}));

// Mock hooks
const mockUseContacts = vi.fn();
const mockMutate = vi.fn();
const mockUseUpdateContact = vi.fn();

vi.mock("@/hooks/use-contacts", () => ({
  useContacts: (...args: unknown[]) => mockUseContacts(...args),
  useUpdateContact: () => mockUseUpdateContact(),
}));

// Mock date-fns
vi.mock("date-fns", () => ({
  formatDistanceToNow: () => "2 months ago",
}));

const mockReplace = vi.fn();
let currentParams = new URLSearchParams();

vi.mock("next/navigation", async () => {
  return {
    useSearchParams: () => currentParams,
    useRouter: () => ({ push: vi.fn(), replace: mockReplace, back: vi.fn() }),
    usePathname: () => "/contacts/archive",
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
    location: null,
    birthday: null,
    linkedin_url: null,
    avatar_url: null,
    tags: [],
    notes: null,
    relationship_score: 75,
    interaction_count: 5,
    last_interaction_at: "2025-01-15T10:00:00Z",
    last_followup_at: null,
    priority_level: "archived",
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
  return render(<ArchivedContactsPage />, { wrapper });
}

describe("ArchivedContactsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentParams = new URLSearchParams();
    mockUseUpdateContact.mockReturnValue({ mutate: mockMutate, isPending: false });
  });

  it("renders archived contacts list with contact names", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [
          makeContact({ id: "c1", full_name: "Alice Smith" }),
          makeContact({ id: "c2", full_name: "Bob Jones", company: "Corp" }),
        ],
        meta: { total: 2, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    expect(screen.getByText("Acme Inc")).toBeInTheDocument();
  });

  it("renders page heading and description", () => {
    mockUseContacts.mockReturnValue({
      data: { data: [], meta: { total: 0, page: 1, page_size: 20, total_pages: 0 } },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("Archived Contacts")).toBeInTheDocument();
  });

  it("shows loading state with skeleton rows", () => {
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = renderPage();
    expect(container.querySelectorAll("[class*='animate-pulse']").length).toBeGreaterThan(0);
  });

  it("shows empty state when no archived contacts", () => {
    mockUseContacts.mockReturnValue({
      data: { data: [], meta: { total: 0, page: 1, page_size: 20, total_pages: 0 } },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("No archived contacts")).toBeInTheDocument();
    expect(
      screen.getByText(/Contacts you archive will appear here/i)
    ).toBeInTheDocument();
  });

  it("renders Back to Contacts navigation link", () => {
    mockUseContacts.mockReturnValue({
      data: { data: [], meta: { total: 0, page: 1, page_size: 20, total_pages: 0 } },
      isLoading: false,
      isError: false,
    });
    renderPage();
    const link = screen.getByText("Back to Contacts").closest("a");
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/contacts");
  });

  it("calls unarchive mutation when Unarchive button is clicked", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact({ id: "c1", full_name: "Alice Smith" })],
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    const unarchiveBtn = screen.getByText("Unarchive");
    fireEvent.click(unarchiveBtn);
    expect(mockMutate).toHaveBeenCalledWith({
      id: "c1",
      input: { priority_level: "medium" },
    });
  });

  it("bulk selects all contacts and calls unarchive for each on Unarchive All", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [
          makeContact({ id: "c1", full_name: "Alice Smith" }),
          makeContact({ id: "c2", full_name: "Bob Jones" }),
        ],
        meta: { total: 2, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();

    // Select all via header checkbox
    const checkboxes = screen.getAllByRole("checkbox");
    // First checkbox is the select-all header checkbox
    fireEvent.click(checkboxes[0]);

    // Bulk action bar should appear
    expect(screen.getByText(/2 selected/)).toBeInTheDocument();

    // Click Unarchive All
    fireEvent.click(screen.getByText("Unarchive All"));

    expect(mockMutate).toHaveBeenCalledWith({ id: "c1", input: { priority_level: "medium" } });
    expect(mockMutate).toHaveBeenCalledWith({ id: "c2", input: { priority_level: "medium" } });
  });

  it("shows bulk action bar when contacts are selected and hides it on dismiss", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact({ id: "c1", full_name: "Alice Smith" })],
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();

    // Bulk action bar not visible initially
    expect(screen.queryByText(/1 selected/)).not.toBeInTheDocument();

    // Select one contact
    const rowCheckboxes = screen.getAllByRole("checkbox");
    fireEvent.click(rowCheckboxes[1]); // second checkbox is the row one

    expect(screen.getByText("1 selected")).toBeInTheDocument();

    // Dismiss via X button
    const dismissBtn = screen.getByTestId("icon-X").closest("button")!;
    fireEvent.click(dismissBtn);

    expect(screen.queryByText(/1 selected/)).not.toBeInTheDocument();
  });

  it("shows error state when loading fails", () => {
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderPage();
    expect(screen.getByText(/Failed to load archived contacts/)).toBeInTheDocument();
  });

  it("passes archived_only: true to useContacts", () => {
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    renderPage();
    expect(mockUseContacts).toHaveBeenCalledWith(
      expect.objectContaining({ archived_only: true })
    );
  });

  it("debounces search input and updates URL", () => {
    vi.useFakeTimers();
    mockUseContacts.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    renderPage();
    const input = screen.getByPlaceholderText("Search archived contacts...");
    fireEvent.change(input, { target: { value: "bob" } });
    expect(mockReplace).not.toHaveBeenCalled();
    vi.advanceTimersByTime(300);
    expect(mockReplace).toHaveBeenCalledWith(
      expect.stringContaining("q=bob"),
      expect.anything()
    );
    vi.useRealTimers();
  });

  it("shows pagination controls when there are multiple pages", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact()],
        meta: { total: 40, page: 1, page_size: 20, total_pages: 2 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("Previous")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
    expect(screen.getByText("Previous")).toBeDisabled();
    expect(screen.getByText("Next")).not.toBeDisabled();
  });

  it("does not show pagination when there is only one page", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact()],
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.queryByText("Previous")).not.toBeInTheDocument();
    expect(screen.queryByText("Next")).not.toBeInTheDocument();
  });

  it("shows contact email when full_name is present", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact({ full_name: "Alice Smith", emails: ["alice@example.com"] })],
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("renders last interaction as relative time", () => {
    mockUseContacts.mockReturnValue({
      data: {
        data: [makeContact({ last_interaction_at: "2025-01-01T00:00:00Z" })],
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
      isError: false,
    });
    renderPage();
    expect(screen.getByText("2 months ago")).toBeInTheDocument();
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
});
