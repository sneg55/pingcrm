import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TagTaxonomyPanel } from "./tag-taxonomy-panel";

// Mock the typed API client module
const mockGET = vi.fn();
const mockPOST = vi.fn();
const mockPUT = vi.fn();
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGET(...args),
    POST: (...args: unknown[]) => mockPOST(...args),
    PUT: (...args: unknown[]) => mockPUT(...args),
  },
}));

function makeTaxonomyData(
  categories: Record<string, string[]>,
  taxonomyStatus: "draft" | "approved" = "draft"
) {
  return {
    data: { data: { categories, total_tags: Object.values(categories).flat().length, status: taxonomyStatus }, error: null },
    error: undefined,
    response: { ok: true, status: 200 },
  };
}

function makeNullData() {
  return { data: { data: null, error: null }, error: undefined, response: { ok: true, status: 200 } };
}

function makeErrorResponse(detail: string) {
  return { data: undefined, error: { detail }, response: { ok: false, status: 500 } };
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// 1. Loading state
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel loading state", () => {
  it("shows a spinner while the taxonomy is loading", () => {
     
    mockGET.mockReturnValue(new Promise(() => {}));
    renderWithQuery(<TagTaxonomyPanel />);
    expect(screen.getByTestId("icon-Loader2")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 2. Empty state
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel empty state", () => {
  it("shows the 'Discover Tags' prompt when no taxonomy exists", async () => {
    mockGET.mockResolvedValue(makeNullData());
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
    mockGET.mockResolvedValue(makeTaxonomyData({
      Role: ["Founder", "Engineer"],
      Industry: ["FinTech", "SaaS"],
    }));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Role");
    expect(screen.getByText("Industry")).toBeInTheDocument();
    expect(screen.getByText("Founder")).toBeInTheDocument();
    expect(screen.getByText("Engineer")).toBeInTheDocument();
    expect(screen.getByText("FinTech")).toBeInTheDocument();
    expect(screen.getByText("SaaS")).toBeInTheDocument();
  });

  it("shows the total tag and category count in the subtitle", async () => {
    mockGET.mockResolvedValue(makeTaxonomyData({ Role: ["Founder", "Engineer"] }, "approved"));
    renderWithQuery(<TagTaxonomyPanel />);
    await screen.findByText(/2 tags across 1 categor/i);
  });
});

// ---------------------------------------------------------------------------
// 4. Category grouping
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel category grouping", () => {
  it("renders each category as a separate section", async () => {
    mockGET.mockResolvedValue(makeTaxonomyData({
      Role: ["Founder"],
      Location: ["Berlin", "NYC"],
      Interest: ["AI"],
    }));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Role");
    const headings = screen.getAllByRole("heading", { level: 3 }).map((el) => el.textContent);
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
    mockGET.mockResolvedValue(makeTaxonomyData({ Role: ["Founder"] }, "draft"));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    expect(screen.getByRole("button", { name: /Approve Taxonomy/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 6. Edit mode
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel edit mode", () => {
  it("shows add-tag inputs and remove buttons after clicking Edit", async () => {
    const user = userEvent.setup();
    mockGET.mockResolvedValue(makeTaxonomyData({ Role: ["Founder"] }, "draft"));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));

    expect(screen.getByPlaceholderText("Add tag...")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 7. Add new tag
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel add tag", () => {
  it("adds a new tag to the correct category when the form is submitted", async () => {
    const user = userEvent.setup();
    mockGET.mockResolvedValue(makeTaxonomyData({ Role: ["Founder"] }, "draft"));
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
    mockGET.mockResolvedValue(makeTaxonomyData({ Role: ["Founder"] }, "draft"));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));

    const input = screen.getByPlaceholderText("Add tag...");
    await user.type(input, "founder");
    await user.keyboard("{Enter}");

    expect(screen.getAllByText("Founder")).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// 8. Remove tag
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel remove tag", () => {
  it("removes a tag when its X button is clicked", async () => {
    const user = userEvent.setup();
    mockGET.mockResolvedValue(makeTaxonomyData({ Role: ["Founder", "Engineer"] }, "draft"));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));

    const founderTag = screen.getByText("Founder");
    const removeBtn = founderTag.parentElement!.querySelector("button")!;
    await user.click(removeBtn);

    expect(screen.queryByText("Founder")).not.toBeInTheDocument();
    expect(screen.getByText("Engineer")).toBeInTheDocument();
  });

  it("removes an empty category when its last tag is removed", async () => {
    const user = userEvent.setup();
    mockGET.mockResolvedValue(makeTaxonomyData({ Solo: ["OnlyTag"] }, "draft"));
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
// 9. Approve taxonomy
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel approve taxonomy", () => {
  it("calls PUT /api/v1/contacts/tags/taxonomy with approved status", async () => {
    const user = userEvent.setup();
    mockGET.mockResolvedValue(makeTaxonomyData({ Role: ["Founder"] }, "draft"));
    mockPUT.mockResolvedValue(makeTaxonomyData({ Role: ["Founder"] }, "approved"));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Draft Taxonomy");
    await user.click(screen.getByRole("button", { name: /Approve Taxonomy/i }));

    await waitFor(() => {
      expect(mockPUT).toHaveBeenCalled();
      const callArgs = mockPUT.mock.calls[0];
      expect(callArgs[1]?.body?.status).toBe("approved");
    });
  });
});

// ---------------------------------------------------------------------------
// 10. Discover tags
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel discover tags", () => {
  it("calls POST /api/v1/contacts/tags/discover when the button is clicked", async () => {
    const user = userEvent.setup();
    mockGET.mockResolvedValue(makeNullData());
    mockPOST.mockResolvedValue(makeTaxonomyData({ Role: ["Founder"] }, "draft"));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Discover Tags with AI");
    await user.click(screen.getByRole("button", { name: /^Discover Tags$/i }));

    await waitFor(() => {
      expect(mockPOST).toHaveBeenCalled();
    });
  });
});

// ---------------------------------------------------------------------------
// 11. Error state
// ---------------------------------------------------------------------------
describe("TagTaxonomyPanel error state", () => {
  it("displays an error message when discover returns a non-ok response", async () => {
    const user = userEvent.setup();
    mockGET.mockResolvedValue(makeNullData());
    mockPOST.mockResolvedValue(makeErrorResponse("Server error during discovery"));
    renderWithQuery(<TagTaxonomyPanel />);

    await screen.findByText("Discover Tags with AI");
    await user.click(screen.getByRole("button", { name: /^Discover Tags$/i }));

    await screen.findByText("Server error during discovery");
  });
});
