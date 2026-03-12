import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TagTaxonomyPanel } from "./tag-taxonomy-panel";

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, "localStorage", { value: localStorageMock });

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

function makeTaxonomyResponse(
  categories: Record<string, string[]>,
  status: "draft" | "approved" = "draft"
) {
  return {
    ok: true,
    json: async () => ({
      data: { categories, total_tags: Object.values(categories).flat().length, status },
    }),
  };
}

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorageMock.clear();
  localStorageMock.setItem("access_token", "test-token");
});

// ---------------------------------------------------------------------------
// 1. Loading state
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel loading state", () => {
  it("shows a spinner while the taxonomy is loading", () => {
    // Never-resolving fetch keeps isLoading === true
    mockFetch.mockReturnValue(new Promise(() => {}));
    renderWithQuery(<TagTaxonomyPanel />);
    expect(screen.getByTestId("icon-Loader2")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 2. Empty state (no taxonomy yet)
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel empty state", () => {
  it("shows the 'Discover Tags' prompt when no taxonomy exists", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ data: null }),
    });
    renderWithQuery(<TagTaxonomyPanel />);
    await screen.findByText("Discover Tags with AI");
    expect(screen.getByRole("button", { name: /Discover Tags/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 3. Tag list renders with names
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel renders tag names", () => {
  it("displays category headings and tag names from the taxonomy", async () => {
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({
        Role: ["Founder", "Engineer"],
        Industry: ["FinTech", "SaaS"],
      })
    );
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Role");
    expect(screen.getByText("Industry")).toBeInTheDocument();
    expect(screen.getByText("Founder")).toBeInTheDocument();
    expect(screen.getByText("Engineer")).toBeInTheDocument();
    expect(screen.getByText("FinTech")).toBeInTheDocument();
    expect(screen.getByText("SaaS")).toBeInTheDocument();
  });

  it("shows the total tag and category count in the subtitle", async () => {
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({ Role: ["Founder", "Engineer"] }, "approved")
    );
    renderWithQuery(<TagTaxonomyPanel />);
    await screen.findByText(/2 tags across 1 categor/i);
  });
});

// ---------------------------------------------------------------------------
// 4. Category grouping
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel category grouping", () => {
  it("renders each category as a separate section", async () => {
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({
        Role: ["Founder"],
        Location: ["Berlin", "NYC"],
        Interest: ["AI"],
      })
    );
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Role");
    const headings = screen
      .getAllByRole("heading", { level: 3 })
      .map((el) => el.textContent);
    expect(headings).toContain("Role");
    expect(headings).toContain("Location");
    expect(headings).toContain("Interest");
  });
});

// ---------------------------------------------------------------------------
// 5. Draft taxonomy status banner
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel draft banner", () => {
  it("shows the draft banner with Approve button for draft taxonomy", async () => {
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({ Role: ["Founder"] }, "draft")
    );
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    expect(screen.getByRole("button", { name: /Approve Taxonomy/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 6. Edit mode — entering edit and seeing add-tag inputs
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel edit mode", () => {
  it("shows add-tag inputs and remove buttons after clicking Edit", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({ Role: ["Founder"] }, "draft")
    );
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));

    expect(screen.getByPlaceholderText("Add tag...")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 7. Add new tag functionality
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel add tag", () => {
  it("adds a new tag to the correct category when the form is submitted", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({ Role: ["Founder"] }, "draft")
    );
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));

    const input = screen.getByPlaceholderText("Add tag...");
    await user.type(input, "Investor");
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Investor")).toBeInTheDocument();
  });

  it("does not add a duplicate tag (case-insensitive)", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({ Role: ["Founder"] }, "draft")
    );
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));

    const input = screen.getByPlaceholderText("Add tag...");
    await user.type(input, "founder");
    await user.keyboard("{Enter}");

    // Only one "Founder" badge should exist
    expect(screen.getAllByText("Founder")).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// 8. Remove tag functionality
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel remove tag", () => {
  it("removes a tag when its X button is clicked", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({ Role: ["Founder", "Engineer"] }, "draft")
    );
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));

    // Each tag has an X icon button; find the one next to "Founder"
    const founderTag = screen.getByText("Founder");
    const removeBtn = founderTag.parentElement!.querySelector("button")!;
    await user.click(removeBtn);

    expect(screen.queryByText("Founder")).not.toBeInTheDocument();
    expect(screen.getByText("Engineer")).toBeInTheDocument();
  });

  it("removes an empty category when its last tag is removed", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue(
      makeTaxonomyResponse({ Solo: ["OnlyTag"] }, "draft")
    );
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));

    const tagEl = screen.getByText("OnlyTag");
    const removeBtn = tagEl.parentElement!.querySelector("button")!;
    await user.click(removeBtn);

    expect(screen.queryByText("OnlyTag")).not.toBeInTheDocument();
    expect(screen.queryByText("Solo")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 9. Save / approve taxonomy
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel approve taxonomy", () => {
  it("calls PUT /api/v1/contacts/tags/taxonomy with approved status", async () => {
    const user = userEvent.setup();

    // First call: GET taxonomy
    mockFetch
      .mockResolvedValueOnce(makeTaxonomyResponse({ Role: ["Founder"] }, "draft"))
      // Second call: PUT (approve)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            categories: { Role: ["Founder"] },
            total_tags: 1,
            status: "approved",
          },
        }),
      })
      // Third call: re-fetch after invalidation
      .mockResolvedValue(makeTaxonomyResponse({ Role: ["Founder"] }, "approved"));

    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /Approve Taxonomy/i }));

    await waitFor(() => {
      const putCall = mockFetch.mock.calls.find(
        ([url, opts]) => url.includes("/taxonomy") && opts?.method === "PUT"
      );
      expect(putCall).toBeDefined();
      const body = JSON.parse(putCall![1].body);
      expect(body.status).toBe("approved");
    });
  });
});

// ---------------------------------------------------------------------------
// 10. Discover tags
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel discover tags", () => {
  it("calls POST /api/v1/contacts/tags/discover when the button is clicked", async () => {
    const user = userEvent.setup();

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: null }),
      })
      // Discover response
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            categories: { Role: ["Founder"] },
            total_tags: 1,
            status: "draft",
          },
        }),
      })
      // Re-fetch after invalidation
      .mockResolvedValue(makeTaxonomyResponse({ Role: ["Founder"] }, "draft"));

    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Discover Tags with AI");
    await user.click(screen.getByRole("button", { name: /^Discover Tags$/i }));

    await waitFor(() => {
      const postCall = mockFetch.mock.calls.find(
        ([url, opts]) => url.includes("/discover") && opts?.method === "POST"
      );
      expect(postCall).toBeDefined();
    });
  });
});

// ---------------------------------------------------------------------------
// 11. Error banner on discover failure
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel error state", () => {
  it("displays an error message when discover returns a non-ok response", async () => {
    const user = userEvent.setup();

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: null }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: "Server error during discovery" }),
      });

    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Discover Tags with AI");
    await user.click(screen.getByRole("button", { name: /^Discover Tags$/i }));

    await screen.findByText("Server error during discovery");
  });
});
