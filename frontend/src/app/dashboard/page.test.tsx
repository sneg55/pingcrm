import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DashboardPage from "./page";

// ---------------------------------------------------------------------------
// Mock hooks
// ---------------------------------------------------------------------------
vi.mock("@/hooks/use-dashboard", () => ({
  useDashboardStats: vi.fn(),
}));

vi.mock("@/hooks/use-suggestions", () => ({
  useUpdateSuggestion: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn() })),
  useSendMessage: vi.fn(() => ({ mutateAsync: vi.fn() })),
}));

vi.mock("@/components/score-badge", () => ({
  ScoreBadge: ({ lastInteractionAt }: { lastInteractionAt: string }) => (
    <span data-testid="score-badge">{lastInteractionAt}</span>
  ),
}));

vi.mock("@/components/message-editor", () => ({
  MessageEditor: () => <div data-testid="message-editor" />,
}));

vi.mock("@/components/animated-number", () => ({
  AnimatedNumber: ({ value, className }: { value: number; className?: string }) => (
    <span className={className}>{value.toLocaleString()}</span>
  ),
}));

import { useDashboardStats } from "@/hooks/use-dashboard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <DashboardPage />
    </QueryClientProvider>
  );
}

const defaultStats = {
  total: 0,
  active: 0,
  strong: 0,
  dormant: 0,
  interactionsThisWeek: 0,
  interactionsLastWeek: 0,
  activeLastWeek: 0,
};

