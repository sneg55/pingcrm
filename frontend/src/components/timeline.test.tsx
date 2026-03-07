import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Timeline, type TimelineEntry } from "./timeline";

const makeEntry = (overrides: Partial<TimelineEntry> = {}): TimelineEntry => ({
  id: "1",
  platform: "email",
  direction: "inbound",
  content_preview: "Hey there!",
  occurred_at: new Date().toISOString(),
  ...overrides,
});

describe("Timeline", () => {
  it("shows empty state when no interactions", () => {
    render(<Timeline interactions={[]} />);
    expect(
      screen.getByText("No interactions yet. Add a note to get started.")
    ).toBeInTheDocument();
  });

  it("renders interaction entries", () => {
    const entries = [
      makeEntry({ id: "1", platform: "email", content_preview: "Email msg" }),
      makeEntry({
        id: "2",
        platform: "telegram",
        content_preview: "TG msg",
      }),
    ];
    render(<Timeline interactions={entries} />);
    expect(screen.getByText("Email msg")).toBeInTheDocument();
    expect(screen.getByText("TG msg")).toBeInTheDocument();
  });

  it("renders platform label for each entry", () => {
    render(
      <Timeline interactions={[makeEntry({ platform: "twitter" })]} />
    );
    expect(screen.getByText(/twitter/)).toBeInTheDocument();
  });

  it("shows Add note button", () => {
    render(<Timeline interactions={[]} />);
    expect(
      screen.getByRole("button", { name: /Add note/ })
    ).toBeInTheDocument();
  });

  it("toggles note input on Add note click", () => {
    render(<Timeline interactions={[]} />);
    fireEvent.click(screen.getByRole("button", { name: /Add note/ }));
    expect(
      screen.getByPlaceholderText("Write a note...")
    ).toBeInTheDocument();
  });

  it("calls onAddNote with trimmed text on Save", () => {
    const onAddNote = vi.fn();
    render(<Timeline interactions={[]} onAddNote={onAddNote} />);
    fireEvent.click(screen.getByRole("button", { name: /Add note/ }));
    fireEvent.change(screen.getByPlaceholderText("Write a note..."), {
      target: { value: "  My note  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onAddNote).toHaveBeenCalledWith("My note");
  });

  it("does not call onAddNote with empty text", () => {
    const onAddNote = vi.fn();
    render(<Timeline interactions={[]} onAddNote={onAddNote} />);
    fireEvent.click(screen.getByRole("button", { name: /Add note/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onAddNote).not.toHaveBeenCalled();
  });

  it("hides note input on Cancel", () => {
    render(<Timeline interactions={[]} />);
    fireEvent.click(screen.getByRole("button", { name: /Add note/ }));
    expect(
      screen.getByPlaceholderText("Write a note...")
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByPlaceholderText("Write a note...")
    ).not.toBeInTheDocument();
  });

  it("hides entry content_preview when null", () => {
    render(
      <Timeline
        interactions={[makeEntry({ content_preview: null })]}
      />
    );
    // Should still show platform label
    expect(screen.getByText(/email/)).toBeInTheDocument();
  });

  it("renders meeting platform entries", () => {
    render(
      <Timeline
        interactions={[
          makeEntry({ platform: "meeting", content_preview: "Team standup" }),
        ]}
      />
    );
    expect(screen.getByText("Team standup")).toBeInTheDocument();
    expect(screen.getByText(/meeting/)).toBeInTheDocument();
  });

  it("renders manual platform entries", () => {
    render(
      <Timeline
        interactions={[
          makeEntry({ platform: "manual", content_preview: "Handwritten note" }),
        ]}
      />
    );
    expect(screen.getByText("Handwritten note")).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(
      <Timeline interactions={[]} className="my-custom" />
    );
    expect(container.firstChild).toHaveClass("my-custom");
  });
});
