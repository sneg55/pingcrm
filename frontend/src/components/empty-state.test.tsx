import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders title", () => {
    render(<EmptyState title="No contacts" />);
    expect(screen.getByText("No contacts")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(
      <EmptyState title="No contacts" description="Add your first contact" />
    );
    expect(screen.getByText("Add your first contact")).toBeInTheDocument();
  });

  it("does not render description when not provided", () => {
    const { container } = render(<EmptyState title="No contacts" />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });

  it("renders link action with href", () => {
    render(
      <EmptyState
        title="No contacts"
        action={{ label: "Add Contact", href: "/contacts/new" }}
      />
    );
    const link = screen.getByText("Add Contact");
    expect(link.tagName).toBe("A");
    expect(link).toHaveAttribute("href", "/contacts/new");
  });

  it("renders button action with onClick", () => {
    const onClick = vi.fn();
    render(
      <EmptyState
        title="No contacts"
        action={{ label: "Add Contact", onClick }}
      />
    );
    fireEvent.click(screen.getByText("Add Contact"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not render action when not provided", () => {
    render(<EmptyState title="No contacts" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
