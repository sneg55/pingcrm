"use client";

import type { ActivityData } from "@/hooks/use-contacts";

const dimensionConfig = [
  { key: "reciprocity" as const, label: "Reciprocity", max: 4 },
  { key: "recency" as const, label: "Recency", max: 3 },
  { key: "frequency" as const, label: "Frequency", max: 2 },
  { key: "breadth" as const, label: "Breadth", max: 1 },
];

const platformColors: Record<string, string> = {
  email: "bg-teal-500",
  telegram: "bg-sky-500",
  twitter: "bg-slate-700",
  linkedin: "bg-blue-600",
  manual: "bg-stone-400",
  meeting: "bg-violet-500",
};

export function ActivityBreakdown({ data }: { data: ActivityData }) {
  const { dimensions, stats, monthly_trend } = data;
  const maxTrend = Math.max(...monthly_trend.map((m) => m.count), 1);

  return (
    <div className="bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 p-4 space-y-4">
      <p className="text-xs font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider">
        Activity Breakdown
      </p>

      {/* Score Dimensions */}
      <div className="space-y-2">
        {dimensionConfig.map(({ key, label, max }) => {
          const value = dimensions[key].value;
          return (
            <div key={key} className="flex items-center gap-2">
              <span className="text-xs text-stone-500 dark:text-stone-400 w-20 text-right">{label}</span>
              <div className="flex-1 flex gap-0.5">
                {Array.from({ length: max }).map((_, i) => (
                  <div
                    key={i}
                    className={`h-2.5 flex-1 rounded-sm ${
                      i < value ? "bg-emerald-500" : "bg-stone-200 dark:bg-stone-700"
                    }`}
                  />
                ))}
              </div>
              <span className="text-xs font-mono-data text-stone-400 dark:text-stone-500 w-8">
                {value}/{max}
              </span>
            </div>
          );
        })}
      </div>

      {/* Activity Stats */}
      <div className="pt-3 border-t border-stone-100 dark:border-stone-800 space-y-2">
        {/* Inbound/Outbound bar */}
        {(stats.inbound_365d > 0 || stats.outbound_365d > 0) && (
          <div>
            <div className="flex items-center justify-between text-xs text-stone-500 dark:text-stone-400 mb-1">
              <span>{stats.inbound_365d} in</span>
              <span>{stats.outbound_365d} out</span>
            </div>
            <div className="flex h-2 rounded-full overflow-hidden bg-stone-100 dark:bg-stone-800">
              {stats.inbound_365d > 0 && (
                <div
                  className="bg-teal-500 h-full"
                  style={{
                    width: `${(stats.inbound_365d / (stats.inbound_365d + stats.outbound_365d)) * 100}%`,
                  }}
                />
              )}
              {stats.outbound_365d > 0 && (
                <div
                  className="bg-stone-400 h-full"
                  style={{
                    width: `${(stats.outbound_365d / (stats.inbound_365d + stats.outbound_365d)) * 100}%`,
                  }}
                />
              )}
            </div>
          </div>
        )}

        {/* Platform chips */}
        {stats.platforms.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {stats.platforms.map((p) => (
              <span
                key={p}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-300"
              >
                <span className={`w-1.5 h-1.5 rounded-full ${platformColors[p] ?? "bg-stone-400"}`} />
                {p}
              </span>
            ))}
          </div>
        )}

        <p className="text-xs text-stone-400 dark:text-stone-500">
          <span className="font-mono-data text-stone-600 dark:text-stone-300">{stats.interaction_count}</span> total interactions
        </p>
      </div>

      {/* 6-Month Trend */}
      {monthly_trend.length > 0 && (
        <div className="pt-3 border-t border-stone-100 dark:border-stone-800">
          <div className="flex items-end gap-1 h-16">
            {monthly_trend.map((m) => (
              <div key={m.month} className="flex-1 flex flex-col items-center gap-1">
                <div className="w-full flex items-end justify-center" style={{ height: "48px" }}>
                  <div
                    className="w-full max-w-[24px] bg-teal-400 rounded-t-sm"
                    style={{ height: `${(m.count / maxTrend) * 100}%`, minHeight: m.count > 0 ? "4px" : "0px" }}
                  />
                </div>
                <span className="text-[10px] text-stone-400 dark:text-stone-500 font-mono-data">{m.count}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-1 mt-0.5">
            {monthly_trend.map((m) => (
              <div key={m.month} className="flex-1 text-center">
                <span className="text-[10px] text-stone-400 dark:text-stone-500">
                  {new Date(`${m.month  }-01`).toLocaleString("en", { month: "short" })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ActivityBreakdownSkeleton() {
  return (
    <div className="bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 p-4 space-y-4 animate-pulse">
      <div className="h-3 w-32 bg-stone-200 dark:bg-stone-700 rounded" />
      <div className="space-y-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="h-3 w-20 bg-stone-100 dark:bg-stone-800 rounded" />
            <div className="flex-1 h-2.5 bg-stone-100 dark:bg-stone-800 rounded" />
          </div>
        ))}
      </div>
      <div className="h-16 bg-stone-100 dark:bg-stone-800 rounded" />
    </div>
  );
}
