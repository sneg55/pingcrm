import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OrganizationsPage from "./page";

// Mock api-client
const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api-client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGet(...args),
    POST: (...args: unknown[]) => mockPost(...args),
    PUT: vi.fn(),
    DELETE: vi.fn(),
  },
}));

// Mock date-fns to avoid time-sensitive output
vi.mock("date-fns", () => ({
  formatDistanceToNow: () => "2 days ago",
}));

// Mock ContactAvatar component
vi.mock("@/components/contact-avatar", () => ({
  ContactAvatar: ({ name }: { name: string }) => (
    <span data-testid="contact-avatar">{name[0]}</span>
  ),
}));

// Mock ScoreBadge component
vi.mock("@/components/score-badge", () => ({
  ScoreBadge: ({ score }: { score: number }) => (
    <span data-testid="score-badge">{score}</span>
  ),
}));

const mockReplace = vi.fn();
let currentParams = new URLSearchParams();

vi.mock("next/navigation", async () => ({
  useSearchParams: () => currentParams,
  useRouter: () => ({ push: vi.fn(), replace: mockReplace, back: vi.fn() }),
  usePathname: () => "/organizations",
  useParams: () => ({}),
}));

// ---- helpers ----

function makeContact(overrides: Record<string, unknown> = {}) {
  return {
    id: "contact-1",
    full_name: "Alice Smith",
    given_name: "Alice",
    family_name: "Smith",
    title: "Engineer",
    avatar_url: null,
    relationship_score: 7,
    last_interaction_at: "2025-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeOrg(overrides: Record<string, unknown> = {}) {
  return {
    company: "Acme Inc",
    contact_count: 1,
    contacts: [makeContact()],
    ...overrides,
  };
}

function makeApiResponse(orgs: ReturnType<typeof makeOrg>[], total = orgs.length) {
  return {
    data: {
      data: orgs,
      meta: { total, page: 1, page_size: 50, total_pages: 1 },
    },
    error: null,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPage() {
  return render(<OrganizationsPage />, { wrapper });
}

// ---- tests ----

describe("OrganizationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentParams = new URLSearchParams();
    // Default tags response
    mockGet.mockImplementation((path: string) => {
      if (path === "/api/v1/contacts/tags") {
        return Promise.resolve({ data: { data: ["investor", "friend"] }, error: null });
      }
      // Default organizations response — empty
      return Promise.resolve(makeApiResponse([]));
    });
  });

  describe("Organization list rendering", () => {
    it("renders page heading", async () => {
      renderPage();
      expect(screen.getByText("Organizations")).toBeInTheDocument();
    });

    it("renders organization names", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(
          makeApiResponse([
            makeOrg({ company: "Acme Inc" }),
            makeOrg({ company: "Beta Corp", contacts: [makeContact({ id: "c2", full_name: "Bob Jones" })] }),
          ])
        );
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText("Acme Inc")).toBeInTheDocument();
        expect(screen.getByText("Beta Corp")).toBeInTheDocument();
      });
    });

    it("shows contact count per organization", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(
          makeApiResponse([
            makeOrg({
              company: "Multi Corp",
              contact_count: 3,
              contacts: [
                makeContact({ id: "c1" }),
                makeContact({ id: "c2", full_name: "Bob" }),
                makeContact({ id: "c3", full_name: "Carol" }),
              ],
            }),
          ])
        );
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText("3 people")).toBeInTheDocument();
      });
    });

    it("shows total companies count in header", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(makeApiResponse([makeOrg()], 5));
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText("5 companies")).toBeInTheDocument();
      });
    });

    it("expands org to show contacts when clicked", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(
          makeApiResponse([makeOrg({ company: "Acme Inc" })])
        );
      });

      renderPage();

      await waitFor(() => expect(screen.getByText("Acme Inc")).toBeInTheDocument());

      fireEvent.click(screen.getByText("Acme Inc"));

      await waitFor(() => {
        expect(screen.getByText("Alice Smith")).toBeInTheDocument();
      });
    });
  });

  describe("Empty state", () => {
    it("shows empty state when no organizations", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(makeApiResponse([]));
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText("No organizations found.")).toBeInTheDocument();
      });
    });
  });

  describe("Loading state", () => {
    it("shows loading text while data is fetching", async () => {
      // Return a never-resolving promise to hold the loading state
      mockGet.mockImplementation(() => new Promise(() => {}));

      renderPage();

      expect(screen.getByText("Loading organizations...")).toBeInTheDocument();
    });
  });

  describe("Error state", () => {
    it("shows error message when API fails", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.reject(new Error("Network error"));
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText("Failed to load organizations.")).toBeInTheDocument();
      });
    });
  });

  describe("Search", () => {
    it("renders search input", async () => {
      renderPage();
      expect(screen.getByPlaceholderText("Search companies...")).toBeInTheDocument();
    });

    it("calls router.replace with search query after debounce", async () => {
      vi.useFakeTimers();
      renderPage();

      const input = screen.getByPlaceholderText("Search companies...");
      fireEvent.change(input, { target: { value: "acme" } });

      // Should not fire immediately
      expect(mockReplace).not.toHaveBeenCalled();

      vi.advanceTimersByTime(300);

      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining("q=acme"),
        expect.anything()
      );

      vi.useRealTimers();
    });

    it("pre-fills search input from URL q param", async () => {
      currentParams = new URLSearchParams("q=beta");
      renderPage();

      const input = screen.getByPlaceholderText("Search companies...") as HTMLInputElement;
      expect(input.value).toBe("beta");
    });

    it("passes search param to API request", async () => {
      currentParams = new URLSearchParams("q=acme");
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(makeApiResponse([]));
      });

      renderPage();

      await waitFor(() => {
        expect(mockGet).toHaveBeenCalledWith(
          "/api/v1/organizations",
          expect.objectContaining({
            params: expect.objectContaining({
              query: expect.objectContaining({ search: "acme" }),
            }),
          })
        );
      });
    });
  });

  describe("Selection and bulk actions", () => {
    it("shows bulk action bar when contacts are selected", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: ["investor"] }, error: null });
        }
        return Promise.resolve(makeApiResponse([makeOrg({ company: "Acme Inc" })]));
      });

      renderPage();

      await waitFor(() => expect(screen.getByText("Acme Inc")).toBeInTheDocument());

      // Click org row toggle-expand button to expand it
      fireEvent.click(screen.getByText("Acme Inc"));

      await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());

      // Click the contact checkbox
      const contactCheckbox = screen.getByRole("checkbox", { name: "Select Alice Smith" });
      fireEvent.click(contactCheckbox);

      await waitFor(() => {
        expect(screen.getByText("1 selected")).toBeInTheDocument();
      });
    });

    it("clears selection when Clear selection is clicked", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(makeApiResponse([makeOrg()]));
      });

      renderPage();

      await waitFor(() => expect(screen.getByText("Acme Inc")).toBeInTheDocument());

      fireEvent.click(screen.getByText("Acme Inc"));
      await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());

      const contactCheckbox = screen.getByRole("checkbox", { name: "Select Alice Smith" });
      fireEvent.click(contactCheckbox);

      await waitFor(() => expect(screen.getByText("Clear selection")).toBeInTheDocument());

      fireEvent.click(screen.getByText("Clear selection"));

      await waitFor(() => {
        expect(screen.queryByText("Clear selection")).not.toBeInTheDocument();
      });
    });
  });

  describe("Pagination", () => {
    it("shows pagination controls when multiple pages exist", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve({
          data: {
            data: [makeOrg()],
            meta: { total: 100, page: 1, page_size: 50, total_pages: 2 },
          },
          error: null,
        });
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText("Previous")).toBeInTheDocument();
        expect(screen.getByText("Next")).toBeInTheDocument();
      });
    });

    it("Previous button is disabled on first page", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve({
          data: {
            data: [makeOrg()],
            meta: { total: 100, page: 1, page_size: 50, total_pages: 2 },
          },
          error: null,
        });
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText("Previous")).toBeDisabled();
      });
    });

    it("clicking Next navigates to page 2 via URL", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve({
          data: {
            data: [makeOrg()],
            meta: { total: 100, page: 1, page_size: 50, total_pages: 2 },
          },
          error: null,
        });
      });

      renderPage();

      await waitFor(() => expect(screen.getByText("Next")).toBeInTheDocument());

      fireEvent.click(screen.getByText("Next"));

      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining("page=2"),
        expect.anything()
      );
    });

    it("does not show pagination when only one page", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(makeApiResponse([makeOrg()]));
      });

      renderPage();

      await waitFor(() => expect(screen.getByText("Acme Inc")).toBeInTheDocument());

      expect(screen.queryByText("Previous")).not.toBeInTheDocument();
      expect(screen.queryByText("Next")).not.toBeInTheDocument();
    });
  });

  describe("Merge organizations modal", () => {
    it("shows merge button when two or more orgs are selected", async () => {
      mockGet.mockImplementation((path: string) => {
        if (path === "/api/v1/contacts/tags") {
          return Promise.resolve({ data: { data: [] }, error: null });
        }
        return Promise.resolve(
          makeApiResponse([
            makeOrg({ company: "Acme Inc", contacts: [makeContact({ id: "c1" })] }),
            makeOrg({
              company: "Beta Corp",
              contacts: [makeContact({ id: "c2", full_name: "Bob Jones" })],
            }),
          ])
        );
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText("Acme Inc")).toBeInTheDocument();
        expect(screen.getByText("Beta Corp")).toBeInTheDocument();
      });

      // Select all contacts in Acme Inc via org-level checkbox
      const acmeCheckbox = screen.getByRole("checkbox", {
        name: "Select all contacts in Acme Inc",
      });
      fireEvent.click(acmeCheckbox);

      const betaCheckbox = screen.getByRole("checkbox", {
        name: "Select all contacts in Beta Corp",
      });
      fireEvent.click(betaCheckbox);

      await waitFor(() => {
        expect(screen.getByText(/Merge 2 Orgs/)).toBeInTheDocument();
      });
    });
  });
});
