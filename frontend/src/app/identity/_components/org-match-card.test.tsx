import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { OrgMatchCard } from "./org-match-card";
import type { OrgIdentityMatch } from "@/hooks/use-org-identity";

const match: OrgIdentityMatch = {
  id: "m1",
  match_score: 0.72,
  match_method: "probabilistic",
  status: "pending_review",
  created_at: "2026-05-13T00:00:00Z",
  org_a: {
    id: "a", name: "Anthropic", domain: "anthropic.com",
    logo_url: null, linkedin_url: null, website: null, twitter_handle: null,
    contact_count: 12,
  },
  org_b: {
    id: "b", name: "Anthropic, Inc.", domain: null,
    logo_url: null, linkedin_url: null, website: null, twitter_handle: null,
    contact_count: 3,
  },
};

describe("OrgMatchCard", () => {
  it("renders both org names", () => {
    render(<OrgMatchCard match={match} onMerge={vi.fn()} onReject={vi.fn()} merging={false} rejecting={false} />);
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    expect(screen.getByText("Anthropic, Inc.")).toBeInTheDocument();
  });

  it("merge button labels target as the org with more contacts", () => {
    render(<OrgMatchCard match={match} onMerge={vi.fn()} onReject={vi.fn()} merging={false} rejecting={false} />);
    expect(screen.getByText(/Merge into Anthropic/)).toBeInTheDocument();
  });

  it("calls onMerge with the target id when merge button clicked", () => {
    const onMerge = vi.fn();
    render(<OrgMatchCard match={match} onMerge={onMerge} onReject={vi.fn()} merging={false} rejecting={false} />);
    fireEvent.click(screen.getByText(/Merge into Anthropic/));
    expect(onMerge).toHaveBeenCalledWith("a");
  });

  it("calls onReject when 'Not the same' clicked", () => {
    const onReject = vi.fn();
    render(<OrgMatchCard match={match} onMerge={vi.fn()} onReject={onReject} merging={false} rejecting={false} />);
    fireEvent.click(screen.getByText(/Not the same/));
    expect(onReject).toHaveBeenCalled();
  });

  it("shows breakdown rows when match detail toggled", () => {
    render(<OrgMatchCard match={match} onMerge={vi.fn()} onReject={vi.fn()} merging={false} rejecting={false} />);
    fireEvent.click(screen.getByText(/Match detail/));
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Domain")).toBeInTheDocument();
    expect(screen.getByText("LinkedIn")).toBeInTheDocument();
  });
});
