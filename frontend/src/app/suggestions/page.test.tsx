import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SuggestionsPage from "./page";

// Mock api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    DELETE: vi.fn(),
  },
}));

// Mock use-suggestions hook
const mockUseSuggestions = vi.fn();
const mockUpdateSuggestionMutate = vi.fn();
const mockGenerateSuggestionsMutate = vi.fn();
const mockSendMessageMutateAsync = vi.fn();

vi.mock("@/hooks/use-suggestions", () => ({
  useSuggestions: (...args: unknown[]) => mockUseSuggestions(...args),
  useUpdateSuggestion: () => ({
    mutate: mockUpdateSuggestionMutate,
    isPending: false,
  }),
  useGenerateSuggestions: () => ({
    mutate: mockGenerateSuggestionsMutate,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    data: undefined,
  }),
  useSendMessage: () => ({
    mutateAsync: mockSendMessageMutateAsync,
    isPending: false,
  }),
}));

// Mock MessageEditor to simplify rendering in expanded state tests
vi.mock("@/components/message-editor", () => ({
  MessageEditor: ({
    initialMessage,
    onSend,
  }: {
    initialMessage?: string;
    onSend?: (msg: string, ch: string) => void;
  }) => (
    <div data-testid="message-editor">
      <span data-testid="editor-message">{initialMessage}</span>
      <button
        data-testid="send-button"
        onClick={() => onSend?.("Hello!", "telegram")}
      >
        Send
      </button>
    </div>
  ),
}));

