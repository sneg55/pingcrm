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
} from "lucide-react";
import { useContacts, useUpdateContact } from "@/hooks/use-contacts";
import { ArchivedContactsTable } from "./_components/ArchivedContactsTable";

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
      updateUrl({ q: searchInput.trim() || null });
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
          <ArchivedContactsTable
            contacts={contacts}
            meta={meta}
            selected={selected}
            allSelected={allSelected}
            someSelected={someSelected}
            isPending={updateContact.isPending}
            onToggleSelectAll={toggleSelectAll}
            onToggleSelect={toggleSelect}
            onUnarchive={handleUnarchive}
            onPageChange={(page) => updateUrl({ page: String(page) })}
          />
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
