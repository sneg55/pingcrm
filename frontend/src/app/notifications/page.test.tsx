import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import NotificationsPage from "./page";
import type { AppNotification } from "@/hooks/use-notifications";

// Mock the hooks module
vi.mock("@/hooks/use-notifications", () => ({
  useNotifications: vi.fn(),
  useMarkRead: vi.fn(),
  useMarkAllRead: vi.fn(),
}));

import {
  useNotifications,
  useMarkRead,
  useMarkAllRead,
} from "@/hooks/use-notifications";

const mockedUseNotifications = useNotifications as ReturnType<typeof vi.fn>;
const mockedUseMarkRead = useMarkRead as ReturnType<typeof vi.fn>;
const mockedUseMarkAllRead = useMarkAllRead as ReturnType<typeof vi.fn>;

function makeNotification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "notif-1",
    notification_type: "suggestion",
    title: "Follow up with Alice",
    body: null,
    read: false,
    link: "/contacts/alice",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function setupDefaultMocks() {
  mockedUseMarkRead.mockReturnValue({ mutate: vi.fn(), isPending: false });
  mockedUseMarkAllRead.mockReturnValue({ mutate: vi.fn(), isPending: false });
}

describe("NotificationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // ─── Loading state ──────────────────────────────────────────────────

  it("renders loading skeletons while notifications are loading", () => {
    mockedUseNotifications.mockReturnValue({ data: undefined, isLoading: true });

    render(<NotificationsPage />);

    // Three skeleton divs with animate-pulse class
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBe(3);
    // Page heading should still be visible
    expect(screen.getByText("Notifications")).toBeInTheDocument();
  });

  // ─── Empty state ────────────────────────────────────────────────────

  it("renders empty state when there are no notifications", () => {
    mockedUseNotifications.mockReturnValue({
      data: { data: [], error: null, meta: { total: 0, page: 1, page_size: 20, total_pages: 0 } },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("You're all caught up")).toBeInTheDocument();
    expect(
      screen.getByText(/Notifications will appear here when there's activity/i)
    ).toBeInTheDocument();
    // No unread badge
    expect(screen.queryByText(/unread/)).not.toBeInTheDocument();
  });

  // ─── Notification list renders ──────────────────────────────────────

  it("renders a list of notifications with titles", () => {
    const notifications = [
      makeNotification({ id: "n1", title: "Follow up with Alice", notification_type: "suggestion" }),
      makeNotification({ id: "n2", title: "New message from Bob", notification_type: "event" }),
      makeNotification({ id: "n3", title: "Sync complete", notification_type: "sync", read: true }),
    ];

    mockedUseNotifications.mockReturnValue({
      data: { data: notifications, error: null, meta: { total: 3, page: 1, page_size: 20, total_pages: 1 } },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("Follow up with Alice")).toBeInTheDocument();
    expect(screen.getByText("New message from Bob")).toBeInTheDocument();
    expect(screen.getByText("Sync complete")).toBeInTheDocument();
  });

  it("shows unread count badge when there are unread notifications", () => {
    const notifications = [
      makeNotification({ id: "n1", read: false }),
      makeNotification({ id: "n2", read: false, title: "Second unread" }),
      makeNotification({ id: "n3", read: true, title: "Already read" }),
    ];

    mockedUseNotifications.mockReturnValue({
      data: { data: notifications, error: null, meta: { total: 3, page: 1, page_size: 20, total_pages: 1 } },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("2 unread")).toBeInTheDocument();
    // "Mark all as read" button should appear
    expect(screen.getByText("Mark all as read")).toBeInTheDocument();
  });

  // ─── Mark all as read ───────────────────────────────────────────────

  it("calls markAllRead.mutate when 'Mark all as read' button is clicked", async () => {
    const user = userEvent.setup();
    const markAllMutate = vi.fn();
    mockedUseMarkAllRead.mockReturnValue({ mutate: markAllMutate, isPending: false });

    mockedUseNotifications.mockReturnValue({
      data: {
        data: [makeNotification({ id: "n1", read: false })],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    await user.click(screen.getByText("Mark all as read"));

    expect(markAllMutate).toHaveBeenCalledTimes(1);
  });

  it("disables 'Mark all as read' button while mutation is pending", () => {
    mockedUseMarkAllRead.mockReturnValue({ mutate: vi.fn(), isPending: true });

    mockedUseNotifications.mockReturnValue({
      data: {
        data: [makeNotification({ id: "n1", read: false })],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    const btn = screen.getByText("Mark all as read").closest("button");
    expect(btn).toBeDisabled();
  });

  // ─── Mark single notification as read ──────────────────────────────

  it("calls markRead.mutate with notification id when clicking an unread notification", async () => {
    const user = userEvent.setup();
    const markReadMutate = vi.fn();
    mockedUseMarkRead.mockReturnValue({ mutate: markReadMutate, isPending: false });

    mockedUseNotifications.mockReturnValue({
      data: {
        data: [makeNotification({ id: "notif-42", read: false, title: "Click me" })],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    await user.click(screen.getByText("Click me"));

    expect(markReadMutate).toHaveBeenCalledWith("notif-42");
  });

  it("does not call markRead when clicking an already-read notification", async () => {
    const user = userEvent.setup();
    const markReadMutate = vi.fn();
    mockedUseMarkRead.mockReturnValue({ mutate: markReadMutate, isPending: false });

    mockedUseNotifications.mockReturnValue({
      data: {
        data: [makeNotification({ id: "notif-99", read: true, title: "Already read item" })],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    await user.click(screen.getByText("Already read item"));

    expect(markReadMutate).not.toHaveBeenCalled();
  });

  // ─── Notification types render differently ──────────────────────────

  it("renders suggestion notifications with summary text", () => {
    mockedUseNotifications.mockReturnValue({
      data: {
        data: [
          makeNotification({
            id: "n1",
            notification_type: "suggestion",
            title: "Reach out to Carol",
            body: "It has been 30 days since your last interaction.",
          }),
        ],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("Reach out to Carol")).toBeInTheDocument();
    expect(
      screen.getByText("It has been 30 days since your last interaction.")
    ).toBeInTheDocument();
  });

  it("renders bio_change notifications", () => {
    mockedUseNotifications.mockReturnValue({
      data: {
        data: [
          makeNotification({
            id: "n1",
            notification_type: "bio_change",
            title: "Dave updated their bio",
            body: null,
          }),
        ],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("Dave updated their bio")).toBeInTheDocument();
  });

  it("renders system notifications", () => {
    mockedUseNotifications.mockReturnValue({
      data: {
        data: [
          makeNotification({
            id: "n1",
            notification_type: "system",
            title: "Your account has been set up",
            body: null,
          }),
        ],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("Your account has been set up")).toBeInTheDocument();
  });

  // ─── Filter tabs ────────────────────────────────────────────────────

  it("renders all filter tabs", () => {
    mockedUseNotifications.mockReturnValue({
      data: { data: [], error: null, meta: { total: 0, page: 1, page_size: 20, total_pages: 0 } },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("All")).toBeInTheDocument();
    expect(screen.getByText("Unread")).toBeInTheDocument();
    expect(screen.getByText("Suggestions")).toBeInTheDocument();
    expect(screen.getByText("Events")).toBeInTheDocument();
    expect(screen.getByText("System")).toBeInTheDocument();
  });

  it("filters to unread-only notifications when 'Unread' tab is clicked", async () => {
    const user = userEvent.setup();
    const notifications = [
      makeNotification({ id: "n1", read: false, title: "Unread notification" }),
      makeNotification({ id: "n2", read: true, title: "Read notification" }),
    ];

    mockedUseNotifications.mockReturnValue({
      data: { data: notifications, error: null, meta: { total: 2, page: 1, page_size: 20, total_pages: 1 } },
      isLoading: false,
    });

    render(<NotificationsPage />);

    // Both visible initially on "All"
    expect(screen.getByText("Unread notification")).toBeInTheDocument();
    expect(screen.getByText("Read notification")).toBeInTheDocument();

    await user.click(screen.getByText("Unread"));

    expect(screen.getByText("Unread notification")).toBeInTheDocument();
    expect(screen.queryByText("Read notification")).not.toBeInTheDocument();
  });

  it("shows empty state when active filter returns no results", async () => {
    const user = userEvent.setup();
    const notifications = [
      makeNotification({ id: "n1", notification_type: "suggestion", title: "A suggestion" }),
    ];

    mockedUseNotifications.mockReturnValue({
      data: { data: notifications, error: null, meta: { total: 1, page: 1, page_size: 20, total_pages: 1 } },
      isLoading: false,
    });

    render(<NotificationsPage />);

    // Switch to "System" filter — no system notifications present
    await user.click(screen.getByText("System"));

    expect(screen.getByText("You're all caught up")).toBeInTheDocument();
  });

  // ─── Expandable body ────────────────────────────────────────────────

  it("expands notification details when body has two-paragraph content", async () => {
    const user = userEvent.setup();
    mockedUseNotifications.mockReturnValue({
      data: {
        data: [
          makeNotification({
            id: "n1",
            title: "Summary only title",
            body: "Short summary\n\nExtra detail here",
            read: true,
          }),
        ],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    // Details not yet visible
    expect(screen.queryByText("Extra detail here")).not.toBeInTheDocument();

    await user.click(screen.getByText("Summary only title"));

    await waitFor(() => {
      expect(screen.getByText("Extra detail here")).toBeInTheDocument();
    });
  });

  // ─── Date grouping ──────────────────────────────────────────────────

  it("groups notifications under 'Today' for today's items", () => {
    mockedUseNotifications.mockReturnValue({
      data: {
        data: [makeNotification({ id: "n1", created_at: new Date().toISOString() })],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("Today")).toBeInTheDocument();
  });

  it("groups old notifications under 'Older'", () => {
    const oldDate = new Date();
    oldDate.setDate(oldDate.getDate() - 30);

    mockedUseNotifications.mockReturnValue({
      data: {
        data: [makeNotification({ id: "n1", created_at: oldDate.toISOString() })],
        error: null,
        meta: { total: 1, page: 1, page_size: 20, total_pages: 1 },
      },
      isLoading: false,
    });

    render(<NotificationsPage />);

    expect(screen.getByText("Older")).toBeInTheDocument();
  });
});
