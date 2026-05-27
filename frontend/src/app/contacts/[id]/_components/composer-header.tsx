"use client";

import { ChevronDown, Sparkles, Send } from "lucide-react";

interface ComposerHeaderProps {
  hasSuggestion: boolean;
  expanded: boolean;
  sent: string | null;
  suggestedMessage?: string;
  onClick: () => void;
}

export function ComposerHeader({
  hasSuggestion,
  expanded,
  sent,
  suggestedMessage,
  onClick,
}: ComposerHeaderProps) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
    >
      {hasSuggestion ? (
        <div className="w-8 h-8 rounded-full bg-amber-50 dark:bg-amber-950 flex items-center justify-center shrink-0 mt-0.5">
          <Sparkles className="w-4 h-4 text-amber-500" />
        </div>
      ) : (
        <Send className="w-4 h-4 text-teal-500 shrink-0 mt-0.5" />
      )}
      <div className="flex-1 min-w-0">
        {sent ? (
          <span className="text-sm text-green-600 font-medium">{sent}</span>
        ) : hasSuggestion ? (
          <span className="text-sm text-stone-700 dark:text-stone-300 line-clamp-1">
            <span className="font-medium text-stone-900 dark:text-stone-100">Follow-up suggested</span>
            {!expanded && suggestedMessage && (
              <span className="text-stone-400 dark:text-stone-500">
                {" "}
                — {suggestedMessage.slice(0, 60)}...
              </span>
            )}
          </span>
        ) : (
          <span className="text-sm text-stone-500 dark:text-stone-400">Write a message...</span>
        )}
      </div>
      <ChevronDown
        className={`w-4 h-4 text-stone-400 dark:text-stone-500 shrink-0 mt-0.5 transition-transform ${
          expanded ? "rotate-180" : ""
        }`}
      />
    </button>
  );
}
