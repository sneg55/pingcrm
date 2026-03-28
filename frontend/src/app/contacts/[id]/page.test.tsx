import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ContactDetailPage from "./page";

/* ── API client mock ── */
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn().mockResolvedValue({ data: { data: [] } }),
    POST: vi.fn().mockResolvedValue({ data: { data: {} } }),
    PUT: vi.fn().mockResolvedValue({ data: { data: {} } }),
    DELETE: vi.fn().mockResolvedValue({ data: { data: {} } }),
  },
}));

/* ── use-contacts hook mocks ── */
const mockUseContact = vi.fn();
const mockUseUpdateContact = vi.fn();
const mockUseDeleteContact = vi.fn();
const mockUseContactDuplicates = vi.fn();
const mockUseMergeContacts = vi.fn();
const mockUseContactActivity = vi.fn();
const mockUseContacts = vi.fn();

vi.mock("@/hooks/use-contacts", () => ({
  useContact: (...args: unknown[]) => mockUseContact(...args),
  useUpdateContact: (...args: unknown[]) => mockUseUpdateContact(...args),
  useDeleteContact: (...args: unknown[]) => mockUseDeleteContact(...args),
  useContactDuplicates: (...args: unknown[]) => mockUseContactDuplicates(...args),
  useMergeContacts: (...args: unknown[]) => mockUseMergeContacts(...args),
  useContactActivity: (...args: unknown[]) => mockUseContactActivity(...args),
  useContacts: (...args: unknown[]) => mockUseContacts(...args),
}));

/* ── use-suggestions hook mocks ── */
const mockUseContactSuggestion = vi.fn();
const mockUseUpdateSuggestion = vi.fn();
const mockUseSendMessage = vi.fn();

vi.mock("@/hooks/use-suggestions", () => ({
  useContactSuggestion: (...args: unknown[]) => mockUseContactSuggestion(...args),
  useUpdateSuggestion: (...args: unknown[]) => mockUseUpdateSuggestion(...args),
  useSendMessage: (...args: unknown[]) => mockUseSendMessage(...args),
}));

/* ── MessageEditor mock ── */
vi.mock("@/components/message-editor", () => ({
  MessageEditor: ({ onSend }: { onSend: (m: string, c: string) => void }) => (
    <div data-testid="message-editor">
      <button onClick={() => onSend("Hello", "email")}>Send</button>
    </div>
  ),
}));

/* ── InlineListField mock ── */
vi.mock("@/components/inline-list-field", () => ({
  InlineListField: ({
    label,
    values,
  }: {
    label: string;
    values: string[];
    onSave: (v: string[]) => void;
    copyable?: boolean;
    isLink?: boolean;
    linkPrefix?: string;
  }) => (
    <div data-testid={`inline-list-${label.toLowerCase()}`}>
      <span>{label}</span>
      {values.map((v, i) => (
        <span key={i}>{v}</span>
      ))}
    </div>
  ),
}));

/* ── date-fns mock ── */
vi.mock("date-fns", () => ({
  formatDistanceToNow: () => "2 months ago",
  format: (_d: unknown, fmt: string) =>
    fmt === "MMM yyyy" ? "Jan 2025" : fmt === "h:mm a" ? "10:00 AM" : fmt === "MMM d, yyyy" ? "Jan 1, 2025" : fmt === "MMM d" ? "Jan 1" : "Jan 1",
  isToday: () => false,
  isYesterday: () => false,
  isSameDay: () => true,
}));

/* ── next/navigation mock ── */
const mockPush = vi.fn();
const mockReplace = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: vi.fn(() => ({ id: "test-id" })),
  useRouter: vi.fn(() => ({ push: mockPush, replace: mockReplace, back: vi.fn() })),
  useSearchParams: vi.fn(() => ({ get: vi.fn(() => null) })),
  usePathname: vi.fn(() => "/contacts/test-id"),
}));

/* ── useAuth mock ── */
vi.mock("@/hooks/use-auth", () => ({
  useAuth: vi.fn(() => ({
    user: { id: "u1", email: "test@example.com", full_name: "Test User" },
    isLoading: false,
  })),
}));

/* ── Helpers ── */

