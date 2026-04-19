import { render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OrganizationDetailPage from "./page";

const mockGet = vi.fn();

vi.mock("@/lib/api-client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGet(...args),
    POST: vi.fn(),
    PUT: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  },
}));

vi.mock("date-fns", () => ({
  formatDistanceToNow: () => "2 days ago",
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "org-1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

function makeContact(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    full_name: "Active Alice",
    given_name: "Alice",
    family_name: null,
    title: null,
    avatar_url: null,
    relationship_score: 5,
    priority_level: "medium",
    last_interaction_at: "2025-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeOrgResponse(contacts: ReturnType<typeof makeContact>[]) {
  return {
    data: {
      data: {
        id: "org-1",
        name: "MixedCo",
        domain: null,
        logo_url: null,
        industry: null,
        location: null,
        website: null,
        linkedin_url: null,
        twitter_handle: null,
        notes: null,
        contact_count: contacts.filter((c) => c.priority_level !== "archived").length,
        avg_relationship_score: 4,
        total_interactions: 0,
        last_interaction_at: null,
        contacts,
      },
    },
    error: null,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("OrganizationDetailPage — archived contacts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders archived contact with chip, after active contact, greyed out", async () => {
    const active = makeContact({ id: "c-active", full_name: "Active Alice", relationship_score: 5 });
    const archived = makeContact({
      id: "c-archived",
      full_name: "Archived Arthur",
      priority_level: "archived",
      relationship_score: 9, // higher than active; must still come last
    });
    mockGet.mockResolvedValue(makeOrgResponse([active, archived]));

    render(<OrganizationDetailPage />, { wrapper });

    const activeRow = await screen.findByText("Active Alice");
    const archivedRow = await screen.findByText("Archived Arthur");

    // DOM order: active precedes archived
    // eslint-disable-next-line no-bitwise
    const relation = activeRow.compareDocumentPosition(archivedRow);
    expect(relation & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Archived row has the chip; active row does not
    const archivedTr = archivedRow.closest("tr")!;
    expect(within(archivedTr).getByText("Archived")).toBeInTheDocument();
    const activeTr = activeRow.closest("tr")!;
    expect(within(activeTr).queryByText("Archived")).toBeNull();

    // Archived name link has opacity-60
    const archivedLink = within(archivedTr).getByRole("link", { name: /Archived Arthur/ });
    expect(archivedLink.className).toMatch(/opacity-60/);
    const activeLink = within(activeTr).getByRole("link", { name: /Active Alice/ });
    expect(activeLink.className).not.toMatch(/opacity-60/);
  });
});
