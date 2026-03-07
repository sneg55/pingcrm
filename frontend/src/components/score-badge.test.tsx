import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ScoreBadge } from "./score-badge";

describe("ScoreBadge", () => {
  it("renders Strong for score >= 8", () => {
    render(<ScoreBadge score={9} />);
    expect(screen.getByText("Strong (9)")).toBeInTheDocument();
  });

  it("renders Active for score 4-7", () => {
    render(<ScoreBadge score={5} />);
    expect(screen.getByText("Active (5)")).toBeInTheDocument();
  });

  it("renders Dormant for score <= 3", () => {
    render(<ScoreBadge score={2} />);
    expect(screen.getByText("Dormant (2)")).toBeInTheDocument();
  });

  it("renders Strong at boundary score 8", () => {
    render(<ScoreBadge score={8} />);
    expect(screen.getByText("Strong (8)")).toBeInTheDocument();
  });

  it("renders Active at boundary score 4", () => {
    render(<ScoreBadge score={4} />);
    expect(screen.getByText("Active (4)")).toBeInTheDocument();
  });

  it("renders Dormant at boundary score 3", () => {
    render(<ScoreBadge score={3} />);
    expect(screen.getByText("Dormant (3)")).toBeInTheDocument();
  });

  it("renders Dormant for score 0", () => {
    render(<ScoreBadge score={0} />);
    expect(screen.getByText("Dormant (0)")).toBeInTheDocument();
  });

  it("renders Strong for score 10", () => {
    render(<ScoreBadge score={10} />);
    expect(screen.getByText("Strong (10)")).toBeInTheDocument();
  });

  it("shows score in title attribute", () => {
    render(<ScoreBadge score={7} />);
    expect(screen.getByTitle("Relationship score: 7/10")).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(<ScoreBadge score={5} className="text-lg" />);
    expect(container.firstChild).toHaveClass("text-lg");
  });
});
