"use client";

import { Suspense, useState, useEffect, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Search,
  Archive,
  ArrowLeft,
  ArchiveRestore,
  X,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useContacts, useUpdateContact } from "@/hooks/use-contacts";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { ContactAvatar } from "@/components/contact-avatar";

/* ── Score badge ── */
function ScorePill({ score }: { score: number | null | undefined }) {
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

/* ═══════════════ PAGE ═══════════════ */

export default function ArchivedContactsPage() {
  return (
    <Suspense fallback={<div className="max-w-6xl mx-auto px-4 py-8"><div className="h-8 w-48 bg-stone-100 dark:bg-stone-800 rounded animate-pulse" /></div>}>
      <ArchivedContactsInner />
    </Suspense>
  );
}

function ArchivedContactsInner() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const pageParam = Number(searchParams.get("page")) || 1;
  const searchParam = searchParams.get("q") ?? "";
  const [searchInput, setSearchInput] = useState(searchParam);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data, isLoading, isError } = useContacts({
    page: pageParam,
    page_size: 20,
    search: searchParam || undefined,
    archived_only: true,
    sort: "created",
  });

  const updateContact = useUpdateContact();

  const updateUrl = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, val] of Object.entries(updates)) {
        if (val) params.set(key, val);
        else params.delete(key);
      }
      if ("q" in updates) params.delete("page");
      const qs = params.toString();
      router.replace(qs ? `/contacts/archive?${qs}` : "/contacts/archive", { scroll: false });
    },
    [searchParams, router],
  );

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      updateUrl({ q: searchInput || null });
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput, updateUrl]);

  // Clear selection on page/data change
  useEffect(() => {
    setSelected(new Set());
  }, [data]);

  const contacts = data?.data ?? [];
  const meta = data?.meta;

  const handleUnarchive = (contactId: string) => {
    updateContact.mutate({ id: contactId, input: { priority_level: "medium" } });
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === contacts.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(contacts.map((c) => c.id)));
    }
  };

  const bulkUnarchive = () => {
    for (const id of selected) {
      updateContact.mutate({ id, input: { priority_level: "medium" } });
    }
    setSelected(new Set());
  };

  const allSelected = contacts.length > 0 && selected.size === contacts.length;
  const someSelected = selected.size > 0 && !allSelected;

  /* Pagination helpers */
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
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Back link */}
        <Link
          href="/contacts"
          className="inline-flex items-center gap-1.5 text-sm text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-100 transition-colors mb-4 group"
        >
          <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          Back to Contacts
        </Link>

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-stone-100 dark:bg-stone-800 flex items-center justify-center">
            <Archive className="w-5 h-5 text-stone-500 dark:text-stone-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100 leading-tight">Archived Contacts</h1>
            <p className="text-sm text-stone-500 dark:text-stone-400 mt-0.5">Contacts you&apos;ve archived from your active network</p>
          </div>
          {meta && (
            <span className="ml-2 inline-flex items-center px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-300 border border-stone-200 dark:border-stone-700">
              {meta.total} contacts
            </span>
          )}
        </div>

        {/* Search bar */}
        <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-4 mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400 dark:text-stone-500" />
            <input
              type="text"
              placeholder="Search archived contacts..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 text-sm rounded-lg border border-stone-200 dark:border-stone-700 focus:outline-none focus:ring-2 focus:ring-teal-400 placeholder:text-stone-400 dark:placeholder:text-stone-500 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100"
            />
          </div>
        </div>

        {/* Content */}
        {isLoading ? (
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 overflow-hidden">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-14 border-b border-stone-100 dark:border-stone-800 animate-pulse" />
            ))}
          </div>
        ) : isError ? (
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-6 text-center">
            <p className="text-sm text-red-600 dark:text-red-400">Failed to load archived contacts.</p>
          </div>
        ) : contacts.length === 0 ? (
          /* Empty state */
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-12 text-center">
            <div className="w-14 h-14 rounded-full bg-stone-100 dark:bg-stone-800 flex items-center justify-center mx-auto mb-4">
              <Archive className="w-7 h-7 text-stone-400 dark:text-stone-500" />
            </div>
            <h3 className="text-base font-bold text-stone-900 dark:text-stone-100 mb-1">No archived contacts</h3>
            <p className="text-sm text-stone-500 dark:text-stone-400 max-w-sm mx-auto">
              Contacts you archive will appear here. Archive contacts to keep your active list focused.
            </p>
          </div>
        ) : (
          /* Table */
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 overflow-hidden">
            {/* Header row */}
            <div className="grid grid-cols-[40px_1fr_140px_100px_140px_140px] gap-2 px-4 py-3 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 items-center">
              <div>
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => { if (el) el.indeterminate = someSelected; }}
                  onChange={toggleSelectAll}
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
                      onChange={() => toggleSelect(c.id)}
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
                      onClick={() => handleUnarchive(c.id)}
                      disabled={updateContact.isPending}
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
                    onClick={() => updateUrl({ page: String(currentPage - 1) })}
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
                          onClick={() => updateUrl({ page: String(p) })}
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
                    onClick={() => updateUrl({ page: String(currentPage + 1) })}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-700 dark:hover:text-stone-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Next <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Bulk actions bar */}
      {selected.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-3 bg-stone-900 text-white rounded-xl px-4 py-3 shadow-2xl border border-stone-700">
            <span className="text-sm font-medium">{selected.size} selected</span>
            <div className="w-px h-5 bg-stone-600" />
            <button
              onClick={bulkUnarchive}
              disabled={updateContact.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-teal-600 hover:bg-teal-500 text-white transition-colors disabled:opacity-50"
            >
              <ArchiveRestore className="w-3.5 h-3.5" />
              Unarchive All
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="p-1 text-stone-400 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
