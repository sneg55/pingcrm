"use client";

export function ScorePill({ score }: { score: number | null | undefined }) {
  const s = score ?? 0;
  if (s >= 70) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
        <span className="font-mono">{Math.round(s / 10)}</span> Strong
      </span>
    );
  }
  if (s >= 30) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
        <span className="font-mono">{Math.round(s / 10)}</span> Warm
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
      <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
      <span className="font-mono">{Math.round(s / 10)}</span> Cold
    </span>
  );
}
