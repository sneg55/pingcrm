"use client";

import { GitMerge, X } from "lucide-react";
import { cn } from "@/lib/utils";

/* ── DuplicateMatchBadge ── */

export function DuplicateMatchBadge({ score }: { score: number }) {
  const label =
    score >= 85 ? "Strong match" : score >= 65 ? "Probable match" : "Possible match";
  const badgeCls =
    score >= 85
      ? "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800"
      : score >= 65
      ? "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
      : "bg-sky-50 dark:bg-sky-950 text-sky-700 dark:text-sky-400 border-sky-200 dark:border-sky-800";
  const barCls =
    score >= 85 ? "bg-emerald-500" : score >= 65 ? "bg-amber-400" : "bg-sky-400";

  return (
    <div className="flex items-center justify-between px-3 py-2 bg-stone-50 dark:bg-stone-800 border-b border-stone-100 dark:border-stone-700">
      <span
        className={cn(
          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border",
          badgeCls
        )}
      >
        {label}
      </span>
      <div className="flex items-center gap-1.5">
        <div className="w-12 h-1.5 bg-stone-200 dark:bg-stone-700 rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full", barCls)}
            style={{ width: `${score}%` }}
          />
        </div>
        <span className="font-mono text-xs font-bold text-stone-600 dark:text-stone-300">
          {score}%
        </span>
      </div>
    </div>
  );
}

/* ── DuplicateMergeActions ── */

export function DuplicateMergeActions({
  dupId,
  confirmId,
  dismissing,
  merging,
  onConfirmMerge,
  onCancelConfirm,
  onDismiss,
  onRequestConfirm,
}: {
  dupId: string;
  confirmId: string | null;
  dismissing: boolean;
  merging: boolean;
  onConfirmMerge: () => void;
  onCancelConfirm: () => void;
  onDismiss: () => void;
  onRequestConfirm: () => void;
}) {
  if (confirmId === dupId) {
    return (
      <div className="flex items-center gap-2">
        <button
          onClick={onConfirmMerge}
          disabled={merging}
          className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors"
        >
          {merging ? "Merging..." : "Confirm merge"}
        </button>
        <button
          onClick={onCancelConfirm}
          className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={onDismiss}
        disabled={dismissing}
        className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50 transition-colors"
      >
        <X className="w-3 h-3" /> {dismissing ? "Dismissing..." : "Not the same"}
      </button>
      <button
        onClick={onRequestConfirm}
        className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 transition-colors"
      >
        <GitMerge className="w-3 h-3" /> Merge
      </button>
    </div>
  );
}
