/**
 * Tests for the InlineField component.
 *
 * InlineField is defined inline inside contacts/[id]/page.tsx and is not
 * exported, so we replicate it here as a standalone component that mirrors
 * the exact behavior found in that file.
 */

import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useState, useRef, useEffect } from "react";

/* ── Standalone replica of InlineField ── */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        void navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      title="Copy"
      data-testid="copy-button"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function InlineField({
  label,
  value,
  displayValue,
  onSave,
  copyable,
  isLink,
  linkPrefix,
}: {
  label: string;
  value: string | null | undefined;
  displayValue?: string;
  onSave: (v: string) => void;
  copyable?: boolean;
  isLink?: boolean;
  linkPrefix?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft !== (value ?? "")) onSave(draft);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(value ?? "");
    setEditing(false);
  };

  const startEdit = () => {
    setDraft(value ?? "");
    setEditing(true);
  };

  return (
    <div>
      <span>{label}</span>
      {editing ? (
        <div>
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") cancel();
            }}
          />
          <button onClick={cancel}>Cancel</button>
          <button onClick={save}>Save</button>
        </div>
      ) : (
        <div>
          {value ? (
            isLink && linkPrefix !== undefined ? (
              <a
                href={`${linkPrefix}${value}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
              >
                {displayValue ?? value}
              </a>
            ) : (
              <span>{displayValue ?? value}</span>
            )
          ) : (
            <span>—</span>
          )}
          {copyable && value && <CopyButton text={value} />}
          <button onClick={startEdit} aria-label="Edit">
            <span data-testid="icon-Pencil" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Tests ── */

describe("InlineField", () => {
  it("renders the label and value in view mode", () => {
    render(
      <InlineField label="Twitter" value="@alice" onSave={vi.fn()} />
    );
    expect(screen.getByText("Twitter")).toBeInTheDocument();
    expect(screen.getByText("@alice")).toBeInTheDocument();
  });

  it('shows an em-dash when value is empty', () => {
    render(<InlineField label="Company" value="" onSave={vi.fn()} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it('shows an em-dash when value is null', () => {
    render(<InlineField label="Company" value={null} onSave={vi.fn()} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders value as a mailto: link when linkPrefix is 'mailto:'", () => {
    render(
      <InlineField
        label="Email"
        value="alice@example.com"
        onSave={vi.fn()}
        isLink
        linkPrefix="mailto:"
      />
    );
    const link = screen.getByRole("link", { name: "alice@example.com" });
    expect(link).toHaveAttribute("href", "mailto:alice@example.com");
  });

  it("renders value as a tel: link when linkPrefix is 'tel:'", () => {
    render(
      <InlineField
        label="Phone"
        value="+1234567890"
        onSave={vi.fn()}
        isLink
        linkPrefix="tel:"
      />
    );
    const link = screen.getByRole("link", { name: "+1234567890" });
    expect(link).toHaveAttribute("href", "tel:+1234567890");
  });

  it("renders value as an https:// link when linkPrefix is 'https://'", () => {
    render(
      <InlineField
        label="Website"
        value="example.com"
        onSave={vi.fn()}
        isLink
        linkPrefix="https://"
      />
    );
    const link = screen.getByRole("link", { name: "example.com" });
    expect(link).toHaveAttribute("href", "https://example.com");
  });

  it("uses displayValue in the link text when provided", () => {
    render(
      <InlineField
        label="Twitter"
        value="alice"
        displayValue="@alice"
        onSave={vi.fn()}
        isLink
        linkPrefix="https://x.com/"
      />
    );
    const link = screen.getByRole("link", { name: "@alice" });
    expect(link).toHaveAttribute("href", "https://x.com/alice");
  });

  it("shows the pencil edit button in view mode", () => {
    render(<InlineField label="Name" value="Alice" onSave={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByTestId("icon-Pencil")).toBeInTheDocument();
  });

  it("clicking the pencil button opens edit mode with input pre-filled", () => {
    render(<InlineField label="Name" value="Alice" onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByDisplayValue("Alice")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("clicking Cancel closes edit mode without calling onSave", () => {
    const onSave = vi.fn();
    render(<InlineField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByDisplayValue("Alice"), {
      target: { value: "Bob" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("clicking Save calls onSave with the new value", () => {
    const onSave = vi.fn();
    render(<InlineField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByDisplayValue("Alice"), {
      target: { value: "Bob" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalledWith("Bob");
  });

  it("pressing Enter in the input triggers save with new value", () => {
    const onSave = vi.fn();
    render(<InlineField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const input = screen.getByDisplayValue("Alice");
    fireEvent.change(input, { target: { value: "Charlie" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSave).toHaveBeenCalledWith("Charlie");
  });

  it("pressing Escape in the input cancels editing without calling onSave", () => {
    const onSave = vi.fn();
    render(<InlineField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const input = screen.getByDisplayValue("Alice");
    fireEvent.change(input, { target: { value: "Changed" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("does not call onSave when value is unchanged on Save", () => {
    const onSave = vi.fn();
    render(<InlineField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    // do not change the draft — value stays "Alice"
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("shows the Copy button when copyable prop is true and value is set", () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      writable: true,
      configurable: true,
    });
    render(
      <InlineField
        label="Email"
        value="alice@example.com"
        onSave={vi.fn()}
        copyable
      />
    );
    expect(screen.getByTestId("copy-button")).toBeInTheDocument();
  });

  it("clicking the Copy button writes value to clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      writable: true,
      configurable: true,
    });
    render(
      <InlineField
        label="Email"
        value="alice@example.com"
        onSave={vi.fn()}
        copyable
      />
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId("copy-button"));
    });
    expect(writeText).toHaveBeenCalledWith("alice@example.com");
  });

  it("does not show the Copy button when copyable is false", () => {
    render(
      <InlineField label="Email" value="alice@example.com" onSave={vi.fn()} />
    );
    expect(screen.queryByTestId("copy-button")).not.toBeInTheDocument();
  });

  it("does not show the Copy button when value is empty even if copyable", () => {
    render(
      <InlineField label="Email" value="" onSave={vi.fn()} copyable />
    );
    expect(screen.queryByTestId("copy-button")).not.toBeInTheDocument();
  });
});
