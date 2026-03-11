"use client";

export const dynamic = "force-dynamic";

import { Suspense, useCallback, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  Search,
  Plus,
  X,
  SlidersHorizontal,
  Tag,
  Archive,
  CheckSquare,
  GitMerge,
  Trash2,
  ArrowUpDown,
  ArrowDown,
  Mail,
  MessageCircle,
  Twitter,
  SearchX,
} from "lucide-react";
import { useContacts } from "@/hooks/use-contacts";
import { ScoreBadge } from "@/components/score-badge";
import { ContactAvatar } from "@/components/contact-avatar";
import { formatDistanceToNow } from "date-fns";
import { client } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const priorityConfig = [
  { key: "high", label: "High", icon: "\uD83D\uDD25", activeColor: "bg-red-50 text-red-700 border-red-200 ring-1 ring-red-300 ring-offset-1" },
  { key: "medium", label: "Medium", icon: "\u26A1", activeColor: "bg-amber-50 text-amber-700 border-amber-200 ring-1 ring-amber-300 ring-offset-1" },
  { key: "low", label: "Low", icon: "\uD83D\uDCA4", activeColor: "bg-blue-50 text-blue-700 border-blue-200 ring-1 ring-blue-300 ring-offset-1" },
] as const;

const scoreConfig = [
  { key: "strong", label: "Strong", dotColor: "bg-emerald-500", activeColor: "bg-emerald-50 text-emerald-700 border-emerald-200 ring-1 ring-emerald-300 ring-offset-1" },
  { key: "active", label: "Warm", dotColor: "bg-amber-400", activeColor: "bg-amber-50 text-amber-700 border-amber-200 ring-1 ring-amber-300 ring-offset-1" },
  { key: "dormant", label: "Cold", dotColor: "bg-red-400", activeColor: "bg-red-50 text-red-700 border-red-200 ring-1 ring-red-300 ring-offset-1" },
] as const;

const datePresets = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "3mo", days: 90 },
  { label: "6mo", days: 180 },
  { label: "12mo", days: 365 },
] as const;

const sortColumns = [
  { key: "name", label: "Contact" },
  { key: "company", label: "Company" },
  { key: "score", label: "Score" },
  { key: "priority", label: "Priority" },
  { key: "activity", label: "Activity" },
  { key: "interaction", label: "Last" },
] as const;

// ---------------------------------------------------------------------------
// Score number badge
// ---------------------------------------------------------------------------

