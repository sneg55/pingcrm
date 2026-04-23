"use client";

import Link from "next/link";
import type { components } from "@/lib/api-types";

type Pin = components["schemas"]["ContactMapPin"];

export function MapSidebar({
  pins,
  totalInBounds,
  onHover,
  selectedId,
}: {
  pins: Pin[];
  totalInBounds: number;
  onHover: (id: string | null) => void;
  selectedId: string | null;
}) {
  return (
    <aside className="w-80 border-l border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 overflow-y-auto">
      <div className="p-3 text-xs text-stone-500 dark:text-stone-400 border-b border-stone-200 dark:border-stone-800">
        {totalInBounds > pins.length
          ? `Showing ${pins.length} of ${totalInBounds} — zoom in for more`
          : `${pins.length} contact${pins.length === 1 ? "" : "s"} in view`}
      </div>
      <ul>
        {pins.map((p) => (
          <li
            key={p.id}
            onMouseEnter={() => onHover(p.id)}
            onMouseLeave={() => onHover(null)}
            className={`px-3 py-2 border-b border-stone-100 dark:border-stone-800 hover:bg-stone-50 dark:hover:bg-stone-800 ${
              selectedId === p.id ? "bg-teal-50 dark:bg-teal-950/40" : ""
            }`}
          >
            <Link href={`/contacts/${p.id}`} className="flex items-center gap-2">
              {p.avatar_url ? (
                <img src={p.avatar_url} alt="" className="w-8 h-8 rounded-full" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-stone-200 dark:bg-stone-700" />
              )}
              <div className="flex-1 min-w-0">
                <div className="truncate font-medium text-stone-900 dark:text-stone-100">
                  {p.full_name ?? "Unnamed"}
                </div>
                <div className="text-xs text-stone-500 dark:text-stone-400">
                  Score {p.relationship_score}
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}
