"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

import { useVersion } from "@/hooks/use-version";

const DISMISS_KEY = "pingcrm.dismissed_version";

export function VersionBanner() {
  const { data } = useVersion();
  const [expanded, setExpanded] = useState(false);
  const [dismissedTick, setDismissedTick] = useState(0);

  if (!data || data.update_available !== true || !data.latest) {
    return null;
  }

  const dismissed =
    typeof window !== "undefined"
      ? localStorage.getItem(DISMISS_KEY)
      : null;
  void dismissedTick;
  if (dismissed === data.latest) {
    return null;
  }

  const handleDismiss = () => {
    localStorage.setItem(DISMISS_KEY, data.latest!);
    setDismissedTick((n) => n + 1);
  };

  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 dark:border-amber-900/40 dark:bg-amber-950/30">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">
          🎉 PingCRM {data.latest} is available
        </span>
        <span className="text-stone-600 dark:text-stone-400">
          (you&apos;re on {data.current})
        </span>
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="text-stone-700 underline-offset-2 hover:underline dark:text-stone-300"
          aria-label={expanded ? "Hide release notes" : "Show release notes"}
        >
          {expanded ? "▲ Hide release notes" : "▼ Show release notes"}
        </button>
        {data.release_url && (
          <a
            href={data.release_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-stone-700 underline-offset-2 hover:underline dark:text-stone-300"
          >
            View on GitHub →
          </a>
        )}
        <button
          type="button"
          onClick={handleDismiss}
          className="ml-2 text-stone-500 hover:text-stone-800 dark:text-stone-400 dark:hover:text-stone-100"
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
      {expanded && data.release_notes && (
        <div className="prose prose-sm mx-auto mt-2 max-w-6xl border-t border-amber-200/60 pt-2 text-sm dark:prose-invert dark:border-amber-900/40">
          <Markdown rehypePlugins={[rehypeSanitize]}>
            {data.release_notes}
          </Markdown>
        </div>
      )}
    </div>
  );
}
