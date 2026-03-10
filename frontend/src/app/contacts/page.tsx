"use client";

import { Suspense, useCallback, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Search, Plus, X, Filter, Tag, Archive, CheckSquare, GitMerge, ArrowUp, ArrowDown } from "lucide-react";
import { useContacts } from "@/hooks/use-contacts";
import { ScoreBadge } from "@/components/score-badge";
import { ContactAvatar } from "@/components/contact-avatar";
import { formatDistanceToNow } from "date-fns";
import { client } from "@/lib/api-client";

const scoreTierLabels: Record<string, string> = {
  strong: "Strong (8+)",
  active: "Warm (4-7)",
  dormant: "Cold (0-3)",
};

const sourceLabels: Record<string, string> = {
  google: "Google",
  gmail: "Gmail",
  google_calendar: "Calendar",
  csv: "CSV Import",
  linkedin: "LinkedIn",
  telegram: "Telegram",
  twitter: "Twitter",
  manual: "Manual",
};

function BulkActionBar({
  selectedCount,
  allTags,
  onAddTag,
  onRemoveTag,
  onSetPriority,
  onMerge,
  onClear,
  isPending,
}: {
  selectedCount: number;
  allTags: string[];
  onAddTag: (tag: string) => void;
  onRemoveTag: (tag: string) => void;
  onSetPriority: (level: string) => void;
  onMerge: () => void;
  onClear: () => void;
  isPending: boolean;
}) {
  const [tagInput, setTagInput] = useState("");
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const [tagMode, setTagMode] = useState<"add" | "remove">("add");

  const filteredTags = allTags.filter(
    (t) => !tagInput || t.toLowerCase().includes(tagInput.toLowerCase())
  );

  return (
    <div className="sticky top-14 z-30 bg-teal-600 text-white px-4 py-2.5 rounded-lg mb-4 flex items-center gap-3 shadow-lg">
      <div className="flex items-center gap-2 flex-shrink-0">
        <CheckSquare className="w-4 h-4" />
        <span className="text-sm font-medium font-mono-data">{selectedCount}</span>
        <span className="text-sm">selected</span>
      </div>

      <div className="h-5 w-px bg-teal-400" />

      {/* Tag actions */}
      <div className="relative">
        <div className="flex items-center gap-1">
          <button
            onClick={() => { setTagMode("add"); setShowTagDropdown((v) => !v); }}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-teal-500 hover:bg-teal-400 transition-colors"
          >
            <Tag className="w-3 h-3" />
            Add Tag
          </button>
          <button
            onClick={() => { setTagMode("remove"); setShowTagDropdown((v) => !v); }}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-teal-500 hover:bg-teal-400 transition-colors"
          >
            <X className="w-3 h-3" />
            Remove Tag
          </button>
        </div>

        {showTagDropdown && (
          <div className="absolute left-0 top-full mt-1 w-56 bg-white rounded-lg border border-stone-200 shadow-lg z-50 p-2">
            <input
              type="text"
              placeholder={tagMode === "add" ? "Type tag name..." : "Select tag to remove..."}
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && tagInput.trim() && tagMode === "add") {
                  onAddTag(tagInput.trim());
                  setTagInput("");
                  setShowTagDropdown(false);
                }
              }}
              className="w-full px-2.5 py-1.5 text-sm text-stone-900 rounded-md border border-stone-300 focus:outline-none focus:ring-2 focus:ring-teal-400 mb-1"
              autoFocus
            />
            <div className="max-h-32 overflow-y-auto">
              {filteredTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => {
                    if (tagMode === "add") onAddTag(tag);
                    else onRemoveTag(tag);
                    setTagInput("");
                    setShowTagDropdown(false);
                  }}
                  className="w-full text-left px-2.5 py-1.5 text-sm text-stone-700 hover:bg-stone-100 rounded-md"
                >
                  {tagMode === "add" ? "+" : "-"} {tag}
                </button>
              ))}
              {tagMode === "add" && tagInput.trim() && !allTags.includes(tagInput.trim()) && (
                <button
                  onClick={() => {
                    onAddTag(tagInput.trim());
                    setTagInput("");
                    setShowTagDropdown(false);
                  }}
                  className="w-full text-left px-2.5 py-1.5 text-sm text-teal-600 hover:bg-teal-50 rounded-md font-medium"
                >
                  + Create &quot;{tagInput.trim()}&quot;
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="h-5 w-px bg-teal-400" />

      {/* Priority actions */}
      <button
        onClick={() => onSetPriority("archived")}
        disabled={isPending}
        className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-teal-500 hover:bg-teal-400 transition-colors disabled:opacity-50"
      >
        <Archive className="w-3 h-3" />
        Archive All
      </button>

      {selectedCount >= 2 && (
        <>
          <div className="h-5 w-px bg-teal-400" />
          <button
            onClick={onMerge}
            disabled={isPending}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-teal-500 hover:bg-teal-400 transition-colors disabled:opacity-50"
          >
            <GitMerge className="w-3 h-3" />
            Merge
          </button>
        </>
      )}

      <div className="flex-1" />

      <button
        onClick={onClear}
        className="text-xs text-teal-200 hover:text-white underline"
      >
        Clear selection
      </button>
    </div>
  );
}

function ContactsPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();

  // Read all filters from URL search params
  const searchFromUrl = searchParams.get("q") ?? "";
  const [searchInput, setSearchInput] = useState(searchFromUrl);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const search = searchFromUrl;
  const page = Number(searchParams.get("page") ?? "1");
  const scoreFilter = searchParams.get("score") ?? undefined;
  const tagFilter = searchParams.get("tag") ?? "";
  const sourceFilter = searchParams.get("source") ?? "";
  const dateFrom = searchParams.get("date_from") ?? "";
  const dateTo = searchParams.get("date_to") ?? "";
  const sortParam = searchParams.get("sort") ?? "score";
  const hasInteractions = searchParams.get("has_interactions") === "true" ? true : undefined;
  const interactionDays = searchParams.get("interaction_days") ? Number(searchParams.get("interaction_days")) : undefined;
  const hasBirthday = searchParams.get("has_birthday") === "true" ? true : undefined;
  const showFilters = searchParams.get("filters") === "1";

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Helper to update URL params without full page reload
  const setParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value) {
          params.set(key, value);
        } else {
          params.delete(key);
        }
      }
      // Reset page to 1 when any filter changes (unless page itself is being set)
      if (!("page" in updates)) {
        params.delete("page");
      }
      router.replace(`/contacts?${params.toString()}`, { scroll: false });
    },
    [searchParams, router]
  );

  const { data: allTags = [] } = useQuery({
    queryKey: ["tags"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/tags");
      return (data?.data as string[]) ?? [];
    },
  });

  const activeFilterCount = [tagFilter, sourceFilter, dateFrom, dateTo, scoreFilter].filter(Boolean).length;

  const priorityFilter = searchParams.get("priority") || undefined;
  const { data, isLoading, isError } = useContacts({
    search: search || undefined,
    page,
    page_size: 20,
    score: scoreFilter,
    priority: priorityFilter,
    tag: tagFilter || undefined,
    source: sourceFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    has_interactions: hasInteractions,
    interaction_days: interactionDays,
    has_birthday: hasBirthday,
    sort: sortParam,
  });

  const contacts = data?.data ?? [];
  const meta = data?.meta;

  // Bulk update mutation
  const bulkUpdate = useMutation({
    mutationFn: async (body: {
      contact_ids: string[];
      add_tags?: string[];
      remove_tags?: string[];
      priority_level?: string;
    }) => {
      const { data, error } = await client.POST("/api/v1/contacts/bulk-update" as any, {
        body,
      });
      if (error) throw new Error((error as { detail?: string })?.detail ?? "Bulk update failed");
      return data;
    },
    onSuccess: () => {
      setSelectedIds(new Set());
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
      void queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });

  // Merge mutation: chain-merge all selected into the first one
  const mergeMutation = useMutation({
    mutationFn: async (contactIds: string[]) => {
      const [primaryId, ...otherIds] = contactIds;
      for (const otherId of otherIds) {
        await client.POST("/api/v1/contacts/{contact_id}/merge/{other_id}" as any, {
          params: { path: { contact_id: primaryId, other_id: otherId } },
        });
      }
    },
    onSuccess: () => {
      setSelectedIds(new Set());
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === contacts.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(contacts.map((c) => c.id)));
    }
  };

  const selectedArray = Array.from(selectedIds);

  return (
    <div className="min-h-screen bg-stone-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-display font-bold text-stone-900">Contacts</h1>
            {meta && (
              <p className="text-sm text-stone-500 mt-0.5">
                <span className="font-mono-data">{meta.total}</span> total contacts
              </p>
            )}
          </div>
          <Link
            href="/contacts/new"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 transition-colors btn-press"
          >
            <Plus className="w-4 h-4" />
            Add Contact
          </Link>
        </div>

        {/* Priority quick-filter chips */}
        <div className="flex items-center gap-2 mb-3">
          {[
            { key: "high", label: "High", icon: "🔥", color: "bg-red-50 text-red-700 border-red-200 hover:bg-red-100" },
            { key: "medium", label: "Medium", icon: "⚡", color: "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100" },
            { key: "low", label: "Low", icon: "💤", color: "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100" },
          ].map(({ key, label, icon, color }) => {
            const priorityParam = searchParams.get("priority");
            const isActive = priorityParam === key;
            return (
              <button
                key={key}
                onClick={() => setParams({ priority: isActive ? undefined : key })}
                className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                  isActive
                    ? color + " ring-1 ring-offset-1 ring-current"
                    : "bg-white border-stone-200 text-stone-500 hover:bg-stone-50"
                }`}
              >
                <span className="text-xs">{icon}</span>
                {label}
              </button>
            );
          })}
          {["strong", "active", "dormant"].map((tier) => {
            const isActive = scoreFilter === tier;
            const config = {
              strong: { label: "Strong", color: "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100" },
              active: { label: "Warm", color: "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100" },
              dormant: { label: "Cold", color: "bg-red-50 text-red-700 border-red-200 hover:bg-red-100" },
            }[tier]!;
            return (
              <button
                key={tier}
                onClick={() => setParams({ score: isActive ? undefined : tier })}
                className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                  isActive
                    ? config.color + " ring-1 ring-offset-1 ring-current"
                    : "bg-white border-stone-200 text-stone-500 hover:bg-stone-50"
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                {config.label}
              </button>
            );
          })}
        </div>

        <div className="flex gap-2 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
            <input
              type="text"
              placeholder="Search by name, company, or email..."
              value={searchInput}
              onChange={(e) => {
                const value = e.target.value;
                setSearchInput(value);
                if (debounceRef.current) clearTimeout(debounceRef.current);
                debounceRef.current = setTimeout(() => {
                  setParams({ q: value || undefined });
                }, 300);
              }}
              className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-stone-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
          <button
            onClick={() => setParams({ filters: showFilters ? undefined : "1", page: String(page) })}
            className={`inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
              showFilters || activeFilterCount > 0
                ? "bg-teal-50 border-teal-300 text-teal-700"
                : "bg-white border-stone-300 text-stone-600 hover:bg-stone-50"
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {activeFilterCount > 0 && (
              <span className="ml-0.5 inline-flex items-center justify-center w-5 h-5 text-xs rounded-full bg-teal-600 text-white font-mono-data">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {showFilters && (
          <div className="mb-4 p-4 bg-white rounded-lg border border-stone-200 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label htmlFor="filter-tag" className="block text-xs font-medium text-stone-500 mb-1">Tag</label>
              <select
                id="filter-tag"
                value={tagFilter}
                onChange={(e) => setParams({ tag: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-stone-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
              >
                <option value="">All tags</option>
                {allTags.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="filter-source" className="block text-xs font-medium text-stone-500 mb-1">Source</label>
              <select
                id="filter-source"
                value={sourceFilter}
                onChange={(e) => setParams({ source: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-stone-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
              >
                <option value="">All sources</option>
                {Object.entries(sourceLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="filter-from" className="block text-xs font-medium text-stone-500 mb-1">From</label>
              <input
                id="filter-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setParams({ date_from: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-stone-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </div>
            <div>
              <label htmlFor="filter-to" className="block text-xs font-medium text-stone-500 mb-1">To</label>
              <input
                id="filter-to"
                type="date"
                value={dateTo}
                onChange={(e) => setParams({ date_to: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-stone-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </div>
          </div>
        )}

        {activeFilterCount > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-4">
            {scoreFilter && scoreTierLabels[scoreFilter] && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full bg-teal-50 text-teal-700 border border-teal-200">
                Score: {scoreTierLabels[scoreFilter]}
                <button onClick={() => setParams({ score: undefined })} className="ml-0.5 hover:text-teal-900">
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {tagFilter && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                Tag: {tagFilter}
                <button onClick={() => setParams({ tag: undefined })} className="ml-0.5 hover:text-emerald-900">
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {sourceFilter && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full bg-violet-50 text-violet-700 border border-violet-200">
                Source: {sourceLabels[sourceFilter] ?? sourceFilter}
                <button onClick={() => setParams({ source: undefined })} className="ml-0.5 hover:text-violet-900">
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {(dateFrom || dateTo) && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                Date: {dateFrom || "..."} — {dateTo || "..."}
                <button onClick={() => setParams({ date_from: undefined, date_to: undefined })} className="ml-0.5 hover:text-amber-900">
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            <button
              onClick={() => {
                router.replace("/contacts", { scroll: false });
              }}
              className="text-xs text-stone-500 hover:text-stone-700 underline"
            >
              Clear all
            </button>
          </div>
        )}

        {/* Bulk action bar */}
        {selectedIds.size > 0 && (
          <BulkActionBar
            selectedCount={selectedIds.size}
            allTags={allTags}
            isPending={bulkUpdate.isPending || mergeMutation.isPending}
            onAddTag={(tag) =>
              bulkUpdate.mutate({ contact_ids: selectedArray, add_tags: [tag] })
            }
            onRemoveTag={(tag) =>
              bulkUpdate.mutate({ contact_ids: selectedArray, remove_tags: [tag] })
            }
            onSetPriority={(level) =>
              bulkUpdate.mutate({ contact_ids: selectedArray, priority_level: level })
            }
            onMerge={() => {
              if (selectedArray.length >= 2 && confirm(`Merge ${selectedArray.length} contacts into one? This cannot be undone.`)) {
                mergeMutation.mutate(selectedArray);
              }
            }}
            onClear={() => setSelectedIds(new Set())}
          />
        )}

        {isLoading && (
          <div className="bg-white rounded-lg border border-stone-200 overflow-hidden">
            <div className="bg-stone-50 border-b border-stone-200 h-11" />
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-stone-100">
                <div className="w-4 h-4 rounded bg-stone-100 animate-pulse" />
                <div className="w-7 h-7 rounded-full bg-stone-100 animate-pulse" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3.5 w-32 bg-stone-100 rounded animate-pulse" />
                </div>
                <div className="h-3.5 w-24 bg-stone-100 rounded animate-pulse" />
                <div className="h-5 w-20 bg-stone-100 rounded-full animate-pulse" />
                <div className="h-3.5 w-20 bg-stone-100 rounded animate-pulse" />
              </div>
            ))}
          </div>
        )}

        {isError && (
          <div className="text-center py-12 text-red-500">
            Failed to load contacts. Is the backend running?
          </div>
        )}

        {!isLoading && !isError && contacts.length === 0 && (
          <div className="text-center py-12 text-stone-400">
            No contacts found.
          </div>
        )}

        {contacts.length > 0 && (
          <div className="bg-white rounded-lg border border-stone-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-stone-50 border-b border-stone-200">
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={contacts.length > 0 && selectedIds.size === contacts.length}
                      onChange={toggleSelectAll}
                      className="w-4 h-4 rounded border-stone-300 text-teal-600 focus:ring-teal-500"
                      aria-label="Select all contacts"
                    />
                  </th>
                  <th
                    className="text-left px-4 py-3 font-medium text-stone-600 cursor-pointer select-none hover:text-stone-900"
                    onClick={() => setParams({ sort: sortParam === "created" ? "score" : "created" })}
                  >
                    <span className="inline-flex items-center gap-1">
                      Name
                      {sortParam === "created" && <ArrowDown className="w-3 h-3 text-teal-600" />}
                    </span>
                  </th>
                  <th
                    className="text-left px-4 py-3 font-medium text-stone-600 cursor-pointer select-none hover:text-stone-900"
                    onClick={() => setParams({ sort: sortParam === "company" ? "score" : "company" })}
                  >
                    <span className="inline-flex items-center gap-1">
                      Company
                      {sortParam === "company" && <ArrowDown className="w-3 h-3 text-teal-600" />}
                    </span>
                  </th>
                  <th
                    className="text-left px-4 py-3 font-medium text-stone-600 cursor-pointer select-none hover:text-stone-900"
                    onClick={() => setParams({ sort: sortParam === "score" ? "created" : "score" })}
                  >
                    <span className="inline-flex items-center gap-1">
                      Score
                      {sortParam === "score" && <ArrowDown className="w-3 h-3 text-teal-600" />}
                    </span>
                  </th>
                  <th
                    className="text-right px-4 py-3 font-medium text-stone-600 w-20 cursor-pointer select-none hover:text-stone-900"
                    onClick={() => setParams({ sort: sortParam === "activity" ? "score" : "activity" })}
                  >
                    <span className="inline-flex items-center gap-1">
                      Activity
                      {sortParam === "activity" && <ArrowDown className="w-3 h-3 text-teal-600" />}
                    </span>
                  </th>
                  <th
                    className="text-left px-4 py-3 font-medium text-stone-600 cursor-pointer select-none hover:text-stone-900"
                    onClick={() => setParams({ sort: sortParam === "interaction" ? "score" : "interaction" })}
                  >
                    <span className="inline-flex items-center gap-1">
                      Last Interaction
                      {sortParam === "interaction" && <ArrowDown className="w-3 h-3 text-teal-600" />}
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {contacts.map((contact) => {
                  const name =
                    contact.full_name ??
                    [contact.given_name, contact.family_name].filter(Boolean).join(" ") ??
                    "Unnamed";
                  const isSelected = selectedIds.has(contact.id);
                  return (
                    <tr
                      key={contact.id}
                      className={`transition-colors ${isSelected ? "bg-teal-50" : "hover:bg-stone-50"}`}
                    >
                      <td className="w-10 px-4 py-3">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(contact.id)}
                          className="w-4 h-4 rounded border-stone-300 text-teal-600 focus:ring-teal-500"
                          aria-label={`Select ${name}`}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/contacts/${contact.id}`}
                          className="flex items-center gap-2 text-teal-700 hover:text-teal-900 font-medium"
                        >
                          <ContactAvatar
                            avatarUrl={contact.avatar_url}
                            name={name}
                            size="xs"
                          />
                          {name}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-stone-600">
                        {contact.company || <span className="text-stone-300">&mdash;</span>}
                      </td>
                      <td className="px-4 py-3">
                        <ScoreBadge score={contact.relationship_score} lastInteractionAt={contact.last_interaction_at} />
                      </td>
                      <td className="px-4 py-3 text-right font-mono-data text-stone-500">
                        {(contact as any).interaction_count ?? 0}
                      </td>
                      <td className="px-4 py-3 text-stone-500">
                        {contact.last_interaction_at
                          ? formatDistanceToNow(new Date(contact.last_interaction_at), {
                              addSuffix: true,
                            })
                          : "Never"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {meta && meta.total_pages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <button
              disabled={page <= 1}
              onClick={() => setParams({ page: String(page - 1) })}
              className="px-3 py-1.5 text-sm rounded-md border border-stone-300 disabled:opacity-40 hover:bg-stone-100 btn-press"
            >
              Previous
            </button>
            <span className="text-sm text-stone-500">
              Page <span className="font-mono-data">{page}</span> of <span className="font-mono-data">{meta.total_pages}</span>
            </span>
            <button
              disabled={page >= meta.total_pages}
              onClick={() => setParams({ page: String(page + 1) })}
              className="px-3 py-1.5 text-sm rounded-md border border-stone-300 disabled:opacity-40 hover:bg-stone-100 btn-press"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ContactsPageLoading() {
  return (
    <div className="min-h-screen bg-stone-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="h-8 w-32 bg-stone-200 rounded animate-pulse mb-6" />
        <div className="bg-white rounded-lg border border-stone-200 overflow-hidden">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-stone-100">
              <div className="w-7 h-7 rounded-full bg-stone-100 animate-pulse" />
              <div className="flex-1 h-4 bg-stone-100 rounded animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ContactsPage() {
  return (
    <Suspense fallback={<ContactsPageLoading />}>
      <ContactsPageContent />
    </Suspense>
  );
}
