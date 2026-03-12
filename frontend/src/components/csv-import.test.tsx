import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CsvImport } from "./csv-import";

// Mock api-client
vi.mock("@/lib/api-client", () => ({
  client: {
    POST: vi.fn(),
  },
}));

import { client } from "@/lib/api-client";
const mockPost = vi.mocked(client.POST);

// Helper: create a fake CSV File object
function makeCsvFile(content: string, name = "contacts.csv"): File {
  return new File([content], name, { type: "text/csv" });
}

// Helper: simulate FileReader loading a file
function mockFileReader(content: string) {
  const originalFileReader = globalThis.FileReader;
  const mockLoad = vi.fn();

  const MockFileReader = vi.fn().mockImplementation(function (this: {
    onload: ((e: ProgressEvent<FileReader>) => void) | null;
    readAsText: (file: File) => void;
    result: string;
  }) {
    this.onload = null;
    this.result = content;
    this.readAsText = (_file: File) => {
      mockLoad.mockImplementation(() => {
        if (this.onload) {
          this.onload({ target: this } as unknown as ProgressEvent<FileReader>);
        }
      });
      // Trigger onload asynchronously
      setTimeout(() => {
        if (this.onload) {
          this.onload({ target: this } as unknown as ProgressEvent<FileReader>);
        }
      }, 0);
    };
  });

  globalThis.FileReader = MockFileReader as unknown as typeof FileReader;
  return () => {
    globalThis.FileReader = originalFileReader;
  };
}

const CSV_CONTENT = `name,email,phone,company
Alice Smith,alice@example.com,555-1234,Acme Inc
Bob Jones,bob@example.com,555-5678,Corp Ltd`;

describe("CsvImport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders file upload input and drop zone", () => {
    render(<CsvImport />);
    expect(screen.getByText(/Drop a CSV file here/i)).toBeInTheDocument();
    const input = document.querySelector("input[type='file']");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("accept", ".csv,text/csv");
  });

  it("shows supported columns hint text", () => {
    render(<CsvImport />);
    expect(
      screen.getByText(/Supported columns: name, email, phone, company, title, tags/i)
    ).toBeInTheDocument();
  });

  it("shows preview table with headers and rows after file selection", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      // Allow FileReader's setTimeout to fire
      await new Promise((r) => setTimeout(r, 10));
    });

    // File name should appear
    expect(screen.getByText("contacts.csv")).toBeInTheDocument();

    // Column headers from CSV
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("email")).toBeInTheDocument();
    expect(screen.getByText("phone")).toBeInTheDocument();
    expect(screen.getByText("company")).toBeInTheDocument();

    // Data rows
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();

    restore();
  });

  it("shows Import contacts button after file selection", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(screen.getByRole("button", { name: /Import contacts/i })).toBeInTheDocument();

    restore();
  });

  it("calls POST /api/v1/contacts/import/csv when Import contacts is clicked", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    mockPost.mockResolvedValueOnce({
      data: { data: { created: 2, errors: [] } },
      error: undefined,
    } as unknown as Awaited<ReturnType<typeof client.POST>>);

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    const importBtn = screen.getByRole("button", { name: /Import contacts/i });
    await act(async () => {
      fireEvent.click(importBtn);
    });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/v1/contacts/import/csv",
        expect.objectContaining({ bodySerializer: expect.any(Function) })
      );
    });

    restore();
  });

  it("shows success state with created count after successful import", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    mockPost.mockResolvedValueOnce({
      data: { data: { created: 2, errors: [] } },
      error: undefined,
    } as unknown as Awaited<ReturnType<typeof client.POST>>);

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Import contacts/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/Import complete/i)).toBeInTheDocument();
      expect(screen.getByText(/2 contacts created/i)).toBeInTheDocument();
    });

    restore();
  });

  it("shows success state with partial errors listed", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    mockPost.mockResolvedValueOnce({
      data: { data: { created: 1, errors: ["Row 2: missing required field 'name'"] } },
      error: undefined,
    } as unknown as Awaited<ReturnType<typeof client.POST>>);

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Import contacts/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/Import complete/i)).toBeInTheDocument();
      expect(screen.getByText(/Row 2: missing required field/i)).toBeInTheDocument();
    });

    restore();
  });

  it("shows error message when API returns an error", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    mockPost.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "Invalid CSV format" },
    } as unknown as Awaited<ReturnType<typeof client.POST>>);

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Import contacts/i }));
    });

    await waitFor(() => {
      expect(screen.getByText("Invalid CSV format")).toBeInTheDocument();
    });

    restore();
  });

  it("shows generic error message when API throws", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    mockPost.mockRejectedValueOnce(new Error("Network error"));

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Import contacts/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/Import failed. Please try again./i)).toBeInTheDocument();
    });

    restore();
  });

  it("resets back to upload state when X button is clicked on file preview", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(screen.getByText("contacts.csv")).toBeInTheDocument();

    // Click the dismiss X button (not the upload icon, but the reset button in the file preview)
    const xButtons = screen.getAllByRole("button");
    const resetBtn = xButtons.find((btn) => !btn.textContent?.includes("Import"));
    expect(resetBtn).toBeTruthy();
    fireEvent.click(resetBtn!);

    // Drop zone should reappear
    expect(screen.getByText(/Drop a CSV file here/i)).toBeInTheDocument();

    restore();
  });

  it("resets back to upload state when X button is clicked on success panel", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    mockPost.mockResolvedValueOnce({
      data: { data: { created: 1, errors: [] } },
      error: undefined,
    } as unknown as Awaited<ReturnType<typeof client.POST>>);

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Import contacts/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/Import complete/i)).toBeInTheDocument();
    });

    // Click X on the success panel
    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByText(/Drop a CSV file here/i)).toBeInTheDocument();

    restore();
  });

  it("shows Importing... label while upload is in progress", async () => {
    const restore = mockFileReader(CSV_CONTENT);

    // Never resolve so we can check intermediate state
    let resolveImport!: () => void;
    const importPromise = new Promise<void>((resolve) => {
      resolveImport = resolve;
    });
    mockPost.mockImplementationOnce(async () => {
      await importPromise;
      return { data: { data: { created: 0, errors: [] } }, error: undefined } as unknown as Awaited<ReturnType<typeof client.POST>>;
    });

    render(<CsvImport />);

    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    const file = makeCsvFile(CSV_CONTENT);

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await new Promise((r) => setTimeout(r, 10));
    });

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /Import contacts/i }));
    });

    await waitFor(() => {
      expect(screen.getByText("Importing...")).toBeInTheDocument();
    });

    // The button should be disabled during upload
    expect(screen.getByRole("button", { name: "Importing..." })).toBeDisabled();

    // Clean up
    resolveImport();
    restore();
  });
});
