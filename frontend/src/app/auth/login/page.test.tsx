import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import LoginPage from "./page";

// Mock useAuth
const mockLogin = vi.fn();
vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    login: mockLogin,
    user: null,
    isLoading: false,
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

const mockPush = vi.fn();
vi.mock("next/navigation", async () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => "/auth/login",
  useParams: () => ({}),
}));

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLogin.mockResolvedValue(undefined);
  });

  it("renders sign in form", () => {
    render(<LoginPage />);
    expect(screen.getByText("Sign in to your account")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("renders link to register page", () => {
    render(<LoginPage />);
    const link = screen.getByText("Create one");
    expect(link).toBeInTheDocument();
    expect(link.closest("a")).toHaveAttribute("href", "/auth/register");
  });

  it("calls login and redirects on successful submit", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "mypassword" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("test@example.com", "mypassword");
    });
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("shows error message on login failure", async () => {
    mockLogin.mockRejectedValue(new Error("Incorrect email or password"));
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "bad@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByText("Incorrect email or password")).toBeInTheDocument();
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("shows fallback error for non-Error rejections", async () => {
    mockLogin.mockRejectedValue("unknown");
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "bad@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials. Please try again.")).toBeInTheDocument();
    });
  });

  it("disables button while submitting", async () => {
    let resolveLogin: () => void;
    mockLogin.mockImplementation(
      () => new Promise<void>((resolve) => { resolveLogin = resolve; })
    );
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "pass" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Signing in..." })).toBeDisabled();
    });

    resolveLogin!();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sign in" })).not.toBeDisabled();
    });
  });

  it("shows app name", () => {
    render(<LoginPage />);
    expect(screen.getByText("Ping")).toBeInTheDocument();
  });
});
