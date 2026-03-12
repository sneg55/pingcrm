import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { InlineListField } from "./inline-list-field";

describe("InlineListField", () => {
  it("renders label and first value", () => {
    render(
      <InlineListField
        label="Email"
        values={["alice@example.com"]}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("renders phone values", () => {
    render(
      <InlineListField
        label="Phone"
        values={["+1-555-0100"]}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByText("Phone")).toBeInTheDocument();
    expect(screen.getByText("+1-555-0100")).toBeInTheDocument();
  });

  it('shows "+N" badge when multiple values exist', () => {
    render(
      <InlineListField
        label="Email"
        values={["alice@example.com", "bob@example.com", "carol@example.com"]}
        onSave={vi.fn()}
      />
    );
    // First value is shown; others are summarised as +2
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
  });

  it('shows "—" when values array is empty', () => {
    render(
      <InlineListField label="Email" values={[]} onSave={vi.fn()} />
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("clicking the pencil button opens edit mode", () => {
    render(
      <InlineListField
        label="Email"
        values={["alice@example.com"]}
        onSave={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    // Input should now be visible pre-populated with the value
    expect(screen.getByDisplayValue("alice@example.com")).toBeInTheDocument();
  });

  it("edit mode shows comma-separated values when multiple items exist", () => {
    render(
      <InlineListField
        label="Email"
        values={["a@b.com", "c@d.com"]}
        onSave={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    expect(screen.getByDisplayValue("a@b.com, c@d.com")).toBeInTheDocument();
  });

  it("Save button calls onSave with parsed array", () => {
    const onSave = vi.fn();
    render(
      <InlineListField
        label="Email"
        values={["alice@example.com"]}
        onSave={onSave}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, {
      target: { value: "new@example.com, second@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSave).toHaveBeenCalledWith(["new@example.com", "second@example.com"]);
  });

  it("pressing Enter in input calls onSave", () => {
    const onSave = vi.fn();
    render(
      <InlineListField label="Email" values={["alice@example.com"]} onSave={onSave} />
    );
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "new@example.com" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSave).toHaveBeenCalledWith(["new@example.com"]);
  });

  it("Cancel button reverts to original values without calling onSave", () => {
    const onSave = vi.fn();
    render(
      <InlineListField
        label="Email"
        values={["alice@example.com"]}
        onSave={onSave}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "changed@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onSave).not.toHaveBeenCalled();
    // Original value is visible again
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("pressing Escape reverts to original values without calling onSave", () => {
    const onSave = vi.fn();
    render(
      <InlineListField label="Email" values={["alice@example.com"]} onSave={onSave} />
    );
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "changed@example.com" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("renders value as link when isLink and linkPrefix are provided", () => {
    render(
      <InlineListField
        label="Email"
        values={["alice@example.com"]}
        onSave={vi.fn()}
        isLink
        linkPrefix="mailto:"
      />
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "mailto:alice@example.com");
    expect(link).toHaveTextContent("alice@example.com");
  });

  it("renders phone as tel link when isLink and linkPrefix='tel:' are provided", () => {
    render(
      <InlineListField
        label="Phone"
        values={["+1-555-0100"]}
        onSave={vi.fn()}
        isLink
        linkPrefix="tel:"
      />
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "tel:+1-555-0100");
  });

  it("filters out blank entries when saving", () => {
    const onSave = vi.fn();
    render(
      <InlineListField label="Email" values={[]} onSave={onSave} />
    );
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const input = screen.getByRole("textbox");
    // Trailing comma should not produce an empty entry
    fireEvent.change(input, { target: { value: "a@b.com, , c@d.com," } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSave).toHaveBeenCalledWith(["a@b.com", "c@d.com"]);
  });
});
