import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import NewContactPage from "./page";

// Mock api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    DELETE: vi.fn(),
  },
}));

// Mock useCreateContact hook
const mockMutateAsync = vi.fn();
const mockUseCreateContact = vi.fn();

vi.mock("@/hooks/use-contacts", () => ({
  useCreateContact: (...args: unknown[]) => mockUseCreateContact(...args),
}));

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: vi.fn(() => ({ get: vi.fn(() => null) })),
  useRouter: vi.fn(() => ({
    push: mockPush,
    replace: vi.fn(),
    back: vi.fn(),
  })),
  usePathname: vi.fn(() => "/contacts/new"),
  useParams: vi.fn(() => ({})),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPage() {
  return render(<NewContactPage />, { wrapper });
}

describe("NewContactPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCreateContact.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    });
  });

  it("renders the page heading and all form fields", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Add contact" })).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/phone/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/company/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/twitter handle/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/telegram username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/tags/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/notes/i)).toBeInTheDocument();
  });

  it("renders the submit and cancel buttons", () => {
    renderPage();

    expect(screen.getByRole("button", { name: "Create contact" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cancel" })).toBeInTheDocument();
  });

  it("cancel link points back to /contacts", () => {
    renderPage();

    const cancelLink = screen.getByRole("link", { name: "Cancel" });
    expect(cancelLink).toHaveAttribute("href", "/contacts");
  });

  it("breadcrumb back-arrow link points to /contacts", () => {
    renderPage();

    // The ArrowLeft icon link is the first link on the page
    const links = screen.getAllByRole("link");
    const backLink = links.find((l) => l.getAttribute("href") === "/contacts");
    expect(backLink).toBeInTheDocument();
  });

  it("submits form data and redirects to contact detail on success", async () => {
    const newId = "abc-123";
    mockMutateAsync.mockResolvedValueOnce({ data: { id: newId } });

    renderPage();

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Jane Smith" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "jane@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/phone/i), {
      target: { value: "+1 555 000 0000" },
    });
    fireEvent.change(screen.getByLabelText(/company/i), {
      target: { value: "Acme Corp" },
    });

    fireEvent.submit(screen.getByRole("button", { name: "Create contact" }).closest("form")!);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name: "Jane Smith",
          emails: ["jane@example.com"],
          phones: ["+1 555 000 0000"],
          company: "Acme Corp",
        })
      );
    });

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(`/contacts/${newId}`);
    });
  });

  it("passes comma-separated tags as an array", async () => {
    mockMutateAsync.mockResolvedValueOnce({ data: { id: "x1" } });

    renderPage();

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "John Doe" },
    });
    fireEvent.change(screen.getByLabelText(/tags/i), {
      target: { value: "investor, advisor, customer" },
    });

    fireEvent.submit(screen.getByRole("button", { name: "Create contact" }).closest("form")!);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: ["investor", "advisor", "customer"],
        })
      );
    });
  });

  it("shows an error message when contact creation fails", async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error("Network error"));

    renderPage();

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Jane Smith" },
    });

    fireEvent.submit(screen.getByRole("button", { name: "Create contact" }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("shows fallback error text when a non-Error is thrown", async () => {
    mockMutateAsync.mockRejectedValueOnce("unexpected failure");

    renderPage();

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Jane Smith" },
    });

    fireEvent.submit(screen.getByRole("button", { name: "Create contact" }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("Failed to create contact.")).toBeInTheDocument();
    });
  });

  it("disables the submit button and shows 'Creating...' while pending", () => {
    mockUseCreateContact.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: true,
    });

    renderPage();

    const submitButton = screen.getByRole("button", { name: "Creating..." });
    expect(submitButton).toBeDisabled();
  });

  it("submits empty arrays when optional fields are blank", async () => {
    mockMutateAsync.mockResolvedValueOnce({ data: { id: "y1" } });

    renderPage();

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Minimal Contact" },
    });

    fireEvent.submit(screen.getByRole("button", { name: "Create contact" }).closest("form")!);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name: "Minimal Contact",
          emails: [],
          phones: [],
          tags: [],
        })
      );
    });
  });
});
