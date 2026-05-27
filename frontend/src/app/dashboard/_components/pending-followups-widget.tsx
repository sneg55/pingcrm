"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";
import { type Suggestion } from "@/hooks/use-suggestions";
import { DashboardSuggestionCard } from "./suggestion-card";

interface Props {
  isLoading: boolean;
  pendingSuggestions: Suggestion[];
}

export function PendingFollowUpsWidget({ isLoading, pendingSuggestions }: Props) {
  return (
    <div className="animate-in stagger-2">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-display font-semibold text-stone-900 dark:text-stone-100">
          Pending Follow-ups
        </h2>
        <Link
          href="/suggestions"
          className="text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300"
        >
          View all &rarr;
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-20 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 shimmer"
            />
          ))}
        </div>
      ) : pendingSuggestions.length === 0 ? (
        <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-8 text-center">
          <Sparkles className="w-8 h-8 text-stone-200 dark:text-stone-700 mx-auto mb-2" />
          <p className="text-sm text-stone-400 dark:text-stone-500">
            No pending suggestions.{" "}
            <Link
              href="/suggestions"
              className="text-teal-600 dark:text-teal-400 hover:underline"
            >
              Generate suggestions
            </Link>
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {pendingSuggestions.map((s) => (
            <DashboardSuggestionCard key={s.id} suggestion={s} />
          ))}
        </div>
      )}
    </div>
  );
}
