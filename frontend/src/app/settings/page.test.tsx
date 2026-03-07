import { render, screen, waitFor, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useSearchParams } from "next/navigation";
import SettingsPage from "./page";

// Mock the api module
vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "@/lib/api";

const mockedApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
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
  };
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockedUseSearchParams.mockReturnValue({
      get: vi.fn(() => null),
    });
    // Default: disconnected user
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") return Promise.resolve(mockMeResponse());
      return Promise.reject(new Error("unexpected GET " + url));
    });
    mockedApi.post.mockRejectedValue(new Error("unexpected POST"));

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
    // Make /auth/me hang
    mockedApi.get.mockReturnValue(new Promise(() => {}));
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
    mockedApi.get.mockRejectedValue({ response: { status: 401 } });
    render(<SettingsPage />);
    await waitFor(() => {
      expect(window.location.href).toBe("/auth/login");
    });
  });

  // ─── Connected accounts display ───────────────────────────────────

  it("shows Connected badges when accounts are linked", async () => {
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
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
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.reject(new Error("unexpected"));
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
    expect(window.history.replaceState).toHaveBeenCalledWith({}, "", "/settings");
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/auth/google/url")
        return Promise.resolve({ data: { data: { url: "https://accounts.google.com/o/auth" } } });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/auth/google/url") return Promise.resolve({ data: { data: {} } });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/auth/google/url") return Promise.reject(new Error("network error"));
      return Promise.reject(new Error("unexpected"));
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

  it("syncs Google contacts successfully", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/google")
        return Promise.resolve({
          data: { data: { created: 5, updated: 2, errors: [] } },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    await waitFor(() => {
      // Google sync uses created/updated, not new_interactions
      expect(screen.getByText(/\+5 new contact/)).toBeInTheDocument();
      expect(screen.getByText("2 updated")).toBeInTheDocument();
    });
  });

  it("shows Google sync error from backend", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/google")
        return Promise.reject({
          response: { data: { detail: "Token expired" } },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    // Error message is shown in SyncResultPanel via details.message
    await waitFor(() => {
      expect(screen.getByText("Token expired")).toBeInTheDocument();
    });
  });

  it("shows fallback message on Google sync error without detail", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/google")
        return Promise.reject({ response: {} });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    await waitFor(() => {
      expect(screen.getByText("Sync failed. Connect Google account first.")).toBeInTheDocument();
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "abc123" } } });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.reject({
          response: { data: { detail: "Invalid phone number. Use international format" } },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+1");
    await user.click(screen.getByText("Send code"));

    // Error appears in both modal and card; just check at least one exists
    await waitFor(() => {
      expect(screen.getAllByText(/Invalid phone number/).length).toBeGreaterThan(0);
    });
  });

  it("shows fallback error when send code fails without detail", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.reject({ response: {} });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { connected: true, username: "sawinyh" } } });
      return Promise.reject(new Error("unexpected"));
    });
    // After verify, fetchConnectionStatus will be called again
    let callCount = 0;
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") {
        callCount++;
        if (callCount > 1)
          return Promise.resolve(
            mockMeResponse({ telegram_connected: true, telegram_username: "sawinyh" })
          );
        return Promise.resolve(mockMeResponse());
      }
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    // Open modal → enter phone → send code
    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("12345")).toBeInTheDocument();
    });

    // Enter code → verify
    await user.type(screen.getByPlaceholderText("12345"), "99999");
    await user.click(screen.getByText("Verify"));

    await waitFor(() => {
      expect(screen.getByText("Telegram Connected")).toBeInTheDocument();
    });
  });

  it("shows error on invalid Telegram code", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.reject({
          response: { data: { detail: "Telegram verification failed: PhoneCodeInvalid" } },
        });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.reject({ response: {} });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } } });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } } });
      if (url === "/auth/telegram/verify-2fa")
        return Promise.resolve({ data: { data: { connected: true, username: "sawinyh" } } });
      return Promise.reject(new Error("unexpected"));
    });
    let callCount = 0;
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") {
        callCount++;
        if (callCount > 1)
          return Promise.resolve(
            mockMeResponse({ telegram_connected: true, telegram_username: "sawinyh" })
          );
        return Promise.resolve(mockMeResponse());
      }
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    // phone → code → 2fa → done
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } } });
      if (url === "/auth/telegram/verify-2fa")
        return Promise.reject({
          response: { data: { detail: "Incorrect 2FA password. Please try again." } },
        });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } } });
      if (url === "/auth/telegram/verify-2fa")
        return Promise.reject({ response: {} });
      return Promise.reject(new Error("unexpected"));
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
    // The X button contains an icon
    const closeBtn = screen.getByTestId("icon-X").closest("button")!;
    await user.click(closeBtn);
    expect(screen.queryByPlaceholderText("+1234567890")).not.toBeInTheDocument();
  });

  it("closes Telegram modal on Cancel during code step", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } } });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/telegram")
        return Promise.resolve({
          data: { data: { new_interactions: 42, new_contacts: 3 } },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Chats")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Chats"));
    await waitFor(() => {
      expect(screen.getByText(/42 new interactions/)).toBeInTheDocument();
      expect(screen.getByText(/\+3 new contacts/)).toBeInTheDocument();
    });
  });

  it("shows Telegram sync error", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/telegram")
        return Promise.reject({
          response: { data: { detail: "Telegram session expired" } },
        });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/telegram")
        return Promise.reject({ response: {} });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Chats")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Chats"));
    await waitFor(() => {
      expect(screen.getByText("Sync failed. Connect Telegram first.")).toBeInTheDocument();
    });
  });

  // ─── Twitter connect ──────────────────────────────────────────────

  it("redirects to Twitter OAuth URL on Connect Twitter click", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/auth/twitter/url")
        return Promise.resolve({ data: { data: { url: "https://twitter.com/oauth" } } });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/auth/twitter/url") return Promise.resolve({ data: { data: {} } });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") return Promise.resolve(mockMeResponse());
      if (url === "/auth/twitter/url") return Promise.reject(new Error("network error"));
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ twitter_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/twitter")
        return Promise.resolve({
          data: { data: { dms: 10, mentions: 5, new_contacts: 2 } },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Activity")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Activity"));
    await waitFor(() => {
      expect(screen.getByText(/15 new interactions/)).toBeInTheDocument();
      expect(screen.getByText(/\+2 new contacts/)).toBeInTheDocument();
    });
  });

  it("shows Twitter sync error from backend", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ twitter_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/twitter")
        return Promise.reject({
          response: { data: { detail: "Rate limit exceeded" } },
        });
      return Promise.reject(new Error("unexpected"));
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
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ twitter_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/twitter")
        return Promise.reject({ response: {} });
      return Promise.reject(new Error("unexpected"));
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

  // ─── SyncResultPanel ─────────────────────────────────────────────

  it("shows sync errors in result panel", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/google")
        return Promise.resolve({
          data: {
            data: {
              created: 1,
              updated: 0,
              errors: ["John Doe: duplicate email", "Jane: invalid format"],
            },
          },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    await waitFor(() => {
      expect(screen.getByText("2 errors")).toBeInTheDocument();
      expect(screen.getByText("John Doe: duplicate email")).toBeInTheDocument();
      expect(screen.getByText("Jane: invalid format")).toBeInTheDocument();
    });
  });

  it("shows updated count in result panel", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/google")
        return Promise.resolve({
          data: { data: { created: 0, updated: 7, errors: [] } },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    await waitFor(() => {
      expect(screen.getByText("7 updated")).toBeInTheDocument();
    });
  });

  // ─── ElapsedTimer ─────────────────────────────────────────────────

  it("shows elapsed timer during sync", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let resolveSync: (value: unknown) => void;
    const syncPromise = new Promise((resolve) => {
      resolveSync = resolve;
    });

    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/telegram") return syncPromise;
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Chats")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Chats"));

    // Timer should appear showing 0s
    await waitFor(() => {
      expect(screen.getByText("0s")).toBeInTheDocument();
    });

    // Advance timer by 2 seconds
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(screen.getByText("2s")).toBeInTheDocument();
    });

    // Resolve the sync
    await act(async () => {
      resolveSync!({
        data: { data: { new_interactions: 1, new_contacts: 0 } },
      });
    });

    // Sync should complete and show results
    await waitFor(() => {
      expect(screen.getByText("1 new interaction")).toBeInTheDocument();
    });
  });

  // ─── Page structure / static content ──────────────────────────────

  it("renders all three platform cards", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Google (Gmail + Contacts + Calendar)")).toBeInTheDocument();
      expect(screen.getByText("Telegram")).toBeInTheDocument();
      expect(screen.getByText("Twitter / X")).toBeInTheDocument();
    });
  });

  it("renders card descriptions", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText(/Import contacts, sync email interactions, and pull calendar meetings/)).toBeInTheDocument();
      expect(screen.getByText(/Sync chat history/)).toBeInTheDocument();
      expect(screen.getByText(/Sync DMs, mentions/)).toBeInTheDocument();
    });
  });

  it("renders page heading and subheading", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Settings")).toBeInTheDocument();
      expect(screen.getByText(/Manage connected accounts/)).toBeInTheDocument();
    });
  });

  // ─── Non-error /auth/me failure (e.g. network) ───────────────────

  it("handles non-401 /auth/me error gracefully", async () => {
    mockedApi.get.mockRejectedValue({ response: { status: 500 } });
    render(<SettingsPage />);
    // Should still render the page (not redirect)
    await waitFor(() => {
      expect(screen.getByText("Connected Accounts")).toBeInTheDocument();
    });
  });

  it("handles /auth/me error without response", async () => {
    mockedApi.get.mockRejectedValue(new Error("Network Error"));
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connected Accounts")).toBeInTheDocument();
    });
  });

  // ─── Verify button disabled state ────────────────────────────────

  it("Verify button is disabled with empty code", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Connect Telegram")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));

    await waitFor(() => expect(screen.getByPlaceholderText("12345")).toBeInTheDocument());

    expect(screen.getByText("Verify").closest("button")).toBeDisabled();
  });

  it("Submit button is disabled with empty password", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { requires_2fa: true } } });
      return Promise.reject(new Error("unexpected"));
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

    expect(screen.getByText("Submit").closest("button")).toBeDisabled();
  });

  // ─── Google sync with 1 error (singular) ─────────────────────────

  it("shows singular error count", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/google")
        return Promise.resolve({
          data: { data: { created: 0, updated: 0, errors: ["Row 1: bad data"] } },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Contacts")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Contacts"));
    await waitFor(() => {
      expect(screen.getByText("1 error")).toBeInTheDocument();
    });
  });

  // ─── Singular interaction ─────────────────────────────────────────

  it("shows singular interaction text for 1 new interaction", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/telegram")
        return Promise.resolve({
          data: { data: { new_interactions: 1, new_contacts: 1 } },
        });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("Sync Chats")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Sync Chats"));
    await waitFor(() => {
      expect(screen.getByText("1 new interaction")).toBeInTheDocument();
      expect(screen.getByText("+1 new contact")).toBeInTheDocument();
    });
  });

  // ─── Sync with missing/null data fields (branch coverage) ─────────

  it("handles Google sync with null data fields", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ google_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/google")
        return Promise.resolve({ data: { data: null } });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByText("Sync Contacts")).toBeInTheDocument());
    await user.click(screen.getByText("Sync Contacts"));
    // With all 0 values and no errors, the result panel still shows (green bg)
    // but no stats render since created=0 and updated=0
    await waitFor(() => {
      // The green success result panel should be present
      const panel = document.querySelector(".bg-green-50.border-green-100");
      expect(panel).toBeInTheDocument();
    });
  });

  it("handles Telegram sync with missing data fields", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ telegram_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/telegram")
        return Promise.resolve({ data: { data: {} } });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByText("Sync Chats")).toBeInTheDocument());
    await user.click(screen.getByText("Sync Chats"));
    await waitFor(() => {
      expect(screen.getByText("0 new interactions")).toBeInTheDocument();
    });
  });

  it("handles Twitter sync with missing data fields", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me")
        return Promise.resolve(mockMeResponse({ twitter_connected: true }));
      return Promise.reject(new Error("unexpected"));
    });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/contacts/sync/twitter")
        return Promise.resolve({ data: { data: {} } });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByText("Sync Activity")).toBeInTheDocument());
    await user.click(screen.getByText("Sync Activity"));
    await waitFor(() => {
      expect(screen.getByText("0 new interactions")).toBeInTheDocument();
    });
  });

  it("handles Telegram send code with missing phone_code_hash", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: {} } });
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByText("Connect Telegram")).toBeInTheDocument());
    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));
    // Should still transition to code step
    await waitFor(() => {
      expect(screen.getByPlaceholderText("12345")).toBeInTheDocument();
    });
  });

  // ─── showSuccess without username ──────────────────────────────────

  it("handles showSuccess without username", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { connected: true } } }); // no username
      return Promise.reject(new Error("unexpected"));
    });
    let callCount = 0;
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") {
        callCount++;
        if (callCount > 1)
          return Promise.resolve(mockMeResponse({ telegram_connected: true }));
        return Promise.resolve(mockMeResponse());
      }
      return Promise.reject(new Error("unexpected"));
    });

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByText("Connect Telegram")).toBeInTheDocument());
    await user.click(screen.getByText("Connect Telegram"));
    await user.type(screen.getByPlaceholderText("+1234567890"), "+15551234567");
    await user.click(screen.getByText("Send code"));
    await waitFor(() => expect(screen.getByPlaceholderText("12345")).toBeInTheDocument());
    await user.type(screen.getByPlaceholderText("12345"), "99999");
    await user.click(screen.getByText("Verify"));
    await waitFor(() => expect(screen.getByText("Telegram Connected")).toBeInTheDocument());
    await user.click(screen.getByText("Done"));
    // No connectedLabel shown since no username
    expect(screen.queryByText(/connected @/)).not.toBeInTheDocument();
  });

  // ─── showSuccess optimistic update ────────────────────────────────

  it("optimistically updates connected state with username", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockedApi.post.mockImplementation((url: string) => {
      if (url === "/auth/telegram/connect")
        return Promise.resolve({ data: { data: { phone_code_hash: "hash" } } });
      if (url === "/auth/telegram/verify")
        return Promise.resolve({ data: { data: { connected: true, username: "testuser" } } });
      return Promise.reject(new Error("unexpected"));
    });
    // Subsequent /me calls also return connected
    let callCount = 0;
    mockedApi.get.mockImplementation((url: string) => {
      if (url === "/auth/me") {
        callCount++;
        if (callCount > 1)
          return Promise.resolve(
            mockMeResponse({ telegram_connected: true, telegram_username: "testuser" })
          );
        return Promise.resolve(mockMeResponse());
      }
      return Promise.reject(new Error("unexpected"));
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

    // Success modal appears
    await waitFor(() => {
      expect(screen.getByText("Telegram Connected")).toBeInTheDocument();
    });

    // Close modal and verify connected label
    await user.click(screen.getByText("Done"));
    await waitFor(() => {
      expect(screen.getByText("connected @testuser")).toBeInTheDocument();
    });
  });
});