function makeSuggestion(overrides: Record<string, unknown> = {}) {
  return {
    id: "s1",
    contact_id: "c1",
    contact: {
      id: "c1",
      full_name: "Alice Smith",
      given_name: "Alice",
      family_name: "Smith",
      company: "Acme Inc",
      title: "Engineer",
      avatar_url: null,
      telegram_username: "alice_tg",
      twitter_handle: null,
      last_interaction_at: "2026-01-01T10:00:00Z",
    },
    trigger_type: "time_based",
    suggested_message: "Hey Alice, how have you been?",
    suggested_channel: "telegram" as const,
    status: "pending" as const,
    scheduled_for: null,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPage() {
  return render(<SuggestionsPage />, { wrapper });
}

describe("SuggestionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page heading", () => {
    mockUseSuggestions.mockReturnValue({ data: undefined, isLoading: false });
    renderPage();
    expect(screen.getByText("Suggestions Digest")).toBeInTheDocument();
    expect(screen.getByText("AI-suggested follow-ups for your network")).toBeInTheDocument();
  });

  it("renders Generate new suggestions button", () => {
    mockUseSuggestions.mockReturnValue({ data: undefined, isLoading: false });
    renderPage();
    expect(screen.getAllByText("Generate new suggestions").length).toBeGreaterThan(0);
  });

  it("shows loading state with skeleton cards", () => {
    mockUseSuggestions.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderPage();
    const skeletons = container.querySelectorAll("[class*='animate-pulse']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows empty state when there are no pending suggestions", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [] },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("No pending suggestions")).toBeInTheDocument();
    expect(
      screen.getByText(/Generate new suggestions to get started/)
    ).toBeInTheDocument();
  });

  it("renders suggestion card with contact name and message preview", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("Hey Alice, how have you been?")).toBeInTheDocument();
  });

  it("renders multiple suggestion cards", () => {
    mockUseSuggestions.mockReturnValue({
      data: {
        data: [
          makeSuggestion({ id: "s1", contact: { ...makeSuggestion().contact, full_name: "Alice Smith" } }),
          makeSuggestion({
            id: "s2",
            contact_id: "c2",
            contact: {
              id: "c2",
              full_name: "Bob Jones",
              given_name: "Bob",
              family_name: "Jones",
              company: null,
              title: null,
              avatar_url: null,
              telegram_username: null,
              twitter_handle: null,
              last_interaction_at: null,
            },
            suggested_message: "Hi Bob!",
          }),
        ],
      },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    expect(screen.getByText("Hi Bob!")).toBeInTheDocument();
  });

  it("shows pending count badge next to heading", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion(), makeSuggestion({ id: "s2" })] },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("does not show count badge when no pending suggestions", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [] },
      isLoading: false,
    });
    renderPage();
    // The count badge only appears when pendingSuggestions.length > 0
    // No badge element with a number inside the heading
    const heading = screen.getByText("Suggestions Digest");
    expect(heading.closest("h1")?.querySelector("span")).toBeNull();
  });

  it("shows birthday trigger label for birthday suggestions", () => {
    mockUseSuggestions.mockReturnValue({
      data: {
        data: [makeSuggestion({ trigger_type: "birthday" })],
      },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("Birthday coming up")).toBeInTheDocument();
  });

  it("shows scheduled follow-up trigger label for scheduled suggestions", () => {
    mockUseSuggestions.mockReturnValue({
      data: {
        data: [makeSuggestion({ trigger_type: "scheduled" })],
      },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("Scheduled follow-up")).toBeInTheDocument();
  });

  it("shows Revival badge for time_based suggestions with 90+ day gap", () => {
    // last_interaction_at far enough in the past to exceed 90 days
    mockUseSuggestions.mockReturnValue({
      data: {
        data: [
          makeSuggestion({
            trigger_type: "time_based",
            contact: {
              ...makeSuggestion().contact,
              last_interaction_at: "2024-01-01T00:00:00Z",
            },
          }),
        ],
      },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("Revival")).toBeInTheDocument();
  });

  it("does not show non-pending suggestions", () => {
    mockUseSuggestions.mockReturnValue({
      data: {
        data: [
          makeSuggestion({ status: "snoozed" }),
          makeSuggestion({ id: "s2", status: "dismissed" }),
          makeSuggestion({ id: "s3", status: "sent" }),
        ],
      },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("No pending suggestions")).toBeInTheDocument();
  });

  it("expands a suggestion card on click to show message editor", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    renderPage();

    const card = screen.getByText("Alice Smith").closest("div[class*='rounded-xl']")!;
    fireEvent.click(card);

    expect(screen.getByTestId("message-editor")).toBeInTheDocument();
  });

  it("shows Snooze button in expanded card", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    renderPage();

    const card = screen.getByText("Alice Smith").closest("div[class*='rounded-xl']")!;
    fireEvent.click(card);

    expect(screen.getByText("Snooze")).toBeInTheDocument();
  });

  it("shows Dismiss button in expanded card", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    renderPage();

    const card = screen.getByText("Alice Smith").closest("div[class*='rounded-xl']")!;
    fireEvent.click(card);

    expect(screen.getByText("Dismiss")).toBeInTheDocument();
  });

  it("calls updateSuggestion with dismissed status when Dismiss is clicked", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    renderPage();

    const card = screen.getByText("Alice Smith").closest("div[class*='rounded-xl']")!;
    fireEvent.click(card);

    fireEvent.click(screen.getByText("Dismiss"));

    expect(mockUpdateSuggestionMutate).toHaveBeenCalledWith({
      id: "s1",
      input: { status: "dismissed" },
    });
  });

  it("opens snooze dropdown and shows snooze options", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    renderPage();

    const card = screen.getByText("Alice Smith").closest("div[class*='rounded-xl']")!;
    fireEvent.click(card);

    fireEvent.click(screen.getByText("Snooze"));

    expect(screen.getByText("2 weeks")).toBeInTheDocument();
    expect(screen.getByText("1 month")).toBeInTheDocument();
    expect(screen.getByText("3 months")).toBeInTheDocument();
  });

  it("calls updateSuggestion with snoozed status when a snooze option is selected", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    renderPage();

    const card = screen.getByText("Alice Smith").closest("div[class*='rounded-xl']")!;
    fireEvent.click(card);

    fireEvent.click(screen.getByText("Snooze"));
    fireEvent.click(screen.getByText("2 weeks"));

    expect(mockUpdateSuggestionMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "s1",
        input: expect.objectContaining({
          status: "snoozed",
          snooze_until: expect.any(String),
        }),
      })
    );
  });

  it("calls generateSuggestions.mutate when Generate button is clicked", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [] },
      isLoading: false,
    });
    renderPage();

    // Click the header Generate button (first one)
    const buttons = screen.getAllByText("Generate new suggestions");
    fireEvent.click(buttons[0]);

    expect(mockGenerateSuggestionsMutate).toHaveBeenCalled();
  });

  it("contact name links to contact detail page", () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    renderPage();

    const link = screen.getByText("Alice Smith").closest("a")!;
    expect(link).toHaveAttribute("href", "/contacts/c1");
  });

  it("sends message via send button in expanded card", async () => {
    mockUseSuggestions.mockReturnValue({
      data: { data: [makeSuggestion()] },
      isLoading: false,
    });
    mockSendMessageMutateAsync.mockResolvedValue({});
    renderPage();

    const card = screen.getByText("Alice Smith").closest("div[class*='rounded-xl']")!;
    fireEvent.click(card);

    fireEvent.click(screen.getByTestId("send-button"));

    await waitFor(() => {
      expect(mockSendMessageMutateAsync).toHaveBeenCalledWith({
        contactId: "c1",
        message: "Hello!",
        channel: "telegram",
        scheduledFor: undefined,
      });
    });
  });
});
