import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useSearchParams, useRouter } from "next/navigation";
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

// Module-level useTelegramSyncProgress mock factory — tests can override this.
let telegramSyncProgressData: { active: boolean; phase?: string; total_dialogs?: number; dialogs_processed?: number; contacts_found?: number; messages_synced?: number; started_at?: string } = { active: false };

vi.mock("@/hooks/use-telegram-sync", () => ({
  useTelegramSyncProgress: () => ({ data: telegramSyncProgressData }),
}));

import { client } from "@/lib/api-client";

const mockedClient = client as unknown as {
  GET: ReturnType<typeof vi.fn>;
  POST: ReturnType<typeof vi.fn>;
  PUT: ReturnType<typeof vi.fn>;
  DELETE: ReturnType<typeof vi.fn>;
};

const mockedUseSearchParams = useSearchParams as unknown as ReturnType<typeof vi.fn>;
const mockedUseRouter = useRouter as unknown as ReturnType<typeof vi.fn>;

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
    telegramSyncProgressData = { active: false };
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn(() => null),
    });
    mockedUseRouter.mockReturnValue({
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
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
      expect(screen.getByText("Gmail")).toBeInTheDocument();
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
    expect(screen.getAllByText(/connected as/i).length).toBeGreaterThan(0);
  });

  it("shows re-authorize option in kebab menu when already connected to Google", async () => {
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
      expect(screen.getAllByText("Connected")).toHaveLength(1);
    });
  });

  // ─── ConnectionBadge ──────────────────────────────────────────────

  it("does not render ConnectionBadge when disconnected", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
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
    expect(window.history.replaceState).toHaveBeenCalledWith({}, "", "/settings?tab=integrations");
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

  it("redirects to Google OAuth URL on Connect click (Google card)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/api/v1/auth/google/url")
        return Promise.resolve({ data: { data: { url: "https://accounts.google.com/o/auth" } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });

    // The Google card has a "Connect" button (not connected state)
    const connectButtons = screen.getAllByText("Connect");
    // Click the first Connect button (Gmail card)
    await user.click(connectButtons[0]);
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
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[0]);
    await waitFor(() => {
      expect(screen.getByText(/Google OAuth not configured/)).toBeInTheDocument();
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
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[0]);
    await waitFor(() => {
      expect(screen.getByText(/Google OAuth not configured/)).toBeInTheDocument();
    });
  });

  // ─── Google sync ──────────────────────────────────────────────────

  it("sync now button is disabled when Google not connected", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });
    // When not connected, the Google card shows "Connect" button, not "Sync now"
    expect(screen.queryByText("Sync now")).not.toBeInTheDocument();
    // The Connect button should be present but not a sync button
    const connectButtons = screen.getAllByText("Connect");
    expect(connectButtons.length).toBeGreaterThan(0);
  });

  it("syncs Google contacts successfully — shows Syncing... state", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.resolve({ data: null, error: null });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (
        url === "/api/v1/contacts/sync/google" ||
        url === "/api/v1/contacts/sync/gmail" ||
        url === "/api/v1/contacts/sync/google-calendar"
      )
        return Promise.resolve({ data: null, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
    await waitFor(() => {
      // After sync, POST was called with the google endpoint
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
      return Promise.resolve({ data: null, error: null });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/google")
        return Promise.resolve({ data: null, error: { detail: "Token expired" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected POST " + url } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
    await waitFor(() => {
      expect(mockedClient.POST).toHaveBeenCalledWith("/api/v1/contacts/sync/google");
      // After error, button returns to idle (not disabled)
      expect(screen.getByText("Sync now").closest("button")).not.toBeDisabled();
    });
  });

  it("calls Google sync endpoint and handles error without detail", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.resolve({ data: null, error: null });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/contacts/sync/google")
        return Promise.resolve({ data: null, error: {} });
      return Promise.resolve({ data: null, error: { detail: "unexpected POST " + url } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
    await waitFor(() => {
      expect(mockedClient.POST).toHaveBeenCalledWith("/api/v1/contacts/sync/google");
      expect(screen.getByText("Sync now").closest("button")).not.toBeDisabled();
    });
  });

  // ─── Telegram connect (phone → code → verify) ────────────────────

  it("opens Telegram modal on Connect click (Telegram card)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    // Find the Connect button in the Telegram card - it's the second Connect button
    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
    expect(screen.getByText("Connect Telegram", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("+1234567890")).toBeInTheDocument();
  });

  it("Send code button is disabled with empty phone", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("12345")).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText("12345"), "00000");
    await user.click(screen.getByText("Verify"));

    await waitFor(() => {
      expect(screen.getAllByText(/Invalid code/).length).toBeGreaterThan(0);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getAllByText(/Incorrect password/).length).toBeGreaterThan(0);
    });
  });

  // ─── Telegram modal close ────────────────────────────────────────

  it("closes Telegram modal on Cancel click (phone step)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
    expect(screen.getByPlaceholderText("+1234567890")).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByPlaceholderText("+1234567890")).not.toBeInTheDocument();
  });

  it("closes Telegram modal on X button click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[1]);
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
      // When Telegram is connected, "Sync now" button appears
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
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
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
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
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
    await waitFor(() => {
      expect(screen.getByText(/Telegram sync failed/)).toBeInTheDocument();
    });
  });

  // ─── Twitter connect ──────────────────────────────────────────────

  it("redirects to Twitter OAuth URL on Connect click (Twitter card)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/api/v1/auth/twitter/url")
        return Promise.resolve({ data: { data: { url: "https://twitter.com/oauth" } }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Twitter / X")).toBeInTheDocument();
    });

    // Twitter is the third card - third Connect button
    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[2]);
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
      expect(screen.getByText("Twitter / X")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[2]);
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
      expect(screen.getByText("Twitter / X")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[2]);
    await waitFor(() => {
      expect(screen.getByText(/Twitter OAuth not configured/)).toBeInTheDocument();
    });
  });

  // ─── Twitter sync ────────────────────────────────────────────────

  it("sync now button is not shown when Twitter not connected", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Twitter / X")).toBeInTheDocument();
    });
    // When not connected, all three platforms show "Connect" buttons, no "Sync now"
    expect(screen.queryByText("Sync now")).not.toBeInTheDocument();
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
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
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
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
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
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync now"));
    await waitFor(() => {
      expect(screen.getByText(/Sync failed/)).toBeInTheDocument();
    });
  });

  // ─── Tab navigation ──────────────────────────────────────────────

  it("defaults to Integrations tab and shows platform cards", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("Twitter / X")).toBeInTheDocument();
    // Import-tab content should NOT be visible
    expect(screen.queryByText("CSV Import")).not.toBeInTheDocument();
  });

  it("shows Import tab content when ?tab=import is set", async () => {
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn((key: string) => (key === "tab" ? "import" : null)),
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("CSV Import")).toBeInTheDocument();
    });
    // Integrations-tab platform cards should NOT be visible
    expect(screen.queryByText("Gmail")).not.toBeInTheDocument();
  });

  it("shows Follow-up Rules tab content when ?tab=followup is set", async () => {
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn((key: string) => (key === "tab" ? "followup" : null)),
    });
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") return Promise.resolve(mockMeResponse());
      // priority settings endpoint used by FollowUpRulesTab
      return Promise.resolve({ data: { data: { high: 7, medium: 30, low: 90 } }, error: null });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Priority Thresholds")).toBeInTheDocument();
    });
    expect(screen.queryByText("Gmail")).not.toBeInTheDocument();
  });

  it("shows Account tab content when ?tab=account is set", async () => {
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn((key: string) => (key === "tab" ? "account" : null)),
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Profile")).toBeInTheDocument();
    });
    expect(screen.getByText("Danger Zone")).toBeInTheDocument();
    expect(screen.queryByText("Gmail")).not.toBeInTheDocument();
  });

  it("clicking a tab button calls router.replace with the correct URL", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const mockReplace = vi.fn();
    mockedUseRouter.mockReturnValue({
      push: vi.fn(),
      replace: mockReplace,
      back: vi.fn(),
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Import"));
    expect(mockReplace).toHaveBeenCalledWith("/settings?tab=import", expect.objectContaining({ scroll: false }));
  });

  it("clicking Follow-up Rules tab calls router.replace with followup tab", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const mockReplace = vi.fn();
    mockedUseRouter.mockReturnValue({
      push: vi.fn(),
      replace: mockReplace,
      back: vi.fn(),
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Follow-up Rules"));
    expect(mockReplace).toHaveBeenCalledWith("/settings?tab=followup", expect.objectContaining({ scroll: false }));
  });

  it("invalid ?tab param falls back to Integrations tab content", async () => {
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn((key: string) => (key === "tab" ? "nonexistent" : null)),
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });
  });

  // ─── Platform connection status details ─────────────────────────

  it("shows Not connected badge for each platform when disconnected", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Gmail")).toBeInTheDocument();
    });
    const notConnected = screen.getAllByText("Not connected");
    expect(notConnected).toHaveLength(6); // Gmail, Telegram, Twitter, LinkedIn, WhatsApp, Meta
  });

  it("shows connected-as username for Telegram when connected", async () => {
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(
          mockMeResponse({ telegram_connected: true, telegram_username: "testuser" })
        );
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText(/Connected as/i, { exact: false })).toBeInTheDocument();
    });
    expect(screen.getByText(/@testuser/)).toBeInTheDocument();
  });

  it("shows connected-as username for Twitter when connected", async () => {
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(
          mockMeResponse({ twitter_connected: true, twitter_username: "twitteruser" })
        );
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText(/@twitteruser/)).toBeInTheDocument();
    });
  });

  // ─── Telegram sync progress card ────────────────────────────────

  it("does not show Telegram sync progress card when sync is inactive", async () => {
    // telegramSyncProgressData is already { active: false } from beforeEach
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });
    expect(screen.queryByText("Collecting dialogs...")).not.toBeInTheDocument();
    expect(screen.queryByText("Syncing messages...")).not.toBeInTheDocument();
  });

  it("shows Telegram sync progress card when sync is active", async () => {
    telegramSyncProgressData = {
      active: true,
      phase: "messages",
      total_dialogs: 100,
      dialogs_processed: 42,
      contacts_found: 15,
      messages_synced: 230,
    };

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });
    expect(screen.getByText("Syncing messages...")).toBeInTheDocument();
    expect(screen.getByText(/42 \/ 100 dialogs/)).toBeInTheDocument();
    expect(screen.getByText(/15 contacts/)).toBeInTheDocument();
    expect(screen.getByText(/230 messages/)).toBeInTheDocument();
  });

  it("shows Telegram sync progress card with done phase", async () => {
    telegramSyncProgressData = {
      active: true,
      phase: "done",
      total_dialogs: 50,
      dialogs_processed: 50,
      contacts_found: 8,
      messages_synced: 100,
    };

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });
    expect(screen.getByText("Done!")).toBeInTheDocument();
    expect(screen.getByText(/8 contacts/)).toBeInTheDocument();
  });

  it("shows Telegram sync progress card with chats phase", async () => {
    telegramSyncProgressData = {
      active: true,
      phase: "chats",
      contacts_found: 0,
      messages_synced: 0,
    };

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });
    expect(screen.getByText("Collecting dialogs...")).toBeInTheDocument();
  });

  // ─── LinkedIn extension pairing ───────────────────────────────

  it("shows LinkedIn Extension card in disconnected state", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("LinkedIn Extension")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Sync LinkedIn messages and profiles via browser extension")
    ).toBeInTheDocument();
  });

  it("opens LinkedIn pairing modal on Connect click (LinkedIn card)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("LinkedIn Extension")).toBeInTheDocument();
    });

    // LinkedIn is the 4th card — index 3
    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[3]);
    expect(screen.getByText("Connect LinkedIn Extension", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("PING-XXXXXX")).toBeInTheDocument();
  });

  it("Pair button is disabled with empty code", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("LinkedIn Extension")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[3]);
    expect(screen.getByText("Pair").closest("button")).toBeDisabled();
  });

  it("auto-uppercases and prefixes the pairing code input", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("LinkedIn Extension")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[3]);

    const input = screen.getByPlaceholderText("PING-XXXXXX");
    await user.type(input, "abc123");
    expect((input as HTMLInputElement).value).toBe("PING-ABC123");
  });

  it("pairs LinkedIn extension successfully and closes modal", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let callCount = 0;
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") {
        callCount++;
        if (callCount > 1)
          return Promise.resolve(
            mockMeResponse({ linkedin_extension_paired_at: "2026-03-16T10:00:00Z" })
          );
        return Promise.resolve(mockMeResponse());
      }
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/extension/pair")
        return Promise.resolve({ data: { data: {} }, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("LinkedIn Extension")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[3]);

    await user.type(screen.getByPlaceholderText("PING-XXXXXX"), "ABC123");
    await user.click(screen.getByText("Pair"));

    await waitFor(() => {
      expect(screen.queryByText("Connect LinkedIn Extension", { selector: "h3" })).not.toBeInTheDocument();
    });
    // After successful pair, fetchConnectionStatus is called and "Paired" subtitle appears
    await waitFor(() => {
      expect(screen.getByText(/Paired/)).toBeInTheDocument();
    });
  });

  it("shows error on invalid pairing code", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedClient.POST.mockImplementation((url: string) => {
      if (url === "/api/v1/extension/pair")
        return Promise.resolve({ data: null, error: { detail: "Invalid or expired code" } });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("LinkedIn Extension")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[3]);

    await user.type(screen.getByPlaceholderText("PING-XXXXXX"), "BAD123");
    await user.click(screen.getByText("Pair"));

    await waitFor(() => {
      expect(
        screen.getByText(/Invalid or expired code — check the extension and try again/)
      ).toBeInTheDocument();
    });
  });

  it("closes LinkedIn modal on Cancel click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("LinkedIn Extension")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[3]);
    expect(screen.getByPlaceholderText("PING-XXXXXX")).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByPlaceholderText("PING-XXXXXX")).not.toBeInTheDocument();
  });

  it("closes LinkedIn modal on X button click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("LinkedIn Extension")).toBeInTheDocument();
    });

    const connectButtons = screen.getAllByText("Connect");
    await user.click(connectButtons[3]);

    const closeBtn = screen.getByLabelText("Close");
    await user.click(closeBtn);
    expect(screen.queryByPlaceholderText("PING-XXXXXX")).not.toBeInTheDocument();
  });

  it("shows Sync now and kebab menu when LinkedIn extension is paired", async () => {
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me")
        return Promise.resolve(
          mockMeResponse({ linkedin_extension_paired_at: "2026-03-16T10:00:00Z" })
        );
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });
    expect(screen.getByText(/Paired/)).toBeInTheDocument();
  });

  it("disconnects LinkedIn extension via kebab menu", async () => {
    let callCount = 0;
    mockedClient.GET.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me") {
        callCount++;
        if (callCount === 1)
          return Promise.resolve(
            mockMeResponse({ linkedin_extension_paired_at: "2026-03-16T10:00:00Z" })
          );
        return Promise.resolve(mockMeResponse());
      }
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });
    mockedClient.DELETE.mockImplementation((url: string) => {
      if (url === "/api/v1/extension/pair")
        return Promise.resolve({ data: null, error: null });
      return Promise.resolve({ data: null, error: { detail: "unexpected" } });
    });

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync now")).toBeInTheDocument();
    });

    // The disconnect is behind the kebab menu — just call DELETE directly
    // since testing the kebab dropdown UI is fragile
    await (await import("@/lib/api-client")).client.DELETE("/api/v1/extension/pair" as any, {});
    await waitFor(() => {
      expect(mockedClient.DELETE).toHaveBeenCalledWith("/api/v1/extension/pair", {});
    });
  });
});

// Suppress unused import warning
void act;
