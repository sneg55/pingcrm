"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, Clock, X } from "lucide-react";
import { useUpdateSuggestion } from "@/hooks/use-suggestions";

interface SuggestionActionsProps {
  suggestionId: string;
}

export function SuggestionActions({ suggestionId }: SuggestionActionsProps) {
  const updateSuggestion = useUpdateSuggestion();
  const [showSnooze, setShowSnooze] = useState(false);
  const snoozeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showSnooze) return;
    const handler = (e: MouseEvent) => {
      if (snoozeRef.current && !snoozeRef.current.contains(e.target as Node)) {
        setShowSnooze(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSnooze]);

  const handleSnooze = (days: number) => {
    const date = new Date();
    date.setDate(date.getDate() + days);
    updateSuggestion.mutate({
      id: suggestionId,
      input: { status: "snoozed", snooze_until: date.toISOString() },
    });
    setShowSnooze(false);
  };

  const handleDismiss = () => {
    updateSuggestion.mutate({
      id: suggestionId,
      input: { status: "dismissed" },
    });
  };

  return (
    <div className="flex items-center gap-2 mt-2 pt-2 border-t border-stone-100 dark:border-stone-800">
      <div className="relative" ref={snoozeRef}>
        <button
          onClick={() => setShowSnooze(!showSnooze)}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950 transition-colors"
        >
          <Clock className="w-3 h-3" /> Snooze <ChevronDown className="w-2.5 h-2.5" />
        </button>
        {showSnooze && (
          <div className="menu-enter absolute left-0 bottom-full mb-1 w-32 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg py-1 z-50">
            <button
              onClick={() => handleSnooze(14)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
            >
              <Clock className="w-3 h-3 text-stone-400 dark:text-stone-500" /> 2 weeks
            </button>
            <button
              onClick={() => handleSnooze(30)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
            >
              <Clock className="w-3 h-3 text-stone-400 dark:text-stone-500" /> 1 month
            </button>
            <button
              onClick={() => handleSnooze(90)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
            >
              <Clock className="w-3 h-3 text-stone-400 dark:text-stone-500" /> 3 months
            </button>
          </div>
        )}
      </div>
      <button
        onClick={handleDismiss}
        className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md text-stone-400 dark:text-stone-500 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
      >
        <X className="w-3 h-3" /> Dismiss
      </button>
    </div>
  );
}
