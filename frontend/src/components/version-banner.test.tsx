import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { VersionBanner } from "./version-banner";

vi.mock("@/hooks/use-version", () => ({
  useVersion: vi.fn(),
}));
import { useVersion } from "@/hooks/use-version";

const baseStatus = {
  current: "v1.6.0",
  latest: "v1.7.0",
  release_url: "https://github.com/sneg55/pingcrm/releases/tag/v1.7.0",
  release_notes: "## What's new\n- birthday suggestions",
  update_available: true,
  checked_at: "2026-05-12T14:00:00Z",
  disabled: false,
};

describe("VersionBanner", () => {
  let store: Record<string, string>;

  beforeEach(() => {
    store = {};
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => {
        store[k] = String(v);
      },
      removeItem: (k: string) => {
        delete store[k];
      },
      clear: () => {
        store = {};
      },
      key: () => null,
      length: 0,
    });
    vi.clearAllMocks();
  });

  it("renders nothing when update_available is false", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...baseStatus, update_available: false },
    });
    const { container } = render(<VersionBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when update_available is null", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...baseStatus, update_available: null },
    });
    const { container } = render(<VersionBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the banner with version pair when update available", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({ data: baseStatus });
    render(<VersionBanner />);
    expect(screen.getByText(/v1\.7\.0 is available/)).toBeInTheDocument();
    expect(screen.getByText(/v1\.6\.0/)).toBeInTheDocument();
  });

  it("hides the banner when dismissed value matches latest", () => {
    localStorage.setItem("pingcrm.dismissed_version", "v1.7.0");
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({ data: baseStatus });
    const { container } = render(<VersionBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("reappears when latest advances past dismissed value", () => {
    localStorage.setItem("pingcrm.dismissed_version", "v1.7.0");
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...baseStatus, latest: "v1.8.0" },
    });
    render(<VersionBanner />);
    expect(screen.getByText(/v1\.8\.0 is available/)).toBeInTheDocument();
  });

  it("stores dismissed version in localStorage when dismiss clicked", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({ data: baseStatus });
    render(<VersionBanner />);
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(localStorage.getItem("pingcrm.dismissed_version")).toBe("v1.7.0");
  });

  it("expands release notes when toggle clicked", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({ data: baseStatus });
    render(<VersionBanner />);
    expect(screen.queryByText(/birthday suggestions/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /release notes/i }));
    expect(screen.getByText(/birthday suggestions/)).toBeInTheDocument();
  });
});
