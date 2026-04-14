"use client";

import Link from "next/link";
import type { components } from "@/lib/api-types";

type Pin = components["schemas"]["ContactMapPin"];

export function ContactPinPopover({
  pin,
  onClose,
}: {
  pin: Pin;
  onClose: () => void;
}) {
  return (
    <div className="bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-lg shadow-lg p-3 min-w-[220px] text-sm">
      <div className="flex items-center gap-2 mb-2">
        {pin.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={pin.avatar_url} alt="" className="w-8 h-8 rounded-full" />
        ) : (
          <div className="w-8 h-8 rounded-full bg-stone-200 dark:bg-stone-700" />
        )}
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate text-stone-900 dark:text-stone-100">
            {pin.full_name ?? "Unnamed"}
          </div>
          <div className="text-xs text-stone-500 dark:text-stone-400">
            Score {pin.relationship_score}
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className="text-stone-400 hover:text-stone-700 dark:hover:text-stone-200"
        >
          ×
        </button>
      </div>
      <Link
        href={`/contacts/${pin.id}`}
        className="text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700"
      >
        Open contact →
      </Link>
    </div>
  );
}