function ScoreNumberBadge({ score }: { score: number }) {
  let color = "bg-sky-50 text-sky-700 border-sky-100";
  let dotColor = "bg-sky-400";
  if (score >= 8) { color = "bg-emerald-50 text-emerald-700 border-emerald-100"; dotColor = "bg-emerald-500"; }
  else if (score >= 4) { color = "bg-amber-50 text-amber-700 border-amber-100"; dotColor = "bg-amber-400"; }
  else if (score >= 1) { color = "bg-red-50 text-red-700 border-red-100"; dotColor = "bg-red-400"; }

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      <span className="font-mono-data">{score}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Priority badge
// ---------------------------------------------------------------------------

function PriorityBadge({ level }: { level: string }) {
  const icons: Record<string, string> = { high: "\uD83D\uDD25", medium: "\u26A1", low: "\uD83D\uDCA4" };
  const icon = icons[level];
  if (!icon) return <span className="text-stone-300">&mdash;</span>;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-50 text-red-700 border border-red-100">
      {icon}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Platform icons for contact row
// ---------------------------------------------------------------------------

function PlatformIcons({ emails, telegram, twitter }: { emails: string[]; telegram: string | null; twitter: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {emails.length > 0 && <Mail className="w-3 h-3 text-red-400" title="Email" />}
      {telegram && <MessageCircle className="w-3 h-3 text-sky-400" title="Telegram" />}
      {twitter && <Twitter className="w-3 h-3 text-stone-400" title="Twitter/X" />}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Days-ago label
// ---------------------------------------------------------------------------

function DaysAgo({ dateStr }: { dateStr: string | null }) {
  if (!dateStr) return <span className="text-stone-300">&mdash;</span>;
  const days = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
  const isOverdue = days > 30;
  return (
    <span className={`font-mono-data text-xs ${isOverdue ? "font-medium text-red-500" : "text-stone-500"}`}>
      {days}d
    </span>
  );
}

// ---------------------------------------------------------------------------
// Bulk Action Bar
// ---------------------------------------------------------------------------

function BulkActionBar({
  selectedCount,
  allTags,
  onAddTag,
  onRemoveTag,
  onArchive,
  onDelete,
  onMerge,
  onClear,
  isPending,
}: {
  selectedCount: number;
  allTags: string[];
  onAddTag: (tag: string) => void;
  onRemoveTag: (tag: string) => void;
  onArchive: () => void;
  onDelete: () => void;
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
    <div className="sticky bottom-4 z-30 mx-auto w-fit bg-stone-900 text-white rounded-xl shadow-2xl px-5 py-3 flex items-center gap-4">
      <span className="text-sm font-medium">
        <span className="font-mono-data">{selectedCount}</span> selected
      </span>
      <div className="w-px h-5 bg-stone-700" />

      {/* Tag actions */}
      <div className="relative">
        <div className="flex items-center gap-1">
          <button
            onClick={() => { setTagMode("add"); setShowTagDropdown((v) => !v); }}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
          >
            <Tag className="w-3.5 h-3.5" /> Add Tag
          </button>
          <button
            onClick={() => { setTagMode("remove"); setShowTagDropdown((v) => !v); }}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
          >
            <X className="w-3.5 h-3.5" /> Remove Tag
          </button>
        </div>
        {showTagDropdown && (
          <div className="absolute left-0 bottom-full mb-1 w-56 bg-white rounded-lg border border-stone-200 shadow-lg z-50 p-2">
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

      {selectedCount >= 2 && (
        <>
          <button
            onClick={onMerge}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
          >
            <GitMerge className="w-3.5 h-3.5" /> Merge
          </button>
        </>
      )}

      <button
        onClick={onArchive}
        disabled={isPending}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
      >
        <Archive className="w-3.5 h-3.5" /> Archive
      </button>

      <button
        onClick={onDelete}
        disabled={isPending}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-red-600 hover:bg-red-700 transition-colors disabled:opacity-50"
      >
        <Trash2 className="w-3.5 h-3.5" /> Delete
      </button>

      <button
        onClick={onClear}
        className="p-1.5 rounded-lg hover:bg-stone-700 text-stone-400 transition-colors ml-1"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pagination with numbered pages
// ---------------------------------------------------------------------------

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPageChange: (p: number) => void;
}) {
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  // Build page numbers to show
  const pages: (number | "...")[] = [];
  if (totalPages <= 5) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (page > 3) pages.push("...");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) pages.push(i);
    if (page < totalPages - 2) pages.push("...");
    pages.push(totalPages);
  }

  return (
    <div className="flex items-center justify-between mt-4">
      <p className="text-xs text-stone-500">
        Showing <strong>{from}-{to}</strong> of <strong>{total}</strong>
      </p>
      <div className="flex items-center gap-1.5">
        <button
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 disabled:text-stone-300 disabled:bg-stone-50 disabled:cursor-not-allowed transition-colors"
        >
          Previous
        </button>
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`dots-${i}`} className="text-xs text-stone-400 px-1">...</span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p)}
              className={`px-2.5 py-1.5 text-xs font-medium rounded-lg min-w-[32px] text-center transition-colors ${
                p === page
                  ? "bg-teal-600 text-white"
                  : "border border-stone-200 text-stone-600 hover:bg-stone-50"
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 disabled:text-stone-300 disabled:bg-stone-50 disabled:cursor-not-allowed transition-colors"
        >
          Next
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Content
// ---------------------------------------------------------------------------

function ContactsPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();

  // URL-based state
  const searchFromUrl = searchParams.get("q") ?? "";
  const [searchInput, setSearchInput] = useState(searchFromUrl);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const search = searchFromUrl;
  const page = Number(searchParams.get("page") ?? "1");
  const scoreFilter = searchParams.get("score") ?? undefined;
  const priorityFilter = searchParams.get("priority") ?? undefined;
  const tagFilter = searchParams.get("tag") ?? "";
  const sourceFilter = searchParams.get("source") ?? "";
  const dateFrom = searchParams.get("date_from") ?? "";
  const dateTo = searchParams.get("date_to") ?? "";
  const sortParam = searchParams.get("sort") ?? "score";
  const showFilters = searchParams.get("filters") === "1";

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const setParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value) params.set(key, value);
        else params.delete(key);
      }
      if (!("page" in updates)) params.delete("page");
      router.replace(`/contacts?${params.toString()}`, { scroll: false });
    },
    [searchParams, router]
  );

  // Data queries
  const { data: allTags = [] } = useQuery({
    queryKey: ["tags"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/tags");
      return (data?.data as string[]) ?? [];
    },
  });

  const statsQuery = useQuery({
    queryKey: ["contacts", "stats"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/stats");
      return data?.data as { total: number; strong: number; active: number; dormant: number } | undefined;
    },
  });

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
    sort: sortParam,
  });

  const contacts = data?.data ?? [];
  const meta = data?.meta;
  const activeFilterCount = [tagFilter, sourceFilter, dateFrom, dateTo, scoreFilter, priorityFilter].filter(Boolean).length;
  const stats = statsQuery.data;
  const activeRelationships = stats ? stats.strong + stats.active : 0;

  // Bulk mutations
  const bulkUpdate = useMutation({
    mutationFn: async (body: {
      contact_ids: string[];
      add_tags?: string[];
      remove_tags?: string[];
      priority_level?: string;
    }) => {
      const { data, error } = await client.POST("/api/v1/contacts/bulk-update" as any, { body });
      if (error) throw new Error((error as { detail?: string })?.detail ?? "Bulk update failed");
      return data;
    },
    onSuccess: () => {
      setSelectedIds(new Set());
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
      void queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });

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

  const deleteMutation = useMutation({
    mutationFn: async (contactIds: string[]) => {
      for (const id of contactIds) {
        await client.DELETE("/api/v1/contacts/{contact_id}", {
          params: { path: { contact_id: id } },
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
    if (selectedIds.size === contacts.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(contacts.map((c) => c.id)));
  };

  const selectedArray = Array.from(selectedIds);
  const isPending = bulkUpdate.isPending || mergeMutation.isPending || deleteMutation.isPending;

  return (
    <div className="min-h-screen bg-stone-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-display font-bold text-stone-900">Contacts</h1>
            {stats && (
              <p className="text-sm text-stone-500 mt-0.5">
                <span className="font-mono-data">{stats.total.toLocaleString()}</span> contacts
                {" \u00B7 "}
                <span className="font-mono-data">{activeRelationships}</span> active relationships
              </p>
            )}
          </div>
          <Link
            href="/contacts/new"
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" /> Add Contact
          </Link>
        </div>

        {/* Search + Filter bar */}
        <div className="bg-white rounded-xl border border-stone-200 p-4 mb-4">
          <div className="flex gap-3 mb-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
              <input
                type="text"
                placeholder="Search by name, email, company, or notes..."
                value={searchInput}
                onChange={(e) => {
                  const value = e.target.value;
                  setSearchInput(value);
                  if (debounceRef.current) clearTimeout(debounceRef.current);
                  debounceRef.current = setTimeout(() => {
                    setParams({ q: value || undefined });
                  }, 300);
                }}
                className="w-full pl-10 pr-4 py-2.5 text-sm rounded-lg border border-stone-200 focus:outline-none focus:ring-2 focus:ring-teal-400 placeholder:text-stone-400"
              />
            </div>
            <button
              onClick={() => setParams({ filters: showFilters ? undefined : "1", page: String(page) })}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border transition-colors ${
                showFilters || activeFilterCount > 0
                  ? "bg-teal-50 border-teal-200 text-teal-700"
                  : "border-stone-200 text-stone-600 hover:bg-stone-50"
              }`}
            >
              <SlidersHorizontal className="w-4 h-4" />
              Filters
              {activeFilterCount > 0 && (
                <span className="ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full bg-teal-100 text-teal-700 text-[10px] font-bold">
                  {activeFilterCount}
                </span>
              )}
            </button>
          </div>

          {/* Quick filter chips with group labels */}
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mr-1">Priority</span>
              {priorityConfig.map(({ key, label, icon, activeColor }) => {
                const isActive = priorityFilter === key;
                return (
                  <button
                    key={key}
                    onClick={() => setParams({ priority: isActive ? undefined : key })}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                      isActive ? activeColor : "bg-white border-stone-200 text-stone-500 hover:bg-stone-50"
                    }`}
                  >
                    {icon} {label}
                  </button>
                );
              })}
            </div>
            <div className="w-px h-5 bg-stone-200" />
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mr-1">Score</span>
              {scoreConfig.map(({ key, label, dotColor, activeColor }) => {
                const isActive = scoreFilter === key;
                return (
                  <button
                    key={key}
                    onClick={() => setParams({ score: isActive ? undefined : key })}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                      isActive ? activeColor : "bg-white border-stone-200 text-stone-500 hover:bg-stone-50"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} /> {label}
                  </button>
                );
              })}
            </div>
            {activeFilterCount > 0 && (
              <div className="flex items-center gap-2 ml-auto">
                <div className="w-px h-4 bg-stone-200" />
                <button
                  onClick={() => router.replace("/contacts", { scroll: false })}
                  className="text-xs text-stone-400 hover:text-stone-600 font-medium"
                >
                  Clear all
                </button>
              </div>
            )}
          </div>

          {/* Expanded filter panel */}
          {showFilters && (
            <div className="border-t border-stone-200 pt-4 mt-4">
              <div className="grid grid-cols-3 gap-4">
                {/* Platform filter */}
                <div>
                  <label className="text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-2 block">Platform</label>
                  <div className="space-y-2">
                    {[
                      { value: "gmail", label: "Gmail", icon: <Mail className="w-3.5 h-3.5 text-red-400" /> },
                      { value: "telegram", label: "Telegram", icon: <MessageCircle className="w-3.5 h-3.5 text-sky-500" /> },
                      { value: "twitter", label: "Twitter / X", icon: <Twitter className="w-3.5 h-3.5 text-stone-500" /> },
                    ].map(({ value, label, icon }) => (
                      <label key={value} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={sourceFilter === value}
                          onChange={() => setParams({ source: sourceFilter === value ? undefined : value })}
                          className="w-3.5 h-3.5 rounded border-stone-300 text-teal-600"
                        />
                        {icon}
                        <span className="text-xs text-stone-700">{label}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Tags filter */}
                <div>
                  <label className="text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-2 block">Tags</label>
                  <select
                    value={tagFilter}
                    onChange={(e) => setParams({ tag: e.target.value || undefined })}
                    className="w-full px-2.5 py-2 rounded-md border border-stone-200 bg-white text-xs focus:outline-none focus:ring-2 focus:ring-teal-400 mb-2"
                  >
                    <option value="">All tags</option>
                    {allTags.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                  {tagFilter && (
                    <div className="flex flex-wrap gap-1.5">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-violet-50 text-violet-700 border border-violet-200">
                        {tagFilter}
                        <button onClick={() => setParams({ tag: undefined })}>
                          <X className="w-2.5 h-2.5" />
                        </button>
                      </span>
                    </div>
                  )}
                </div>

                {/* Last Contact — date presets + range */}
                <div>
                  <label className="text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-2 block">Last Contact</label>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {datePresets.map(({ label, days }) => {
                      const presetDate = new Date(Date.now() - days * 86400000).toISOString().split("T")[0];
                      const isActive = dateFrom === presetDate;
                      return (
                        <button
                          key={label}
                          onClick={() => setParams({
                            date_from: isActive ? undefined : presetDate,
                            date_to: isActive ? undefined : new Date().toISOString().split("T")[0],
                          })}
                          className={`px-2 py-1 text-[11px] font-medium rounded-md border transition-colors ${
                            isActive
                              ? "border-teal-200 bg-teal-50 text-teal-700"
                              : "border-stone-200 text-stone-500 hover:bg-stone-50"
                          }`}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                  <div className="space-y-2">
                    <div>
                      <label className="text-[10px] text-stone-400 mb-0.5 block">From</label>
                      <input
                        type="date"
                        value={dateFrom}
                        onChange={(e) => setParams({ date_from: e.target.value || undefined })}
                        className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-1.5 text-stone-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-stone-400 mb-0.5 block">To</label>
                      <input
                        type="date"
                        value={dateTo}
                        onChange={(e) => setParams({ date_to: e.target.value || undefined })}
                        className="w-full text-xs border border-stone-200 rounded-lg px-2.5 py-1.5 text-stone-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between mt-4 pt-3 border-t border-stone-100">
                <p className="text-xs text-stone-400">
                  {meta ? (
                    <>Showing <strong className="text-stone-600">{meta.total}</strong> contacts matching filters</>
                  ) : (
                    "Loading..."
                  )}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => router.replace("/contacts", { scroll: false })}
                    className="text-xs text-stone-500 hover:text-stone-700"
                  >
                    Reset all
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Empty state */}
        {!isLoading && !isError && contacts.length === 0 && (
          <div className="bg-white rounded-xl border border-stone-200 p-12 text-center mb-4">
            <div className="w-14 h-14 rounded-full bg-stone-100 flex items-center justify-center mx-auto mb-4">
              <SearchX className="w-7 h-7 text-stone-400" />
            </div>
            <h3 className="text-base font-display font-bold text-stone-900 mb-1">No contacts found</h3>
            <p className="text-sm text-stone-500 mb-5 max-w-sm mx-auto">
              Try adjusting your filters or search terms, or add a new contact.
            </p>
            <div className="flex items-center justify-center gap-3">
              {activeFilterCount > 0 && (
                <button
                  onClick={() => router.replace("/contacts", { scroll: false })}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 transition-colors"
                >
                  Clear filters
                </button>
              )}
              <Link
                href="/contacts/new"
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm"
              >
                <Plus className="w-4 h-4" /> Add Contact
              </Link>
            </div>
          </div>
        )}

        {/* Loading skeleton */}
        {isLoading && (
          <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
            <div className="bg-stone-50 border-b border-stone-200 h-11" />
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-stone-100">
                <div className="w-4 h-4 rounded bg-stone-100 animate-pulse" />
                <div className="w-9 h-9 rounded-full bg-stone-100 animate-pulse" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3.5 w-32 bg-stone-100 rounded animate-pulse" />
                  <div className="h-3 w-40 bg-stone-50 rounded animate-pulse" />
                </div>
                <div className="h-3.5 w-20 bg-stone-100 rounded animate-pulse" />
                <div className="h-5 w-14 bg-stone-100 rounded-full animate-pulse" />
                <div className="h-5 w-10 bg-stone-100 rounded-full animate-pulse" />
                <div className="h-3.5 w-10 bg-stone-100 rounded animate-pulse" />
                <div className="h-3.5 w-8 bg-stone-100 rounded animate-pulse" />
              </div>
            ))}
          </div>
        )}

        {isError && (
          <div className="text-center py-12 text-red-500">
            Failed to load contacts. Is the backend running?
          </div>
        )}

        {/* Table */}
        {contacts.length > 0 && (
          <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
            {/* Header row */}
            <div className="grid grid-cols-[40px_1fr_120px_80px_80px_80px_80px] gap-2 px-4 py-3 bg-stone-50 border-b border-stone-200 items-center">
              <div>
                <input
                  type="checkbox"
                  checked={contacts.length > 0 && selectedIds.size === contacts.length}
                  onChange={toggleSelectAll}
                  className="w-3.5 h-3.5 rounded border-stone-300 text-teal-600"
                  aria-label="Select all"
                />
              </div>
              {sortColumns.map(({ key, label }) => {
                const isActive = sortParam === key || (key === "name" && sortParam === "created") || (key === "interaction" && sortParam === "interaction");
                const sortKey = key === "name" ? "created" : key;
                return (
                  <div
                    key={key}
                    onClick={() => setParams({ sort: sortParam === sortKey ? "score" : sortKey })}
                    className={`flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider cursor-pointer select-none transition-colors hover:text-teal-600 ${
                      isActive ? "text-teal-600" : "text-stone-500"
                    } ${key === "activity" || key === "interaction" ? "justify-end" : key === "score" || key === "priority" ? "justify-center" : ""}`}
                  >
                    {label}
                    {isActive ? (
                      <ArrowDown className="w-3 h-3" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-100" />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Rows */}
            {contacts.map((contact) => {
              const name =
                contact.full_name ??
                ([contact.given_name, contact.family_name].filter(Boolean).join(" ") || "Unnamed");
              const isSelected = selectedIds.has(contact.id);
              const primaryEmail = contact.emails?.[0];

              return (
                <div
                  key={contact.id}
                  className={`grid grid-cols-[40px_1fr_120px_80px_80px_80px_80px] gap-2 px-4 py-3 border-b border-stone-100 items-center transition-colors ${
                    isSelected ? "bg-teal-50" : "hover:bg-stone-50/50"
                  }`}
                >
                  <div>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(contact.id)}
                      className="w-3.5 h-3.5 rounded border-stone-300 text-teal-600"
                      aria-label={`Select ${name}`}
                    />
                  </div>

                  {/* Contact: avatar + name + email + platform icons */}
                  <div className="flex items-center gap-3 min-w-0">
                    <ContactAvatar avatarUrl={contact.avatar_url} name={name} size="sm" />
                    <div className="min-w-0">
                      <Link
                        href={`/contacts/${contact.id}`}
                        className="text-sm font-medium text-stone-900 hover:text-teal-700 truncate block"
                      >
                        {name}
                      </Link>
                      <div className="flex items-center gap-1.5">
                        {primaryEmail && (
                          <p className="text-xs text-stone-400 truncate">{primaryEmail}</p>
                        )}
                        <PlatformIcons
                          emails={contact.emails}
                          telegram={contact.telegram_username}
                          twitter={contact.twitter_handle}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Company */}
                  <div className="text-xs text-stone-600 truncate">
                    {contact.company || <span className="text-stone-300">&mdash;</span>}
                  </div>

                  {/* Score */}
                  <div className="text-center">
                    <ScoreNumberBadge score={contact.relationship_score} />
                  </div>

                  {/* Priority */}
                  <div className="text-center">
                    <PriorityBadge level={contact.priority_level} />
                  </div>

                  {/* Activity count */}
                  <div className="text-right font-mono-data text-xs text-stone-500">
                    {contact.interaction_count ?? 0}
                  </div>

                  {/* Last interaction */}
                  <div className="text-right">
                    <DaysAgo dateStr={contact.last_interaction_at} />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination */}
        {meta && meta.total_pages > 1 && (
          <Pagination
            page={page}
            totalPages={meta.total_pages}
            total={meta.total}
            pageSize={20}
            onPageChange={(p) => setParams({ page: String(p) })}
          />
        )}

        {/* Bulk action bar — sticky bottom */}
        {selectedIds.size > 0 && (
          <BulkActionBar
            selectedCount={selectedIds.size}
            allTags={allTags}
            isPending={isPending}
            onAddTag={(tag) => bulkUpdate.mutate({ contact_ids: selectedArray, add_tags: [tag] })}
            onRemoveTag={(tag) => bulkUpdate.mutate({ contact_ids: selectedArray, remove_tags: [tag] })}
            onArchive={() => bulkUpdate.mutate({ contact_ids: selectedArray, priority_level: "archived" })}
            onDelete={() => {
              if (confirm(`Delete ${selectedArray.length} contact${selectedArray.length > 1 ? "s" : ""}? This cannot be undone.`)) {
                deleteMutation.mutate(selectedArray);
              }
            }}
            onMerge={() => {
              if (selectedArray.length >= 2 && confirm(`Merge ${selectedArray.length} contacts into one? This cannot be undone.`)) {
                mergeMutation.mutate(selectedArray);
              }
            }}
            onClear={() => setSelectedIds(new Set())}
          />
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