function makeContact(overrides: Record<string, unknown> = {}) {
  return {
    id: "test-id",
    user_id: "u1",
    full_name: "Alice Smith",
    given_name: "Alice",
    family_name: "Smith",
    emails: ["alice@example.com"],
    phones: ["555-1234"],
    company: "Acme Inc",
    title: "Engineer",
    twitter_handle: "@alice",
    twitter_bio: null,
    telegram_username: "alice_tg",
    telegram_bio: null,
    location: "New York",
    birthday: "1990-01-01",
    linkedin_url: "https://linkedin.com/in/alice",
    avatar_url: null,
    tags: ["investor", "founder"],
    notes: null,
    relationship_score: 7,
    interaction_count: 12,
    last_interaction_at: "2025-01-15T10:00:00Z",
    last_followup_at: null,
    priority_level: "medium",
    source: "google",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

function makeActivityData() {
  return {
    score: 7,
    dimensions: {
      reciprocity: { value: 3, max: 4 },
      recency: { value: 2, max: 3 },
      frequency: { value: 1, max: 2 },
      breadth: { value: 1, max: 1 },
    },
    stats: {
      inbound_365d: 5,
      outbound_365d: 7,
      count_30d: 2,
      count_90d: 6,
      platforms: ["email"],
      interaction_count: 12,
      first_interaction_at: "2025-01-15T00:00:00Z",
    },
    monthly_trend: [],
  };
}

const noopMutation = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isError: false,
  isSuccess: false,
  reset: vi.fn(),
};

function setupDefaultMocks() {
  const contact = makeContact();
  mockUseContact.mockReturnValue({
    data: { data: contact },
    isLoading: false,
    isError: false,
  });
  mockUseUpdateContact.mockReturnValue(noopMutation);
  mockUseDeleteContact.mockReturnValue(noopMutation);
  mockUseContactDuplicates.mockReturnValue({ data: { data: [] }, isLoading: false });
  mockUseMergeContacts.mockReturnValue(noopMutation);
  mockUseContactActivity.mockReturnValue({ data: makeActivityData(), isLoading: false });
  mockUseContacts.mockReturnValue({ data: { data: [] }, isLoading: false });
  mockUseContactSuggestion.mockReturnValue(null);
  mockUseUpdateSuggestion.mockReturnValue(noopMutation);
  mockUseSendMessage.mockReturnValue(noopMutation);
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPage() {
  return render(<ContactDetailPage />, { wrapper });
}

/* ══════════════════════════════════════════════
   Tests
══════════════════════════════════════════════ */

describe("ContactDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  /* 1 — Loading state */
  it("shows animated skeleton while contact is loading", () => {
    mockUseContact.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = renderPage();
    expect(container.querySelector("[class*='animate-pulse']")).toBeTruthy();
  });

  /* 2 — Error / not found */
  it("shows contact not found message on error", () => {
    mockUseContact.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderPage();
    expect(screen.getByText("Contact not found.")).toBeInTheDocument();
    expect(screen.getByText("Back to contacts")).toBeInTheDocument();
  });

  /* 3 — Header: contact name */
  it("renders contact name in the header", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Alice Smith" })).toBeInTheDocument();
  });

  /* 4 — Header: avatar initials */
  it("renders avatar with initials when no avatar_url", () => {
    renderPage();
    // Initials for "Alice Smith" = "AS"
    expect(screen.getByText("AS")).toBeInTheDocument();
  });

  /* 5 — Header: avatar image */
  it("renders img tag when contact has avatar_url", () => {
    mockUseContact.mockReturnValue({
      data: { data: makeContact({ avatar_url: "https://example.com/avatar.png" }) },
      isLoading: false,
      isError: false,
    });
    renderPage();
    const img = screen.getByRole("img", { name: "Alice Smith" });
    expect(img).toHaveAttribute("src", "https://example.com/avatar.png");
  });

  /* 6 — Tags section */
  it("renders contact tags as pills", () => {
    renderPage();
    expect(screen.getByText("investor")).toBeInTheDocument();
    expect(screen.getByText("founder")).toBeInTheDocument();
  });

  /* 7 — Tags: add tag button */
  it("shows add tag button (+)", () => {
    renderPage();
    expect(screen.getByText("+")).toBeInTheDocument();
  });

  /* 8 — Tags: input appears on add click */
  it("shows tag input when + is clicked", () => {
    renderPage();
    fireEvent.click(screen.getByText("+"));
    expect(screen.getByPlaceholderText("Tag name...")).toBeInTheDocument();
  });

  /* 9 — Detail fields: company shown */
  it("renders company in Contact Details sidebar", () => {
    renderPage();
    expect(screen.getByText("Company")).toBeInTheDocument();
    expect(screen.getByText("Acme Inc")).toBeInTheDocument();
  });

  /* 10 — Detail fields: title shown */
  it("renders title in Contact Details sidebar", () => {
    renderPage();
    expect(screen.getByText("Title")).toBeInTheDocument();
    expect(screen.getByText("Engineer")).toBeInTheDocument();
  });

  /* 11 — Detail fields: dash for missing field */
  it("renders em-dash when a field has no value", () => {
    mockUseContact.mockReturnValue({
      data: { data: makeContact({ location: null }) },
      isLoading: false,
      isError: false,
    });
    renderPage();
    // The InlineField renders "—" for a null value
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  /* 12 — Detail fields: edit mode for inline field */
  it("opens edit input when pencil icon is hovered/clicked", async () => {
    renderPage();
    // Find the Company row and click its edit button
    const companyLabel = screen.getByText("Company");
    const companyRow = companyLabel.closest("div[class*='group']");
    expect(companyRow).toBeTruthy();
    const editButton = companyRow!.querySelector("button");
    expect(editButton).toBeTruthy();
    fireEvent.click(editButton!);
    // After clicking, an input with the current value should appear
    const input = companyRow!.querySelector("input") as HTMLInputElement;
    expect(input).toBeTruthy();
    expect(input.value).toBe("Acme Inc");
  });

  /* 13 — Edit mode: Save/Cancel buttons */
  it("shows Save and Cancel buttons in inline edit mode", () => {
    renderPage();
    const titleLabel = screen.getByText("Title");
    const titleRow = titleLabel.closest("div[class*='group']");
    const editButton = titleRow!.querySelector("button");
    fireEvent.click(editButton!);
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  /* 14 — Edit mode: cancel restores original value */
  it("cancels edit and restores original value", () => {
    renderPage();
    const titleLabel = screen.getByText("Title");
    const titleRow = titleLabel.closest("div[class*='group']");
    const editButton = titleRow!.querySelector("button");
    fireEvent.click(editButton!);
    const input = titleRow!.querySelector("input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "CEO" } });
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.getByText("Engineer")).toBeInTheDocument();
  });

  /* 15 — Relationship health section */
  it("renders Relationship Health card when activity data is present", () => {
    renderPage();
    expect(screen.getByText("Relationship Health")).toBeInTheDocument();
    expect(screen.getByText("Reciprocity")).toBeInTheDocument();
    expect(screen.getByText("Recency")).toBeInTheDocument();
    expect(screen.getByText("Frequency")).toBeInTheDocument();
    expect(screen.getByText("Breadth")).toBeInTheDocument();
  });

  /* 16 — Activity: interaction stats */
  it("renders total interactions and last contacted in health card", () => {
    renderPage();
    expect(screen.getByText("Total interactions")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Last contacted")).toBeInTheDocument();
    expect(screen.getByText("2 months ago")).toBeInTheDocument();
  });

  /* 16b — Activity: Since date from first_interaction_at */
  it("renders Since date from first_interaction_at in health card", () => {
    renderPage();
    expect(screen.getByText("Since")).toBeInTheDocument();
    // date-fns format mock returns "Jan 2025" for "MMM yyyy"
    expect(screen.getByText("Jan 2025")).toBeInTheDocument();
  });

  /* 17 — Activity: loading state */
  it("shows activity skeleton while activity is loading", () => {
    mockUseContactActivity.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderPage();
    const pulseEls = container.querySelectorAll("[class*='animate-pulse']");
    expect(pulseEls.length).toBeGreaterThan(0);
  });

  /* 18 — Kebab menu: opens on click */
  it("opens kebab menu when MoreVertical button is clicked", () => {
    renderPage();
    const menuButton = screen.getByTitle(/archive contact/i)
      ? screen.getAllByRole("button").find((b) => b.querySelector("[data-testid='icon-MoreVertical']"))
      : null;
    // MoreVertical icon inside a button triggers menu open
    const moreBtn = screen.getAllByRole("button").find(
      (b) => b.querySelector("[data-testid='icon-MoreVertical']")
    );
    expect(moreBtn).toBeTruthy();
    fireEvent.click(moreBtn!);
    expect(screen.getByText("Refresh details")).toBeInTheDocument();
    expect(screen.getByText("Enrich with Apollo")).toBeInTheDocument();
    expect(screen.getByText("Delete contact")).toBeInTheDocument();
  });

  /* 19 — Kebab: delete triggers confirmation modal */
  it("shows delete confirmation modal after clicking Delete contact", () => {
    renderPage();
    const moreBtn = screen.getAllByRole("button").find(
      (b) => b.querySelector("[data-testid='icon-MoreVertical']")
    );
    fireEvent.click(moreBtn!);
    fireEvent.click(screen.getByText("Delete contact"));
    expect(screen.getByText("Delete contact?")).toBeInTheDocument();
    expect(screen.getByText(/permanently delete/i)).toBeInTheDocument();
  });

  /* 20 — Kebab: archive button calls updateContact */
  it("calls updateContact with archived priority when archive button is clicked", () => {
    const mutate = vi.fn();
    mockUseUpdateContact.mockReturnValue({ ...noopMutation, mutate });
    renderPage();
    const archiveBtn = screen.getByTitle("Archive contact");
    fireEvent.click(archiveBtn);
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ input: { priority_level: "archived" } }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  /* 21 — Delete confirmation: cancel hides modal */
  it("hides delete confirmation when Cancel is clicked", () => {
    renderPage();
    const moreBtn = screen.getAllByRole("button").find(
      (b) => b.querySelector("[data-testid='icon-MoreVertical']")
    );
    fireEvent.click(moreBtn!);
    fireEvent.click(screen.getByText("Delete contact"));
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Delete contact?")).not.toBeInTheDocument();
  });

  /* 22 — Delete confirmation: confirm calls deleteContact */
  it("calls deleteContact.mutate when confirm delete is clicked", () => {
    const mutate = vi.fn();
    mockUseDeleteContact.mockReturnValue({ ...noopMutation, mutate });
    renderPage();
    const moreBtn = screen.getAllByRole("button").find(
      (b) => b.querySelector("[data-testid='icon-MoreVertical']")
    );
    fireEvent.click(moreBtn!);
    fireEvent.click(screen.getByText("Delete contact"));
    // Click the red Delete button inside the modal
    const deleteButtons = screen.getAllByText("Delete");
    const confirmBtn = deleteButtons.find((b) => b.tagName === "BUTTON");
    fireEvent.click(confirmBtn!);
    expect(mutate).toHaveBeenCalledWith("test-id", expect.any(Object));
  });

  /* 23 — Duplicate card: hidden when no duplicates */
  it("does not render Possible Duplicates card when there are no duplicates", () => {
    mockUseContactDuplicates.mockReturnValue({ data: { data: [] }, isLoading: false });
    renderPage();
    expect(screen.queryByText("Possible Duplicates")).not.toBeInTheDocument();
  });

  /* 24 — Duplicate card: shown when duplicates exist */
  it("renders Possible Duplicates card when duplicates exist", () => {
    mockUseContactDuplicates.mockReturnValue({
      data: {
        data: [
          {
            id: "dup-id",
            full_name: "Alice S.",
            given_name: "Alice",
            family_name: "S.",
            emails: ["alice@other.com"],
            company: "Other Corp",
            twitter_handle: null,
            telegram_username: null,
            source: "google",
            score: 0.9,
          },
        ],
      },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("Possible Duplicates")).toBeInTheDocument();
    expect(screen.getByText("Alice S.")).toBeInTheDocument();
  });

  /* 25 — Duplicate card: merge and dismiss buttons */
  it("shows Merge and Not the same buttons in duplicate card", () => {
    mockUseContactDuplicates.mockReturnValue({
      data: {
        data: [
          {
            id: "dup-id",
            full_name: "Alice S.",
            emails: ["alice@other.com"],
            company: null,
            twitter_handle: null,
            telegram_username: null,
            source: "google",
            score: 0.88,
          },
        ],
      },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("Merge")).toBeInTheDocument();
    expect(screen.getByText("Not the same")).toBeInTheDocument();
  });

  /* 26 — Notes section: AddNoteInput renders */
  it("renders the Add a note textarea", () => {
    renderPage();
    expect(screen.getByPlaceholderText("Add a note...")).toBeInTheDocument();
  });

  /* 27 — Notes: Save note button appears on focus */
  it("shows Save note button when textarea is focused", () => {
    renderPage();
    const textarea = screen.getByPlaceholderText("Add a note...");
    fireEvent.focus(textarea);
    expect(screen.getByText("Save note")).toBeInTheDocument();
  });

  /* 28 — Notes: cancel clears textarea */
  it("hides Save note button and clears text when Cancel is clicked", () => {
    renderPage();
    const textarea = screen.getByPlaceholderText("Add a note...");
    fireEvent.focus(textarea);
    fireEvent.change(textarea, { target: { value: "My note" } });
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Save note")).not.toBeInTheDocument();
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  /* 29 — Timeline: empty state */
  it("shows empty interaction state when there are no interactions", () => {
    renderPage();
    expect(screen.getByText("No interactions yet")).toBeInTheDocument();
  });

  /* 30 — Timeline: renders interactions */
  it("renders timeline messages when interactions exist", async () => {
    const { client } = await import("@/lib/api-client");
    (client.GET as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/{contact_id}/interactions") {
        return Promise.resolve({
          data: {
            data: [
              {
                id: "i1",
                platform: "email",
                direction: "inbound",
                content_preview: "Hello from Alice",
                occurred_at: "2025-01-15T10:00:00Z",
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Hello from Alice")).toBeInTheDocument();
    });
  });

  /* 30b — Timeline: HTML entities in content_preview are decoded */
  it("decodes HTML entities in interaction content", async () => {
    const { client } = await import("@/lib/api-client");
    (client.GET as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/{contact_id}/interactions") {
        return Promise.resolve({
          data: {
            data: [
              {
                id: "i2",
                platform: "email",
                direction: "inbound",
                content_preview: "it&#39;s great to meet you",
                occurred_at: "2025-01-15T10:00:00Z",
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("it's great to meet you")).toBeInTheDocument();
    });
  });

  /* 31 — Back navigation: contacts link exists */
  it("shows Back to contacts link on error state", () => {
    mockUseContact.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderPage();
    const link = screen.getByText("Back to contacts");
    expect(link).toHaveAttribute("href", "/contacts");
  });

  /* 32 — Priority toggle */
  it("renders priority level buttons (high/medium/low)", () => {
    renderPage();
    expect(screen.getByTitle(/High priority/)).toBeInTheDocument();
    expect(screen.getByTitle(/Medium priority/)).toBeInTheDocument();
    expect(screen.getByTitle(/Low priority/)).toBeInTheDocument();
  });

  /* 33 — Priority: clicking calls updateContact */
  it("calls updateContact when a priority level is clicked", () => {
    const mutate = vi.fn();
    mockUseUpdateContact.mockReturnValue({ ...noopMutation, mutate });
    renderPage();
    fireEvent.click(screen.getByTitle(/High priority/));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ input: { priority_level: "high" } })
    );
  });

  /* 34 — Relationship score pill */
  it("shows relationship score label (Warm for score 7)", () => {
    renderPage();
    expect(screen.getByText("Warm")).toBeInTheDocument();
  });

  /* 35 — Contact Details section heading (appears as both mobile toggle button and section heading) */
  it("renders Contact Details section heading", () => {
    renderPage();
    expect(screen.getAllByText("Contact Details").length).toBeGreaterThanOrEqual(1);
  });

  /* 36 — Auto-tag menu item */
  it("shows Auto-tag with AI in kebab menu", () => {
    renderPage();
    const moreBtn = screen.getAllByRole("button").find(
      (b) => b.querySelector("[data-testid='icon-MoreVertical']")
    );
    fireEvent.click(moreBtn!);
    expect(screen.getByText("Auto-tag with AI")).toBeInTheDocument();
  });

  /* 37 — Related Contacts card: hidden when no related contacts */
  it("does not render Related Contacts card when there are no related contacts", () => {
    // Default mock returns { data: { data: [] } } for all GET calls, so related is empty
    renderPage();
    expect(screen.queryByText("Related Contacts")).not.toBeInTheDocument();
  });

  /* 38 — Related Contacts card: renders when related contacts exist */
  it("renders Related Contacts card when related contacts exist", async () => {
    const { client } = await import("@/lib/api-client");
    (client.GET as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if ((url as string).includes("/related")) {
        return Promise.resolve({
          data: {
            data: [
              {
                id: "rel-1",
                full_name: "Bob Jones",
                title: "Engineer",
                company: "Acme Corp",
                avatar_url: null,
                relationship_score: 5,
                reasons: ["Same company"],
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Related Contacts")).toBeInTheDocument();
    });
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    expect(screen.getByText("Engineer @ Acme Corp")).toBeInTheDocument();
  });

  /* 39 — Related Contacts card: renders multiple reasons as pills */
  it("renders all reason pills for a related contact", async () => {
    const { client } = await import("@/lib/api-client");
    (client.GET as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if ((url as string).includes("/related")) {
        return Promise.resolve({
          data: {
            data: [
              {
                id: "rel-2",
                full_name: "Carol White",
                title: "Designer",
                company: "BetaCo",
                avatar_url: null,
                relationship_score: 8,
                reasons: ["Same company", "Shared tag: Founder"],
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Carol White")).toBeInTheDocument();
    });
    expect(screen.getByText("Designer @ BetaCo")).toBeInTheDocument();
    expect(screen.getByText("Shared tag: Founder")).toBeInTheDocument();
  });

  /* 40 — Timeline: outbound message renders on the right side */
  it("renders outbound interaction message in the timeline", async () => {
    const { client } = await import("@/lib/api-client");
    (client.GET as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/{contact_id}/interactions") {
        return Promise.resolve({
          data: {
            data: [
              {
                id: "out-1",
                platform: "email",
                direction: "outbound",
                content_preview: "Hey Alice, great to connect!",
                occurred_at: "2025-01-15T10:00:00Z",
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Hey Alice, great to connect!")).toBeInTheDocument();
    });
  });

  /* 41 — Timeline: manual note renders via NoteItem */
  it("renders a manual note interaction in the timeline", async () => {
    const { client } = await import("@/lib/api-client");
    (client.GET as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/{contact_id}/interactions") {
        return Promise.resolve({
          data: {
            data: [
              {
                id: "note-1",
                platform: "manual",
                direction: "outbound",
                content_preview: "Met at the conference last week",
                occurred_at: "2025-01-15T10:00:00Z",
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Met at the conference last week")).toBeInTheDocument();
    });
    // Notes render with a "Note" label
    expect(screen.getByText(/Note/)).toBeInTheDocument();
  });

  /* 42 — Message composer: shows "Write a message..." when no suggestion */
  it("renders Write a message collapsed header when no follow-up suggestion", () => {
    mockUseContactSuggestion.mockReturnValue(null);
    renderPage();
    expect(screen.getByText("Write a message...")).toBeInTheDocument();
  });

  /* 43 — Message composer: expands editor on click */
  it("expands message editor when the composer header is clicked", () => {
    mockUseContactSuggestion.mockReturnValue(null);
    renderPage();
    const composerBtn = screen.getByText("Write a message...").closest("button");
    expect(composerBtn).toBeTruthy();
    fireEvent.click(composerBtn!);
    expect(screen.getByTestId("message-editor")).toBeInTheDocument();
  });

  /* 44 — Message composer: shows Follow-up suggested when suggestion present */
  it("renders Follow-up suggested header when a suggestion exists", () => {
    mockUseContactSuggestion.mockReturnValue({
      id: "sug-1",
      suggested_message: "Hey Alice, how are you?",
      suggested_channel: "email",
      status: "pending",
    });
    renderPage();
    expect(screen.getByText("Follow-up suggested")).toBeInTheDocument();
  });
});
