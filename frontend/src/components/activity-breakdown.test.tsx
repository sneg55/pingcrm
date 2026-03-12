import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ActivityBreakdown, ActivityBreakdownSkeleton } from "./activity-breakdown";
import type { ActivityData } from "@/hooks/use-contacts";

function makeData(overrides?: Partial<ActivityData>): ActivityData {
  return {
    score: 7,
    dimensions: {
      reciprocity: { value: 3, max: 4 },
      recency: { value: 2, max: 3 },
      frequency: { value: 1, max: 2 },
      breadth: { value: 1, max: 1 },
    },
    stats: {
      inbound_365d: 10,
      outbound_365d: 5,
      count_30d: 3,
      count_90d: 8,
      platforms: ["email", "telegram"],
      interaction_count: 42,
    },
    monthly_trend: [
      { month: "2026-01", count: 4 },
      { month: "2026-02", count: 2 },
      { month: "2026-03", count: 6 },
    ],
    ...overrides,
  };
}

describe("ActivityBreakdown", () => {
  describe("score dimensions", () => {
    it("renders all four dimension labels", () => {
      render(<ActivityBreakdown data={makeData()} />);
      expect(screen.getByText("Reciprocity")).toBeInTheDocument();
      expect(screen.getByText("Recency")).toBeInTheDocument();
      expect(screen.getByText("Frequency")).toBeInTheDocument();
      expect(screen.getByText("Breadth")).toBeInTheDocument();
    });

    it("renders value/max text for each dimension", () => {
      render(<ActivityBreakdown data={makeData()} />);
      expect(screen.getByText("3/4")).toBeInTheDocument();
      expect(screen.getByText("2/3")).toBeInTheDocument();
      expect(screen.getByText("1/2")).toBeInTheDocument();
      expect(screen.getByText("1/1")).toBeInTheDocument();
    });

    it("fills bars with emerald color for scored segments", () => {
      const { container } = render(<ActivityBreakdown data={makeData()} />);
      const filledBars = container.querySelectorAll(".bg-emerald-500");
      // reciprocity=3 + recency=2 + frequency=1 + breadth=1 = 7 filled
      expect(filledBars.length).toBe(7);
    });

    it("fills unfilled segments with stone color", () => {
      const { container } = render(<ActivityBreakdown data={makeData()} />);
      const emptyBars = container.querySelectorAll(".bg-stone-200");
      // reciprocity has 1 empty, recency has 1 empty, frequency has 1 empty, breadth has 0
      expect(emptyBars.length).toBe(3);
    });

    it("shows all bars filled when dimension value equals max", () => {
      const data = makeData({
        dimensions: {
          reciprocity: { value: 4, max: 4 },
          recency: { value: 3, max: 3 },
          frequency: { value: 2, max: 2 },
          breadth: { value: 1, max: 1 },
        },
      });
      const { container } = render(<ActivityBreakdown data={data} />);
      const filledBars = container.querySelectorAll(".bg-emerald-500");
      expect(filledBars.length).toBe(10);
      const emptyBars = container.querySelectorAll(".bg-stone-200");
      expect(emptyBars.length).toBe(0);
    });

    it("shows no filled bars when all dimension values are zero", () => {
      const data = makeData({
        dimensions: {
          reciprocity: { value: 0, max: 4 },
          recency: { value: 0, max: 3 },
          frequency: { value: 0, max: 2 },
          breadth: { value: 0, max: 1 },
        },
      });
      const { container } = render(<ActivityBreakdown data={data} />);
      const filledBars = container.querySelectorAll(".bg-emerald-500");
      expect(filledBars.length).toBe(0);
    });
  });

  describe("stats section", () => {
    it("shows inbound and outbound counts", () => {
      render(<ActivityBreakdown data={makeData()} />);
      expect(screen.getByText("10 in")).toBeInTheDocument();
      expect(screen.getByText("5 out")).toBeInTheDocument();
    });

    it("shows total interaction count", () => {
      render(<ActivityBreakdown data={makeData()} />);
      expect(screen.getByText("42")).toBeInTheDocument();
      expect(screen.getByText(/total interactions/)).toBeInTheDocument();
    });

    it("renders platform chips for each platform", () => {
      render(<ActivityBreakdown data={makeData()} />);
      expect(screen.getByText("email")).toBeInTheDocument();
      expect(screen.getByText("telegram")).toBeInTheDocument();
    });

    it("applies correct color for known platforms", () => {
      const { container } = render(<ActivityBreakdown data={makeData()} />);
      const emailDot = container.querySelector(".bg-teal-500");
      const telegramDot = container.querySelector(".bg-sky-500");
      expect(emailDot).toBeInTheDocument();
      expect(telegramDot).toBeInTheDocument();
    });

    it("shows inbound/outbound bar when either stat is nonzero", () => {
      const { container } = render(<ActivityBreakdown data={makeData()} />);
      const inboundBar = container.querySelector(".bg-teal-500.h-full");
      const outboundBar = container.querySelector(".bg-stone-400.h-full");
      expect(inboundBar).toBeInTheDocument();
      expect(outboundBar).toBeInTheDocument();
    });

    it("hides inbound/outbound bar when both are zero", () => {
      const data = makeData({
        stats: {
          inbound_365d: 0,
          outbound_365d: 0,
          count_30d: 0,
          count_90d: 0,
          platforms: [],
          interaction_count: 0,
        },
      });
      render(<ActivityBreakdown data={data} />);
      expect(screen.queryByText("0 in")).not.toBeInTheDocument();
      expect(screen.queryByText("0 out")).not.toBeInTheDocument();
    });
  });

  describe("handles zero/empty data gracefully", () => {
    it("renders with zero interaction count", () => {
      const data = makeData({
        stats: {
          inbound_365d: 0,
          outbound_365d: 0,
          count_30d: 0,
          count_90d: 0,
          platforms: [],
          interaction_count: 0,
        },
      });
      render(<ActivityBreakdown data={data} />);
      expect(screen.getByText("0")).toBeInTheDocument();
      expect(screen.getByText(/total interactions/)).toBeInTheDocument();
    });

    it("renders with no platforms without crashing", () => {
      const data = makeData({
        stats: {
          inbound_365d: 5,
          outbound_365d: 3,
          count_30d: 2,
          count_90d: 4,
          platforms: [],
          interaction_count: 8,
        },
      });
      render(<ActivityBreakdown data={data} />);
      expect(screen.queryByText("email")).not.toBeInTheDocument();
      expect(screen.getByText(/total interactions/)).toBeInTheDocument();
    });

    it("renders with empty monthly trend without crashing", () => {
      const data = makeData({ monthly_trend: [] });
      render(<ActivityBreakdown data={data} />);
      expect(screen.getByText("Activity Breakdown")).toBeInTheDocument();
    });

    it("applies fallback color for unknown platform", () => {
      const data = makeData({
        stats: {
          inbound_365d: 1,
          outbound_365d: 0,
          count_30d: 1,
          count_90d: 1,
          platforms: ["fax"],
          interaction_count: 1,
        },
      });
      const { container } = render(<ActivityBreakdown data={data} />);
      expect(screen.getByText("fax")).toBeInTheDocument();
      // Unknown platform falls back to bg-stone-400 dot
      const dots = container.querySelectorAll(".w-1\\.5.h-1\\.5.rounded-full.bg-stone-400");
      expect(dots.length).toBeGreaterThan(0);
    });
  });

  describe("monthly trend", () => {
    it("renders a bar for each month in trend data", () => {
      render(<ActivityBreakdown data={makeData()} />);
      // monthly_trend has 3 items with counts 4, 2, 6
      expect(screen.getByText("4")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("6")).toBeInTheDocument();
    });

    it("renders one month label per trend entry", () => {
      const { container } = render(<ActivityBreakdown data={makeData()} />);
      // Month labels are rendered in the bottom row of the trend section as text-[10px] spans
      const monthLabels = container.querySelectorAll(
        ".flex.gap-1.mt-0\\.5 span"
      );
      expect(monthLabels.length).toBe(3);
      // Each label should be a 3-letter abbreviation
      monthLabels.forEach((label) => {
        expect(label.textContent).toMatch(/^[A-Z][a-z]{2}$/);
      });
    });

    it("does not render trend section when monthly_trend is empty", () => {
      render(<ActivityBreakdown data={makeData({ monthly_trend: [] })} />);
      // No month abbreviations present
      expect(screen.queryByText("Jan")).not.toBeInTheDocument();
    });

    it("handles single-month trend without crashing", () => {
      const data = makeData({ monthly_trend: [{ month: "2026-03", count: 10 }] });
      const { container } = render(<ActivityBreakdown data={data} />);
      expect(screen.getByText("10")).toBeInTheDocument();
      // One month label rendered as a 3-letter abbreviation
      const monthLabels = container.querySelectorAll(".flex.gap-1.mt-0\\.5 span");
      expect(monthLabels.length).toBe(1);
      expect(monthLabels[0].textContent).toMatch(/^[A-Z][a-z]{2}$/);
    });

    it("handles all-zero counts in trend data without crashing", () => {
      const data = makeData({
        monthly_trend: [
          { month: "2026-01", count: 0 },
          { month: "2026-02", count: 0 },
        ],
      });
      render(<ActivityBreakdown data={data} />);
      // Two "0" labels rendered
      const zeros = screen.getAllByText("0");
      expect(zeros.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe("section header", () => {
    it("renders the Activity Breakdown heading", () => {
      render(<ActivityBreakdown data={makeData()} />);
      expect(screen.getByText("Activity Breakdown")).toBeInTheDocument();
    });
  });
});

describe("ActivityBreakdownSkeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<ActivityBreakdownSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("has animate-pulse class for loading state", () => {
    const { container } = render(<ActivityBreakdownSkeleton />);
    expect(container.firstChild).toHaveClass("animate-pulse");
  });

  it("renders four skeleton dimension rows", () => {
    const { container } = render(<ActivityBreakdownSkeleton />);
    // Each row has a label placeholder and a bar placeholder
    const rows = container.querySelectorAll(".flex.items-center.gap-2");
    expect(rows.length).toBe(4);
  });
});