function mockDashboard(overrides: Partial<ReturnType<typeof useDashboardStats>> = {}) {
  (useDashboardStats as ReturnType<typeof vi.fn>).mockReturnValue({
    suggestions: [],
    stats: defaultStats,
    statsReady: true,
    overdueContacts: [],
    recentActivity: [],
    isLoading: false,
    isError: false,
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Loading state -------------------------------------------------------

  it("renders loading skeletons while data is loading", () => {
    mockDashboard({ isLoading: true, stats: { ...defaultStats, total: 10 } });
    renderPage();
    // Pulse skeletons are rendered via animate-pulse divs in Pending Follow-ups
    // and Needs Attention sections. Check that no stat values appear yet.
    const shimmerEls = document.querySelectorAll(".shimmer, .animate-pulse");
    expect(shimmerEls.length).toBeGreaterThan(0);
  });

  // --- Empty state ---------------------------------------------------------

  it("shows empty state with connect message when there are no contacts", () => {
    mockDashboard();
    renderPage();
    expect(screen.getByText("Connect your accounts to get started")).toBeInTheDocument();
  });

  it("shows platform connect buttons in empty state", () => {
    mockDashboard();
    renderPage();
    expect(screen.getByText("Google")).toBeInTheDocument();
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("Twitter/X")).toBeInTheDocument();
    expect(screen.getByText("LinkedIn")).toBeInTheDocument();
  });

  it("shows CSV import link in empty state", () => {
    mockDashboard();
    renderPage();
    expect(screen.getByText("or import a CSV file")).toBeInTheDocument();
  });

  it("platform buttons link to /settings", () => {
    mockDashboard();
    renderPage();
    const links = screen.getAllByRole("link").filter(
      (el) => el.getAttribute("href") === "/settings"
    );
    // 4 platform buttons + CSV link = 5 links to /settings
    expect(links.length).toBeGreaterThanOrEqual(4);
  });

  it("shows CSV import option in empty state pointing to /settings", () => {
    mockDashboard();
    renderPage();
    const link = screen.getByText("or import a CSV file").closest("a");
    expect(link).toHaveAttribute("href", "/settings");
  });

  // --- Stat cards ----------------------------------------------------------

  it("renders stat cards when contacts exist", () => {
    mockDashboard({
      stats: { total: 42, active: 10, strong: 5, dormant: 3, interactionsThisWeek: 7, interactionsLastWeek: 0, activeLastWeek: 0 },
    });
    renderPage();
    expect(screen.getByText("Total contacts")).toBeInTheDocument();
    expect(screen.getByText("Active relationships")).toBeInTheDocument();
    expect(screen.getByText("Interactions this week")).toBeInTheDocument();
  });

  it("displays correct total contacts value in stat card", () => {
    mockDashboard({
      stats: { total: 99, active: 5, strong: 3, dormant: 2, interactionsThisWeek: 4, interactionsLastWeek: 0, activeLastWeek: 0 },
    });
    renderPage();
    expect(screen.getByText("99")).toBeInTheDocument();
  });

  it("displays active + strong relationships count in active relationships card", () => {
    mockDashboard({
      stats: { total: 20, active: 8, strong: 4, dormant: 2, interactionsThisWeek: 3, interactionsLastWeek: 0, activeLastWeek: 0 },
    });
    renderPage();
    // active(8) + strong(4) = 12
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("displays interactions this week count in stat card", () => {
    mockDashboard({
      stats: { total: 10, active: 2, strong: 1, dormant: 0, interactionsThisWeek: 15, interactionsLastWeek: 0, activeLastWeek: 0 },
    });
    renderPage();
    expect(screen.getByText("15")).toBeInTheDocument();
  });

  // --- Pending follow-ups section ------------------------------------------

  it("shows Pending Follow-ups section heading when contacts exist", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
    });
    renderPage();
    expect(screen.getByText("Pending Follow-ups")).toBeInTheDocument();
  });

  it("shows no-suggestions empty state when pending list is empty", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      suggestions: [],
    });
    renderPage();
    expect(screen.getByText(/No pending suggestions/i)).toBeInTheDocument();
  });

  it("shows Generate suggestions link inside empty pending suggestions state", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      suggestions: [],
    });
    renderPage();
    const link = screen.getByRole("link", { name: /Generate suggestions/i });
    expect(link).toHaveAttribute("href", "/suggestions");
  });

  it("renders a suggestion card for each pending suggestion (up to 5)", () => {
    const makeSuggestion = (i: number) => ({
      id: `sug-${i}`,
      contact_id: `c-${i}`,
      contact: {
        id: `c-${i}`,
        full_name: `Person ${i}`,
        given_name: null,
        family_name: null,
        company: null,
        title: null,
        avatar_url: null,
        telegram_username: null,
        twitter_handle: null,
        last_interaction_at: null,
      },
      trigger_type: "time_based",
      suggested_message: `Say hello to Person ${i}`,
      suggested_channel: "email" as const,
      status: "pending" as const,
      scheduled_for: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: null,
    });

    mockDashboard({
      stats: { total: 10, active: 3, strong: 1, dormant: 0, interactionsThisWeek: 2, interactionsLastWeek: 0, activeLastWeek: 0 },
      suggestions: [1, 2, 3].map(makeSuggestion),
    });
    renderPage();
    expect(screen.getByText("Person 1")).toBeInTheDocument();
    expect(screen.getByText("Person 2")).toBeInTheDocument();
    expect(screen.getByText("Person 3")).toBeInTheDocument();
  });

  it("shows 'View all' link in Pending Follow-ups pointing to /suggestions", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
    });
    renderPage();
    const links = screen.getAllByRole("link", { name: /View all/i });
    const suggestionsLink = links.find((l) => l.getAttribute("href") === "/suggestions");
    expect(suggestionsLink).toBeDefined();
  });

  // --- Needs Attention section ---------------------------------------------

  it("shows 'All caught up!' when there are no overdue contacts", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      overdueContacts: [],
    });
    renderPage();
    expect(screen.getByText("All caught up!")).toBeInTheDocument();
  });

  it("renders overdue contact rows with their names", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      overdueContacts: [
        {
          id: "oc-1",
          full_name: "Alice Smith",
          given_name: null,
          family_name: null,
          avatar_url: null,
          priority_level: null,
          last_interaction_at: null,
          days_overdue: 7,
          relationship_score: null,
        },
      ],
    });
    renderPage();
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
  });

  it("renders overdue contact link pointing to correct contact page", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      overdueContacts: [
        {
          id: "oc-42",
          full_name: "Bob Jones",
          given_name: null,
          family_name: null,
          avatar_url: null,
          priority_level: null,
          last_interaction_at: null,
          days_overdue: 3,
          relationship_score: null,
        },
      ],
    });
    renderPage();
    const link = screen.getByRole("link", { name: /Bob Jones/i });
    expect(link).toHaveAttribute("href", "/contacts/oc-42");
  });

  it("shows '7d overdue' label for a contact that is 7 days overdue", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      overdueContacts: [
        {
          id: "oc-1",
          full_name: "Charlie D",
          given_name: null,
          family_name: null,
          avatar_url: null,
          priority_level: null,
          last_interaction_at: null,
          days_overdue: 7,
          relationship_score: null,
        },
      ],
    });
    renderPage();
    expect(screen.getByText("7d overdue")).toBeInTheDocument();
  });

  it("shows 'due today' label for a contact with 0 days overdue", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      overdueContacts: [
        {
          id: "oc-today",
          full_name: "Eve Today",
          given_name: null,
          family_name: null,
          avatar_url: null,
          priority_level: null,
          last_interaction_at: null,
          days_overdue: 0,
          relationship_score: null,
        },
      ],
    });
    renderPage();
    expect(screen.getByText("due today")).toBeInTheDocument();
  });

  // --- Recent Activity section ---------------------------------------------

  it("shows 'No recent activity' when activity list is empty", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      recentActivity: [],
    });
    renderPage();
    expect(screen.getByText("No recent activity")).toBeInTheDocument();
  });

  it("renders activity events with contact name links", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      recentActivity: [
        {
          type: "message",
          contact_name: "Diana Prince",
          contact_id: "c-diana",
          contact_avatar_url: null,
          platform: "email",
          direction: "inbound",
          content_preview: "Hello there",
          timestamp: new Date(Date.now() - 3600000).toISOString(),
        },
      ],
    });
    renderPage();
    expect(screen.getByRole("link", { name: /Diana Prince/i })).toHaveAttribute(
      "href",
      "/contacts/c-diana"
    );
  });

  it("shows contact name and fallback text in activity card", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      recentActivity: [
        {
          type: "message",
          contact_name: "Frank Castle",
          contact_id: "c-frank",
          contact_avatar_url: null,
          platform: "email",
          direction: "inbound",
          content_preview: null,
          timestamp: new Date(Date.now() - 7200000).toISOString(),
        },
      ],
    });
    renderPage();
    expect(screen.getByText("Frank Castle")).toBeInTheDocument();
    expect(screen.getByText("email message received")).toBeInTheDocument();
  });

  // --- Header subtitle message -------------------------------------------

  it("shows 'Your networking overview' subtitle when nothing is pending", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      suggestions: [],
      overdueContacts: [],
    });
    renderPage();
    expect(screen.getByText("Your networking overview")).toBeInTheDocument();
  });

  it("shows pending suggestions count in subtitle when suggestions are pending", () => {
    mockDashboard({
      stats: { total: 5, active: 1, strong: 0, dormant: 0, interactionsThisWeek: 0, interactionsLastWeek: 0, activeLastWeek: 0 },
      suggestions: [
        {
          id: "s1",
          contact_id: "c1",
          contact: {
            id: "c1",
            full_name: "Test User",
            given_name: null,
            family_name: null,
            company: null,
            title: null,
            avatar_url: null,
            telegram_username: null,
            twitter_handle: null,
            last_interaction_at: null,
          },
          trigger_type: "time_based",
          suggested_message: "Hi there",
          suggested_channel: "email" as const,
          status: "pending" as const,
          scheduled_for: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: null,
        },
      ],
    });
    renderPage();
    expect(screen.getByText(/1 pending suggestion/i)).toBeInTheDocument();
  });

  // --- Page heading --------------------------------------------------------

  it("renders Dashboard heading", () => {
    mockDashboard();
    renderPage();
    expect(screen.getByRole("heading", { name: /Dashboard/i })).toBeInTheDocument();
  });
});
