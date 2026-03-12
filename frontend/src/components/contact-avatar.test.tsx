import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ContactAvatar } from "./contact-avatar";

describe("ContactAvatar", () => {
  // --- image rendering ---

  it("renders an img element when avatarUrl is provided", () => {
    render(<ContactAvatar avatarUrl="https://example.com/photo.jpg" name="Alice Smith" />);
    const img = screen.getByRole("img");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", "https://example.com/photo.jpg");
    expect(img).toHaveAttribute("alt", "Alice Smith");
  });

  // --- initials fallback ---

  it("renders initials fallback when avatarUrl is null", () => {
    render(<ContactAvatar avatarUrl={null} name="Alice Smith" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("AS")).toBeInTheDocument();
  });

  it("renders initials fallback when avatarUrl is undefined", () => {
    render(<ContactAvatar avatarUrl={undefined} name="Bob Jones" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("BJ")).toBeInTheDocument();
  });

  // --- initials derivation ---

  it("uses first letter of first name and first letter of last name", () => {
    render(<ContactAvatar avatarUrl={null} name="Carlos Rivera" />);
    expect(screen.getByText("CR")).toBeInTheDocument();
  });

  it("uses first and last word when name has more than two words", () => {
    render(<ContactAvatar avatarUrl={null} name="Mary Anne Johnson" />);
    // first word[0] = M, last word[0] = J
    expect(screen.getByText("MJ")).toBeInTheDocument();
  });

  // --- incomplete name fallback ---

  it("renders a single uppercase letter when name is a single word", () => {
    render(<ContactAvatar avatarUrl={null} name="Madonna" />);
    expect(screen.getByText("M")).toBeInTheDocument();
  });

  it("renders '?' when name is an empty string", () => {
    render(<ContactAvatar avatarUrl={null} name="" />);
    expect(screen.getByText("?")).toBeInTheDocument();
  });

  it("renders '?' when name is only whitespace", () => {
    render(<ContactAvatar avatarUrl={null} name="   " />);
    expect(screen.getByText("?")).toBeInTheDocument();
  });

  // --- size classes ---

  it("applies xs size classes by default when size is xs", () => {
    const { container } = render(<ContactAvatar avatarUrl={null} name="Ann Brown" size="xs" />);
    expect(container.firstChild).toHaveClass("w-6", "h-6", "text-[10px]");
  });

  it("applies sm size classes when size is sm", () => {
    const { container } = render(<ContactAvatar avatarUrl={null} name="Ann Brown" size="sm" />);
    expect(container.firstChild).toHaveClass("w-8", "h-8", "text-xs");
  });

  it("applies md size classes when size is md (default)", () => {
    const { container } = render(<ContactAvatar avatarUrl={null} name="Ann Brown" />);
    expect(container.firstChild).toHaveClass("w-10", "h-10", "text-sm");
  });

  it("applies lg size classes when size is lg", () => {
    const { container } = render(<ContactAvatar avatarUrl={null} name="Ann Brown" size="lg" />);
    expect(container.firstChild).toHaveClass("w-14", "h-14", "text-lg");
  });

  it("applies size classes to img element when avatarUrl is present", () => {
    render(<ContactAvatar avatarUrl="https://example.com/photo.jpg" name="Ann Brown" size="lg" />);
    const img = screen.getByRole("img");
    expect(img).toHaveClass("w-14", "h-14", "text-lg");
  });

  // --- score ring colors ---

  it("applies emerald ring for score >= 8", () => {
    const { container } = render(<ContactAvatar avatarUrl={null} name="Ann Brown" score={9} />);
    expect(container.firstChild).toHaveClass("ring-emerald-400");
  });

  it("applies amber ring for score 4–7", () => {
    const { container } = render(<ContactAvatar avatarUrl={null} name="Ann Brown" score={5} />);
    expect(container.firstChild).toHaveClass("ring-amber-400");
  });

  it("applies red ring for score < 4", () => {
    const { container } = render(<ContactAvatar avatarUrl={null} name="Ann Brown" score={2} />);
    expect(container.firstChild).toHaveClass("ring-red-300");
  });

  it("applies no ring classes when score is not provided", () => {
    const { container } = render(<ContactAvatar avatarUrl={null} name="Ann Brown" />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).not.toMatch(/ring-emerald|ring-amber|ring-red/);
  });

  // --- custom className forwarding ---

  it("forwards custom className to the root element", () => {
    const { container } = render(
      <ContactAvatar avatarUrl={null} name="Ann Brown" className="my-custom-class" />
    );
    expect(container.firstChild).toHaveClass("my-custom-class");
  });
});
