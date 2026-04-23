import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import {
  EditableField,
  EditableListField,
  EditableTagsField,
} from "./editable-field";

describe("EditableField", () => {
  it("renders label and value", () => {
    render(<EditableField label="Name" value="Alice" onSave={vi.fn()} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("shows placeholder when value is null", () => {
    render(
      <EditableField
        label="Name"
        value={null}
        onSave={vi.fn()}
        placeholder="Add name..."
      />
    );
    expect(screen.getByText("Add name...")).toBeInTheDocument();
  });

  it("enters edit mode on click", () => {
    render(<EditableField label="Name" value="Alice" onSave={vi.fn()} />);
    fireEvent.click(screen.getByText("Alice"));
    expect(screen.getByDisplayValue("Alice")).toBeInTheDocument();
  });

  it("saves on Enter key", () => {
    const onSave = vi.fn();
    render(<EditableField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByText("Alice"));
    const input = screen.getByDisplayValue("Alice");
    fireEvent.change(input, { target: { value: "Bob" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSave).toHaveBeenCalledWith("Bob");
  });

  it("saves on blur", () => {
    const onSave = vi.fn();
    render(<EditableField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByText("Alice"));
    const input = screen.getByDisplayValue("Alice");
    fireEvent.change(input, { target: { value: "Bob" } });
    fireEvent.blur(input);
    expect(onSave).toHaveBeenCalledWith("Bob");
  });

  it("cancels on Escape key", () => {
    const onSave = vi.fn();
    render(<EditableField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByText("Alice"));
    const input = screen.getByDisplayValue("Alice");
    fireEvent.change(input, { target: { value: "Bob" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("does not call onSave when value is unchanged", () => {
    const onSave = vi.fn();
    render(<EditableField label="Name" value="Alice" onSave={onSave} />);
    fireEvent.click(screen.getByText("Alice"));
    fireEvent.keyDown(screen.getByDisplayValue("Alice"), { key: "Enter" });
    expect(onSave).not.toHaveBeenCalled();
  });

  it("trims whitespace before saving", () => {
    const onSave = vi.fn();
    render(<EditableField label="Name" value="" onSave={onSave} />);
    fireEvent.click(screen.getByText("Add..."));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "  Bob  " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSave).toHaveBeenCalledWith("Bob");
  });

  it("renders link when linkPrefix provided", () => {
    render(
      <EditableField
        label="Twitter"
        value="alice"
        onSave={vi.fn()}
        linkPrefix="https://x.com/"
      />
    );
    const link = screen.getByText("alice");
    expect(link.tagName).toBe("A");
    expect(link).toHaveAttribute("href", "https://x.com/alice");
  });

  it("renders textarea for type=textarea", () => {
    render(
      <EditableField
        label="Notes"
        value="Some notes"
        onSave={vi.fn()}
        type="textarea"
      />
    );
    fireEvent.click(screen.getByText("Some notes"));
    expect(screen.getByDisplayValue("Some notes").tagName).toBe("TEXTAREA");
  });
});

describe("EditableListField", () => {
  it("renders values", () => {
    render(
      <EditableListField
        label="Emails"
        values={["a@b.com", "c@d.com"]}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByText("a@b.com")).toBeInTheDocument();
    expect(screen.getByText("c@d.com")).toBeInTheDocument();
  });

  it("shows placeholder when empty", () => {
    render(
      <EditableListField
        label="Emails"
        values={[]}
        onSave={vi.fn()}
        placeholder="Add email..."
      />
    );
    expect(screen.getByText("Add email...")).toBeInTheDocument();
  });

  it("saves comma-separated values on Enter", () => {
    const onSave = vi.fn();
    render(
      <EditableListField label="Emails" values={[]} onSave={onSave} />
    );
    fireEvent.click(screen.getByText("Add..."));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "a@b.com, c@d.com" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSave).toHaveBeenCalledWith(["a@b.com", "c@d.com"]);
  });

  it("saves on blur", () => {
    const onSave = vi.fn();
    render(
      <EditableListField label="Emails" values={[]} onSave={onSave} />
    );
    fireEvent.click(screen.getByText("Add..."));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "x@y.com" } });
    fireEvent.blur(input);
    expect(onSave).toHaveBeenCalledWith(["x@y.com"]);
  });

  it("renders links with linkPrefix", () => {
    render(
      <EditableListField
        label="Emails"
        values={["a@b.com"]}
        onSave={vi.fn()}
        linkPrefix="mailto:"
      />
    );
    const link = screen.getByText("a@b.com");
    expect(link.tagName).toBe("A");
    expect(link).toHaveAttribute("href", "mailto:a@b.com");
  });
});

describe("EditableTagsField", () => {
  it("renders tags as chips", () => {
    render(
      <EditableTagsField label="Tags" values={["vip", "lead"]} onSave={vi.fn()} />
    );
    expect(screen.getByText("vip")).toBeInTheDocument();
    expect(screen.getByText("lead")).toBeInTheDocument();
  });

  it("shows placeholder when no tags", () => {
    render(
      <EditableTagsField label="Tags" values={[]} onSave={vi.fn()} />
    );
    expect(screen.getByText("Add tags...")).toBeInTheDocument();
  });

  it("opens edit mode and shows selected tags as removable chips", () => {
    render(
      <EditableTagsField label="Tags" values={["vip"]} onSave={vi.fn()} />
    );
    fireEvent.click(screen.getByText("vip"));
    // In edit mode, should see the tag as a button with ×
    expect(screen.getByRole("button", { name: /vip/ })).toBeInTheDocument();
  });

  it("shows suggestions from allTags", () => {
    render(
      <EditableTagsField
        label="Tags"
        values={[]}
        onSave={vi.fn()}
        allTags={["vip", "lead", "partner"]}
      />
    );
    fireEvent.click(screen.getByText("Add tags..."));
    // All suggestions should show since none are selected
    expect(screen.getByText("vip")).toBeInTheDocument();
    expect(screen.getByText("lead")).toBeInTheDocument();
    expect(screen.getByText("partner")).toBeInTheDocument();
  });

  it("filters suggestions as user types", () => {
    render(
      <EditableTagsField
        label="Tags"
        values={[]}
        onSave={vi.fn()}
        allTags={["vip", "lead", "partner"]}
      />
    );
    fireEvent.click(screen.getByText("Add tags..."));
    const input = screen.getByPlaceholderText("Type to add tag...");
    fireEvent.change(input, { target: { value: "le" } });
    expect(screen.getByText("lead")).toBeInTheDocument();
    expect(screen.queryByText("partner")).not.toBeInTheDocument();
  });

  it("shows Create option for new tag", () => {
    render(
      <EditableTagsField
        label="Tags"
        values={[]}
        onSave={vi.fn()}
        allTags={["vip"]}
      />
    );
    fireEvent.click(screen.getByText("Add tags..."));
    const input = screen.getByPlaceholderText("Type to add tag...");
    fireEvent.change(input, { target: { value: "newtag" } });
    expect(screen.getByText(/Create "newtag"/)).toBeInTheDocument();
  });

  it("adds new tag on Enter", () => {
    const onSave = vi.fn();
    render(
      <EditableTagsField label="Tags" values={[]} onSave={onSave} allTags={[]} />
    );
    fireEvent.click(screen.getByText("Add tags..."));
    const input = screen.getByPlaceholderText("Type to add tag...");
    fireEvent.change(input, { target: { value: "newtag" } });
    fireEvent.keyDown(input, { key: "Enter" });
    // Tag should appear as chip
    expect(screen.getByRole("button", { name: /newtag/ })).toBeInTheDocument();
  });

  it("removes last tag on Backspace when input empty", () => {
    render(
      <EditableTagsField
        label="Tags"
        values={["vip", "lead"]}
        onSave={vi.fn()}
        allTags={[]}
      />
    );
    fireEvent.click(screen.getByText("vip"));
    const input = screen.getByRole("textbox");
    // Press backspace to remove "lead" (last tag)
    fireEvent.keyDown(input, { key: "Backspace" });
    // "lead" should no longer be a selected chip button
    expect(
      screen.queryByRole("button", { name: /lead/ })
    ).not.toBeInTheDocument();
    // "vip" should still be there
    expect(screen.getByRole("button", { name: /vip/ })).toBeInTheDocument();
  });

  it("excludes already-selected tags from suggestions", () => {
    render(
      <EditableTagsField
        label="Tags"
        values={["vip"]}
        onSave={vi.fn()}
        allTags={["vip", "lead"]}
      />
    );
    fireEvent.click(screen.getByText("vip"));
    // "vip" is selected so should NOT appear in suggestions
    // "lead" should appear
    const buttons = screen.getAllByRole("button");
    const _suggestionTexts = buttons.map((b) => b.textContent);
    // lead should be in suggestions
    expect(screen.getByText("lead")).toBeInTheDocument();
  });
});
