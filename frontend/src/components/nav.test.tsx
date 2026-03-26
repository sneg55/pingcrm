import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { usePathname } from "next/navigation";
import { Nav } from "./nav";

// Mock useAuth
vi.mock("@/hooks/use-auth", () => ({
  useAuth: vi.fn(),
}));

// Mock useUnreadCount
vi.mock("@/hooks/use-notifications", () => ({
  useUnreadCount: vi.fn(),
}));

// Mock useTelegramSyncProgress
vi.mock("@/hooks/use-telegram-sync", () => ({
  useTelegramSyncProgress: () => ({ data: { active: false } }),
}));

// Mock useContacts
vi.mock("@/hooks/use-contacts", () => ({
  useContacts: vi.fn(),
}));

// Mock ThemeToggle (uses useTheme context not available in tests)
vi.mock("@/components/theme-toggle", () => ({
  ThemeToggle: () => <button aria-label="Toggle dark mode" />,
}));

import { useAuth } from "@/hooks/use-auth";
import { useUnreadCount } from "@/hooks/use-notifications";
import { useContacts } from "@/hooks/use-contacts";

const mockedUsePathname = vi.mocked(usePathname);
const mockedUseAuth = vi.mocked(useAuth);
const mockedUseUnreadCount = vi.mocked(useUnreadCount);
const mockedUseContacts = vi.mocked(useContacts);

const defaultUser = {
  id: "user-1",
  full_name: "Alice Smith",
  email: "alice@example.com",
};

function setupMocks({
  pathname = "/dashboard",
  user = defaultUser as typeof defaultUser | null,
  isLoading = false,
  notificationCount = 0,
} = {}) {
  mockedUsePathname.mockReturnValue(pathname);
  mockedUseAuth.mockReturnValue({
    user,
    isLoading,
    logout: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>);
  mockedUseUnreadCount.mockReturnValue({
    data: { data: { count: notificationCount } },
  } as ReturnType<typeof useUnreadCount>);
  mockedUseContacts.mockReturnValue({
    data: { data: [] },
  } as unknown as ReturnType<typeof useContacts>);
}

describe("Nav", () => {
  beforeEach(() => {
    setupMocks();
  });

  it("renders all navigation links", () => {
    render(<Nav />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Suggestions")).toBeInTheDocument();
    expect(screen.getByText("Contacts")).toBeInTheDocument();
    expect(screen.getByText("Orgs")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("active link gets teal color class based on pathname", () => {
    setupMocks({ pathname: "/suggestions" });
    render(<Nav />);
    const suggestionsLink = screen.getByText("Suggestions").closest("a")!;
    expect(suggestionsLink.className).toContain("text-teal-700");
  });

  it("inactive links do not get teal color class", () => {
    setupMocks({ pathname: "/suggestions" });
    render(<Nav />);
    const dashboardLink = screen.getByText("Dashboard").closest("a")!;
    expect(dashboardLink.className).not.toContain("text-teal-700");
  });

  it("contacts dropdown shows children on hover", () => {
    render(<Nav />);
    const contactsLink = screen.getByText("Contacts").closest("div")!;
    fireEvent.mouseEnter(contactsLink);
    expect(screen.getByText("All Contacts")).toBeInTheDocument();
    expect(screen.getByText("Archive")).toBeInTheDocument();
    expect(screen.getByText("Resolve Duplicates")).toBeInTheDocument();
  });

  it("dropdown closes after mouse leave with 150ms delay", () => {
    vi.useFakeTimers();
    render(<Nav />);
    const contactsLink = screen.getByText("Contacts").closest("div")!;
    fireEvent.mouseEnter(contactsLink);
    expect(screen.getByText("All Contacts")).toBeInTheDocument();

    fireEvent.mouseLeave(contactsLink);
    // Before 150ms, dropdown is still visible
    expect(screen.getByText("All Contacts")).toBeInTheDocument();

    // After 150ms, dropdown is gone
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.queryByText("All Contacts")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("NotificationBell renders with badge when count > 0", () => {
    setupMocks({ notificationCount: 5 });
    render(<Nav />);
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("NotificationBell renders without badge when count is 0", () => {
    setupMocks({ notificationCount: 0 });
    render(<Nav />);
    // Badge span should not be rendered
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("shows 99+ when notification count exceeds 99", () => {
    setupMocks({ notificationCount: 150 });
    render(<Nav />);
    expect(screen.getByText("99+")).toBeInTheDocument();
  });

  it("Nav is hidden on auth pages", () => {
    setupMocks({ pathname: "/auth/login" });
    const { container } = render(<Nav />);
    expect(container.firstChild).toBeNull();
  });

  it("Nav is visible on dashboard (no onboarding page)", () => {
    setupMocks({ pathname: "/dashboard" });
    const { container } = render(<Nav />);
    expect(container.firstChild).not.toBeNull();
  });

  it("search button renders with Search contacts text", () => {
    render(<Nav />);
    expect(screen.getByText("Search contacts")).toBeInTheDocument();
  });

  it("user menu shows user name and sign out button", () => {
    render(<Nav />);
    // Click to open user menu
    const userButton = screen.getByText("Alice Smith").closest("button")!;
    fireEvent.click(userButton);
    expect(screen.getByText("Sign out")).toBeInTheDocument();
  });

  it("sign out calls logout function", () => {
    const logout = vi.fn();
    mockedUseAuth.mockReturnValue({
      user: defaultUser,
      isLoading: false,
      logout,
    } as unknown as ReturnType<typeof useAuth>);

    render(<Nav />);
    const userButton = screen.getByText("Alice Smith").closest("button")!;
    fireEvent.click(userButton);
    fireEvent.click(screen.getByText("Sign out"));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("shows Sign in link when user is not authenticated", () => {
    setupMocks({ user: null });
    render(<Nav />);
    expect(screen.getByText("Sign in")).toBeInTheDocument();
    expect(screen.getByText("Sign in").closest("a")).toHaveAttribute(
      "href",
      "/auth/login"
    );
  });
});
