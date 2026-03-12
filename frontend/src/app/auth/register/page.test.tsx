import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import RegisterPage from "./page";

// Mock useAuth
const mockRegister = vi.fn();
vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    register: mockRegister,
    user: null,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

const mockPush = vi.fn();
vi.mock("next/navigation", async () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => "/auth/register",
  useParams: () => ({}),
}));

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRegister.mockResolvedValue(undefined);
  });

  it("renders form with name, email, and password fields", () => {
    render(<RegisterPage />);
    expect(screen.getByText("Create your account")).toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create account" })
    ).toBeInTheDocument();
  });

  it("renders link to sign-in page", () => {
    render(<RegisterPage />);
    const link = screen.getByText("Sign in");
    expect(link).toBeInTheDocument();
    expect(link.closest("a")).toHaveAttribute("href", "/auth/login");
  });

  it("shows app name", () => {
    render(<RegisterPage />);
    expect(screen.getByText("Ping")).toBeInTheDocument();
  });

  it("calls register with correct args and redirects on success", async () => {
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Jane Smith" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "jane@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith(
        "jane@example.com",
        "secret123",
        "Jane Smith"
      );
    });
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/onboarding");
    });
  });

  it("shows error message on API failure", async () => {
    mockRegister.mockRejectedValue(new Error("Email already registered"));
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Jane Smith" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "existing@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(
        screen.getByText("Email already registered")
      ).toBeInTheDocument();
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("shows fallback error for non-Error rejections", async () => {
    mockRegister.mockRejectedValue("network error");
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Jane Smith" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "jane@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(
        screen.getByText("Registration failed. Please try again.")
      ).toBeInTheDocument();
    });
  });

  it("disables button while submitting", async () => {
    let resolveRegister: () => void;
    mockRegister.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveRegister = resolve;
        })
    );
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Jane Smith" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "jane@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Creating account..." })
      ).toBeDisabled();
    });

    resolveRegister!();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Create account" })
      ).not.toBeDisabled();
    });
  });

  it("does not redirect on failed submit", async () => {
    mockRegister.mockRejectedValue(new Error("Bad request"));
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Jane Smith" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "jane@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(screen.getByText("Bad request")).toBeInTheDocument();
    });
    expect(mockPush).not.toHaveBeenCalled();
  });
});
