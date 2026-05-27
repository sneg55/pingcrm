"use client";

import Link from "next/link";
import { ArchiveRestore, ChevronLeft, ChevronRight } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { ContactAvatar } from "@/components/contact-avatar";
import { ScorePill } from "./ScorePill";

interface ContactItem {
  id: string;
  full_name?: string | null;
  emails: string[];
  avatar_url?: string | null;
  company?: string | null;
  relationship_score: number;
  last_interaction_at?: string | null;
}

interface PaginationMeta {
  page: number;
  total_pages: number;
  total: number;
}

interface ArchivedContactsTableProps {
  contacts: ContactItem[];
  meta: PaginationMeta | undefined;
  selected: Set<string>;
  allSelected: boolean;
  someSelected: boolean;
  isPending: boolean;
  onToggleSelectAll: () => void;
  onToggleSelect: (id: string) => void;
  onUnarchive: (id: string) => void;
  onPageChange: (page: number) => void;
}

export function ArchivedContactsTable({
  contacts,
  meta,
  selected,
  allSelected,
  someSelected,
  isPending,
  onToggleSelectAll,
  onToggleSelect,
  onUnarchive,
  onPageChange,
}: ArchivedContactsTableProps) {
  const totalPages = meta?.total_pages ?? 1;
  const currentPage = meta?.page ?? 1;

  const pageNumbers: Array<number | "..."> = [];
  for (let i = 1; i <= totalPages; i++) {
    if (i <= 3 || i > totalPages - 2 || Math.abs(i - currentPage) <= 1) {
      pageNumbers.push(i);
    } else if (pageNumbers[pageNumbers.length - 1] !== "...") {
      pageNumbers.push("...");
    }
  }

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 overflow-hidden">
      {/* Header row */}
      <div className="grid grid-cols-[40px_1fr_140px_100px_140px_140px] gap-2 px-4 py-3 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 items-center">
        <div>
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => { if (el) el.indeterminate = someSelected; }}
            onChange={onToggleSelectAll}
            className="w-3.5 h-3.5 rounded border-stone-300 dark:border-stone-600 text-teal-600 cursor-pointer"
          />
        </div>
        <div className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider">Name</div>
        <div className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider">Company</div>
        <div className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider text-center">Score</div>
        <div className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider">Last Interaction</div>
        <div className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider">Actions</div>
      </div>

      {/* Rows */}
      {contacts.map((c) => {
        const displayName = c.full_name || c.emails?.[0] || "Unnamed";
        return (
          <div
            key={c.id}
            className="grid grid-cols-[40px_1fr_140px_100px_140px_140px] gap-2 px-4 py-3.5 border-b border-stone-100 dark:border-stone-800 items-center hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
          >
            <div>
              <input
                type="checkbox"
                checked={selected.has(c.id)}
                onChange={() => onToggleSelect(c.id)}
                className="w-3.5 h-3.5 rounded border-stone-300 dark:border-stone-600 text-teal-600 cursor-pointer"
              />
            </div>
            <div className="flex items-center gap-3 min-w-0">
              <ContactAvatar avatarUrl={c.avatar_url} name={displayName} size="sm" />
              <div className="min-w-0">
                <Link
                  href={`/contacts/${c.id}`}
                  className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate block hover:text-teal-700 dark:hover:text-teal-400 transition-colors"
                >
                  {displayName}
                </Link>
                {c.emails?.[0] && c.full_name && (
                  <p className="text-xs text-stone-400 dark:text-stone-500 truncate">{c.emails[0]}</p>
                )}
              </div>
            </div>
            <div className="text-xs text-stone-600 dark:text-stone-300 truncate">{c.company || "—"}</div>
            <div className="text-center">
              <ScorePill score={c.relationship_score} />
            </div>
            <div className="text-xs text-stone-500 dark:text-stone-400">
              {c.last_interaction_at
                ? formatDistanceToNow(new Date(c.last_interaction_at), { addSuffix: true })
                : "Never"}
            </div>
            <div>
              <button
                onClick={() => onUnarchive(c.id)}
                disabled={isPending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:border-teal-300 hover:text-teal-700 dark:hover:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 disabled:opacity-50 transition-colors"
              >
                <ArchiveRestore className="w-3.5 h-3.5" />
                Unarchive
              </button>
            </div>
          </div>
        );
      })}

      {/* Pagination */}
      {meta && totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-800">
          <p className="text-xs text-stone-500 dark:text-stone-400 font-mono">
            Page <strong className="text-stone-700 dark:text-stone-300">{currentPage}</strong> of {totalPages} — <strong className="text-stone-700 dark:text-stone-300">{meta.total}</strong> archived contacts
          </p>
          <div className="flex items-center gap-2">
            <button
              disabled={currentPage <= 1}
              onClick={() => onPageChange(currentPage - 1)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-stone-200 dark:border-stone-700 text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-700 dark:hover:text-stone-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Previous
            </button>
            <div className="flex items-center gap-1">
              {pageNumbers.map((p, i) =>
                p === "..." ? (
                  <span key={`ellipsis-${i}`} className="w-7 h-7 flex items-center justify-center text-xs text-stone-400 dark:text-stone-500">...</span>
                ) : (
                  <button
                    key={p}
                    onClick={() => onPageChange(p as number)}
                    className={cn(
                      "w-7 h-7 rounded-md text-xs font-medium transition-colors",
                      p === currentPage
                        ? "bg-teal-600 text-white"
                        : "text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800"
                    )}
                  >
                    {p}
                  </button>
                )
              )}
            </div>
            <button
              disabled={currentPage >= totalPages}
              onClick={() => onPageChange(currentPage + 1)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-700 dark:hover:text-stone-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
