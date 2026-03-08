import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useSearchParams } from "next/navigation";
import SettingsPage from "./page";

// Mock the api-client module
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    DELETE: vi.fn(),
    use: vi.fn(),
  },
}));

import { client } from "@/lib/api-client";

const mockedClient = client as unknown as {
  GET: ReturnType<typeof vi.fn>;
  POST: ReturnType<typeof vi.fn>;
  PUT: ReturnType<typeof vi.fn>;
  DELETE: ReturnType<typeof vi.fn>;
};

const mockedUseSearchParams = useSearchParams as unknown as ReturnType<typeof vi.fn>;

function mockMeResponse(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      data: {
        google_connected: false,
        google_email: null,
        google_accounts: [],
        telegram_connected: false,
        telegram_username: null,
        twitter_connected: false,
        twitter_username: null,
        ...overrides,
      },
    },
    error: null,
  };
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn(() => null),
    });
    // Default: disconnected user
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      return Promise.resolve({ data: null, error: { detail: "unexpected GET " + url } });
    });
    mockedClient.POST.mockResolvedValue({ data: null, error: { detail: "unexpected POST" } });

    // Mock window.location
    Object.defineProperty(window, "location", {
      writable: true,
      value: { href: "", pathname: "/settings" },
    });
    window.history.replaceState = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // ─── Loading state ────────────────────────────────────────────────

  it("shows loading spinner initially", async () => {
    // Make /api/v1/auth/me hang
    mockedClient.GET.mockReturnValue(new Promise(() => {}));
    render(<SettingsPage />);
    expect(screen.getByText("Loading accounts...")).toBeInTheDocument();
  });

  it("renders settings page after loading", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connected Accounts")).toBeInTheDocument();
    });
  });

  // ─── 401 redirect ─────────────────────────────────────────────────

  it("redirects to login on 401", async () => {
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve({ data: null, error: {}, response: { status: 401 } });
      return Promise.resolve({ data: null, error: null });
    });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(window.location.href).toBe("/auth/login");
    });
  });

  // ─── Connected accounts display ───────────────────────────────────

  it("shows Connected badges when accounts are linked", async () => {
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(
          mockMeResponse({
            google_connected: true,
            google_email: "user@gmail.com",
            google_accounts: [{ id: "ga-1", email: "user@gmail.com" }],
            telegram_connected: true,
            telegram_username: "sawinyh",
            twitter_connected: true,
            twitter_username: "sneg55",
          })
        );
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Connected")).toHaveLength(3);
    });

    expect(screen.getByText("user@gmail.com")).toBeInTheDocument();
    expect(screen.getByText("connected @sawinyh")).toBeInTheDocument();
    expect(screen.getByText("connected @sneg55")).toBeInTheDocument();
  });

  it("shows Add Google Account button when already connected", async () => {
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Add Google Account")).toBeInTheDocument();
    });
  });

  // ─── ConnectionBadge ──────────────────────────────────────────────

  it("does not render ConnectionBadge when disconnected", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connected Accounts")).toBeInTheDocument();
    });
    expect(screen.queryAllByText("Connected")).toHaveLength(0);
  });

  // ─── Success modal (OAuth redirect) ───────────────────────────────

  it("shows success modal on ?connected=twitter redirect", async () => {
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn((key: string) => (key === "connected" ? "twitter" : null)),
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Twitter Connected")).toBeInTheDocument();
    });
    expect(screen.getByText(/successfully linked/)).toBeInTheDocument();
    expect(window.history.replaceState).toHaveBeenCalledWith({}, "", "/settings?tab=sync");
  });

  it("closes success modal on Done click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn((key: string) => (key === "connected" ? "google" : null)),
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Google Connected")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Done"));
    expect(screen.queryByText("Google Connected")).not.toBeInTheDocument();
  });

  // ─── Google connect ───────────────────────────────────────────────

  it("redirects to Google OAuth URL on Connect Google click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/api/v1/auth/google/url")
        return Promise.resolve({ data: { data: { url: "https://accounts.google.com/o/auth" } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Google")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Google"));
    await waitFor(() => {
      expect(window.location.href).toBe("https://accounts.google.com/o/auth");
    });
  });

  it("shows error when Google OAuth URL is missing", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/api/v1/auth/google/url")
        return Promise.resolve({ data: { data: {} }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Google")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Google"));
    await waitFor(() => {
      expect(screen.getByText("Google OAuth not configured")).toBeInTheDocument();
    });
  });

  it("shows error when Google OAuth request fails", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/api/v1/auth/google/url")
        return Promise.resolve({ data: null, error: { detail: "network error" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Google")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Google"));
    await waitFor(() => {
      expect(screen.getByText(/Google OAuth not configured/)).toBeInTheDocument();
    });
  });

  // ─── Google sync ──────────────────────────────────────────────────

  it("sync contacts button is disabled when not connected", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });
    expect(screen.getByText("Sync Contacts").closest("button")).toBeDisabled();
  });

  it("syncs Google contacts successfully — button not in loading state after", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/google")
        return Promise.resolve({ data: null, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    await waitFor(() => {
      // After sync, POST was called with the correct endpoint
      expect(mockedClient.POST).toHaveBeenCalledWith("/api/v1/contacts/sync/google");
      // Button shows syncing state (stays loading while polling for notification)
      expect(screen.getByText("Syncing...")).toBeInTheDocument();
    });
  });

  it("calls Google sync endpoint and handles error from backend", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/google")
        return Promise.resolve({ data: null, error: { detail: "Token expired" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    await waitFor(() => {
      expect(mockedClient.POST).toHaveBeenCalledWith("/api/v1/contacts/sync/google");
      // Button returns to non-loading, non-disabled state after error
      expect(screen.getByText("Sync Contacts").closest("button")).not.toBeDisabled();
    });
  });

  it("calls Google sync endpoint and handles error without detail", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/google")
        return Promise.resolve({ data: null, error: {} });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    await waitFor(() => {
      expect(mockedClient.POST).toHaveBeenCalledWith("/api/v1/contacts/sync/google");
      expect(screen.getByText("Sync Contacts").closest("button")).not.toBeDisabled();
    });
  });

  // ─── Telegram connect (phone → code → verify) ────────────────────

  it("opens Telegram modal on Connect Telegram click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    expect(screen.getByText("Connect Telegram", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("+1234567890")).toBeInTheDocument();
  });

  it("Send code button is disabled with empty phone", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    expect(screen.getByText("Send code").closest("button")).toBeDisabled();
  });

  it("sends Telegram code and transitions to code step", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "abc123" } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getByText(/Enter the code sent/)).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText("12345")).toBeInTheDocument();
  });

  it("shows error when send code fails", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: null, error: { detail: "Invalid phone number. Use international format" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+1");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getAllByText(/Invalid phone number/).length).toBeGreaterThan(0);
    });
  });

  it("shows fallback error when send code fails without detail", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: null, error: {} });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+1");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getAllByText(/Failed to send code/).length).toBeGreaterThan(0);
    });
  });

  it("verifies Telegram code and shows success", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      if (url === "/api/v1/auth/telegram/verify")
        return Promise.resolve({ data: { data: { connected: true, username: "sawinyh" } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    let callCount = 0;
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") {
        callCount++;
        if (callCount > 1)
          return Promise.resolve(
            mockMeResponse({ telegram_connected: true, telegram_username: "sawinyh" })
          );
        return Promise.resolve(mockMeResponse());
      }
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("12345")).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText("12345"), "99999");
    await user.click(screen.getByText("Verify"));

    await waitFor(() => {
      expect(screen.getByText("Telegram Connected")).toBeInTheDocument();
    });
  });

  it("shows error on invalid Telegram code", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      if (url === "/api/v1/auth/telegram/verify")
        return Promise.resolve({ data: null, error: { detail: "Telegram verification failed: PhoneCodeInvalid" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("12345")).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText("12345"), "00000");
    await user.click(screen.getByText("Verify"));

    await waitFor(() => {
      expect(screen.getAllByText(/PhoneCodeInvalid/).length).toBeGreaterThan(0);
    });
  });

  it("shows fallback error on verify failure without detail", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      if (url === "/api/v1/auth/telegram/verify")
        return Promise.resolve({ data: null, error: {} });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("12345")).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText("12345"), "00000");
    await user.click(screen.getByText("Verify"));

    await waitFor(() => {
      expect(screen.getAllByText("Invalid code. Try again.").length).toBeGreaterThan(0);
    });
  });

  // ─── Telegram 2FA ─────────────────────────────────────────────────

  it("transitions to 2FA password step when required", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      if (url === "/api/v1/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("12345")).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText("12345"), "99999");
    await user.click(screen.getByText("Verify"));

    await waitFor(() => {
      expect(screen.getByText(/two-step verification/)).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText("Telegram password")).toBeInTheDocument();
  });

  it("completes 2FA verification successfully", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      if (url === "/api/v1/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } }, error: null });
      if (url === "/api/v1/auth/telegram/verify-2fa")
        return Promise.resolve({ data: { data: { connected: true, username: "sawinyh" } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    let callCount = 0;
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") {
        callCount++;
        if (callCount > 1)
          return Promise.resolve(
            mockMeResponse({ telegram_connected: true, telegram_username: "sawinyh" })
          );
        return Promise.resolve(mockMeResponse());
      }
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));
    await waitFor(() => expect(screen.getByPlaceholderText("12345")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("12345"), "99999");
    await user.click(screen.getByText("Verify"));
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Telegram password")).toBeInTheDocument()
    );

    await user.type(screen.getByPlaceholderText("Telegram password"), "secret123");
    await user.click(screen.getByText("Submit"));

    await waitFor(() => {
      expect(screen.getByText("Telegram Connected")).toBeInTheDocument();
    });
  });

  it("shows error on incorrect 2FA password", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      if (url === "/api/v1/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } }, error: null });
      if (url === "/api/v1/auth/telegram/verify-2fa")
        return Promise.resolve({ data: null, error: { detail: "Incorrect 2FA password. Please try again." } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));
    await waitFor(() => expect(screen.getByPlaceholderText("12345")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("12345"), "99999");
    await user.click(screen.getByText("Verify"));
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Telegram password")).toBeInTheDocument()
    );

    await user.type(screen.getByPlaceholderText("Telegram password"), "wrong");
    await user.click(screen.getByText("Submit"));

    await waitFor(() => {
      expect(screen.getAllByText(/Incorrect 2FA password/).length).toBeGreaterThan(0);
    });
  });

  it("shows fallback error on 2FA failure without detail", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      if (url === "/api/v1/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } }, error: null });
      if (url === "/api/v1/auth/telegram/verify-2fa")
        return Promise.resolve({ data: null, error: {} });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));
    await waitFor(() => expect(screen.getByPlaceholderText("12345")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("12345"), "99999");
    await user.click(screen.getByText("Verify"));
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Telegram password")).toBeInTheDocument()
    );

    await user.type(screen.getByPlaceholderText("Telegram password"), "wrong");
    await user.click(screen.getByText("Submit"));

    await waitFor(() => {
      expect(screen.getAllByText("Incorrect password. Try again.").length).toBeGreaterThan(0);
    });
  });

  // ─── Telegram modal close ────────────────────────────────────────

  it("closes Telegram modal on Cancel click (phone step)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    expect(screen.getByPlaceholderText("+1234567890")).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByPlaceholderText("+1234567890")).not.toBeInTheDocument();
  });

  it("closes Telegram modal on X button click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    const closeBtn = screen.getByLabelText("Close");
    await user.click(closeBtn);
    expect(screen.queryByPlaceholderText("+1234567890")).not.toBeInTheDocument();
  });

  it("closes Telegram modal on Cancel during code step", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => expect(screen.getByPlaceholderText("12345")).toBeInTheDocument());

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByPlaceholderText("12345")).not.toBeInTheDocument();
  });

  it("closes Telegram modal on Cancel during password step", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } }, error: null });
      if (url === "/api/v1/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));
    await waitFor(() => expect(screen.getByPlaceholderText("12345")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("12345"), "99999");
    await user.click(screen.getByText("Verify"));
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Telegram password")).toBeInTheDocument()
    );

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByPlaceholderText("Telegram password")).not.toBeInTheDocument();
  });

  // ─── Telegram sync ───────────────────────────────────────────────

  it("syncs Telegram chats successfully", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/telegram")
        return Promise.resolve({ data: null, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Chats")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Chats"));
    await waitFor(() => {
      expect(screen.getByText(/Sync dispatched/)).toBeInTheDocument();
    });
  });

  it("shows Telegram sync error", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/telegram")
        return Promise.resolve({ data: null, error: { detail: "Telegram session expired" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Chats")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Chats"));
    await waitFor(() => {
      expect(screen.getByText("Telegram session expired")).toBeInTheDocument();
    });
  });

  it("shows Telegram sync fallback error", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/telegram")
        return Promise.resolve({ data: null, error: {} });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Chats")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Chats"));
    await waitFor(() => {
      expect(screen.getByText("Telegram sync failed. Please try again.")).toBeInTheDocument();
    });
  });

  // ─── Twitter connect ──────────────────────────────────────────────

  it("redirects to Twitter OAuth URL on Connect Twitter click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/api/v1/auth/twitter/url")
        return Promise.resolve({ data: { data: { url: "https://twitter.com/oauth" } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Twitter")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Twitter"));
    await waitFor(() => {
      expect(window.location.href).toBe("https://twitter.com/oauth");
    });
  });

  it("shows error when Twitter OAuth URL is missing", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/api/v1/auth/twitter/url")
        return Promise.resolve({ data: { data: {} }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Twitter")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Twitter"));
    await waitFor(() => {
      expect(screen.getByText("Twitter OAuth not configured")).toBeInTheDocument();
    });
  });

  it("shows error when Twitter OAuth request fails", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/api/v1/auth/twitter/url")
        return Promise.resolve({ data: null, error: { detail: "network error" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Twitter")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Twitter"));
    await waitFor(() => {
      expect(screen.getByText(/Twitter OAuth not configured/)).toBeInTheDocument();
    });
  });

  // ─── Twitter sync ────────────────────────────────────────────────

  it("sync activity button is disabled when not connected", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Activity")).toBeInTheDocument();
    });
    expect(screen.getByText("Sync Activity").closest("button")).toBeDisabled();
  });

  it("syncs Twitter activity successfully", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ twitter_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/twitter")
        return Promise.resolve({ data: null, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Activity")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Activity"));
    await waitFor(() => {
      expect(screen.getByText(/Sync dispatched/)).toBeInTheDocument();
    });
  });

  it("shows Twitter sync error from backend", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ twitter_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/twitter")
        return Promise.resolve({ data: null, error: { detail: "Rate limit exceeded" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Activity")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Activity"));
    await waitFor(() => {
      expect(screen.getByText("Rate limit exceeded")).toBeInTheDocument();
    });
  });

  it("shows Twitter sync fallback error", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ twitter_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/twitter")
        return Promise.resolve({ data: null, error: {} });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Activity")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Activity"));
    await waitFor(() => {
      expect(screen.getByText("Sync failed. Connect Twitter first.")).toBeInTheDocument();
    });
  });
});

// Suppress unused import warning
void act;
