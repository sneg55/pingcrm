"use client";

import type { RefObject } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  X,
  SlidersHorizontal,
  Mail,
  MessageCircle,
  Twitter,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Constants (co-located so toolbar is self-contained)
// ---------------------------------------------------------------------------

const priorityConfig = [
  { key: "high", label: "High", icon: "\uD83D\uDD25", activeColor: "bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800 ring-1 ring-red-300 ring-offset-1" },
  { key: "medium", label: "Medium", icon: "\u26A1", activeColor: "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800 ring-1 ring-amber-300 ring-offset-1" },
  { key: "low", label: "Low", icon: "\uD83D\uDCA4", activeColor: "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800 ring-1 ring-blue-300 ring-offset-1" },
] as const;

const scoreConfig = [
  { key: "strong", label: "Strong", dotColor: "bg-emerald-500", activeColor: "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800 ring-1 ring-emerald-300 ring-offset-1" },
  { key: "active", label: "Warm", dotColor: "bg-amber-400", activeColor: "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800 ring-1 ring-amber-300 ring-offset-1" },
  { key: "dormant", label: "Cold", dotColor: "bg-red-400", activeColor: "bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800 ring-1 ring-red-300 ring-offset-1" },
] as const;

const datePresets = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "3mo", days: 90 },
  { label: "6mo", days: 180 },
  { label: "12mo", days: 365 },
] as const;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export type ContactsToolbarProps = {
  // Search
  searchInput: string;
  setSearchInput: (value: string) => void;
  debounceRef: RefObject<ReturnType<typeof setTimeout> | null>;
  // Quick filter chips
  scoreFilter: string | undefined;
  priorityFilter: string | undefined;
  ghostedFilter: boolean;
  // Expanded filter panel
  tagFilter: string;
  sourceFilter: string;
  dateFrom: string;
  dateTo: string;
  includeArchived: boolean;
  showFilters: boolean;
  activeFilterCount: number;
  // Page (needed for filters toggle)
  page: number;
  // Shared state setters
  setParams: (updates: Record<string, string | undefined>) => void;
  // Tags list for the expanded panel
  allTags: string[];
  // Meta for result count display inside expanded panel
  meta: { total: number; total_pages: number } | undefined;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ContactsToolbar({
  searchInput,
  setSearchInput,
  debounceRef,
  scoreFilter,
  priorityFilter,
  ghostedFilter,
  tagFilter,
  sourceFilter,
  dateFrom,
  dateTo,
  includeArchived,
  showFilters,
  activeFilterCount,
  page,
  setParams,
  allTags,
  meta,
}: ContactsToolbarProps) {
  const router = useRouter();

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-4 mb-4">
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="flex-1 min-w-0 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400 dark:text-stone-500" />
          <input
            type="text"
            placeholder="Search by name, email, company, or notes..."
            value={searchInput}
            onChange={(e) => {
              const value = e.target.value;
              setSearchInput(value);
              if (debounceRef.current) clearTimeout(debounceRef.current);
              debounceRef.current = setTimeout(() => {
                setParams({ q: value.trim() || undefined });
              }, 300);
            }}
            className="w-full pl-10 pr-4 py-2.5 text-sm rounded-lg border border-stone-200 dark:border-stone-700 focus:outline-none focus:ring-2 focus:ring-teal-400 placeholder:text-stone-400 dark:placeholder:text-stone-500 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100"
          />
        </div>
        <button
          onClick={() => setParams({ filters: showFilters ? undefined : "1", page: String(page) })}
          className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border transition-colors ${
            showFilters || activeFilterCount > 0
              ? "bg-teal-50 dark:bg-teal-950 border-teal-200 dark:border-teal-800 text-teal-700 dark:text-teal-400"
              : "border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
          }`}
        >
          <SlidersHorizontal className="w-4 h-4" />
          Filters
          {activeFilterCount > 0 && (
            <span className="ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-400 text-[10px] font-bold">
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {/* Quick filter chips with group labels */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] font-semibold text-stone-400 dark:text-stone-500 uppercase tracking-wider mr-1">Priority</span>
          {priorityConfig.map(({ key, label, icon, activeColor }) => {
            const isActive = priorityFilter === key;
            return (
              <button
                key={key}
                onClick={() => setParams({ priority: isActive ? undefined : key })}
                className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                  isActive ? activeColor : "bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-700 text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-800"
                }`}
              >
                {icon} {label}
              </button>
            );
          })}
        </div>
        <div className="hidden sm:block w-px h-5 bg-stone-200 dark:bg-stone-700" />
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] font-semibold text-stone-400 dark:text-stone-500 uppercase tracking-wider mr-1">Score</span>
          {scoreConfig.map(({ key, label, dotColor, activeColor }) => {
            const isActive = scoreFilter === key;
            return (
              <button
                key={key}
                onClick={() => setParams({ score: isActive ? undefined : key })}
                className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                  isActive ? activeColor : "bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-700 text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-800"
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} /> {label}
              </button>
            );
          })}
        </div>
        <div className="hidden sm:block w-px h-5 bg-stone-200 dark:bg-stone-700" />
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setParams({ ghosted: ghostedFilter ? undefined : "true" })}
            title="Last 3 messages were yours, no reply."
            className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
              ghostedFilter
                ? "bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-200 border-stone-300 dark:border-stone-600 ring-1 ring-stone-300 ring-offset-1"
                : "bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-700 text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-800"
            }`}
          >
            Ghosted
          </button>
        </div>
        {activeFilterCount > 0 && (
          <div className="flex items-center gap-2 sm:ml-auto">
            <div className="w-px h-4 bg-stone-200 dark:bg-stone-700" />
            <button
              onClick={() => router.replace("/contacts", { scroll: false })}
              className="text-xs text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 font-medium"
            >
              Clear all
            </button>
          </div>
        )}
      </div>

      {/* Expanded filter panel */}
      {showFilters && (
        <div className="border-t border-stone-200 dark:border-stone-700 pt-4 mt-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Platform filter */}
            <div>
              <label className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider mb-2 block">Platform</label>
              <div className="space-y-2">
                {[
                  { value: "gmail", label: "Gmail", icon: <Mail className="w-3.5 h-3.5 text-red-400" /> },
                  { value: "telegram", label: "Telegram", icon: <MessageCircle className="w-3.5 h-3.5 text-sky-500" /> },
                  { value: "twitter", label: "Twitter / X", icon: <Twitter className="w-3.5 h-3.5 text-stone-500 dark:text-stone-400" /> },
                ].map(({ value, label, icon }) => (
                  <label key={value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={sourceFilter === value}
                      onChange={() => setParams({ source: sourceFilter === value ? undefined : value })}
                      className="w-3.5 h-3.5 rounded border-stone-300 dark:border-stone-600 text-teal-600"
                    />
                    {icon}
                    <span className="text-xs text-stone-700 dark:text-stone-300">{label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Tags filter */}
            <div>
              <label className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider mb-2 block">Tags</label>
              <select
                value={tagFilter}
                onChange={(e) => setParams({ tag: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 text-xs focus:outline-none focus:ring-2 focus:ring-teal-400 mb-2"
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
              <label className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider mb-2 block">Last Contact</label>
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
                          ? "border-teal-200 dark:border-teal-800 bg-teal-50 dark:bg-teal-950 text-teal-700 dark:text-teal-400"
                          : "border-stone-200 dark:border-stone-700 text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-800"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              <div className="space-y-2">
                <div>
                  <label className="text-[10px] text-stone-400 dark:text-stone-500 mb-0.5 block">From</label>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setParams({ date_from: e.target.value || undefined })}
                    className="w-full text-xs border border-stone-200 dark:border-stone-700 rounded-lg px-2.5 py-1.5 text-stone-700 dark:text-stone-300 focus:outline-none focus:ring-2 focus:ring-teal-400 bg-white dark:bg-stone-900"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-stone-400 dark:text-stone-500 mb-0.5 block">To</label>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setParams({ date_to: e.target.value || undefined })}
                    className="w-full text-xs border border-stone-200 dark:border-stone-700 rounded-lg px-2.5 py-1.5 text-stone-700 dark:text-stone-300 focus:outline-none focus:ring-2 focus:ring-teal-400 bg-white dark:bg-stone-900"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="border-t border-stone-100 dark:border-stone-800 mt-4 pt-3 flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) =>
                  setParams({ include_archived: e.target.checked ? "1" : undefined })
                }
                className="w-4 h-4 rounded border-stone-300 dark:border-stone-600 text-teal-600"
              />
              <span className="text-xs font-medium text-stone-700 dark:text-stone-300">
                Include archived contacts
              </span>
            </label>
            <span className="hidden sm:inline text-[11px] text-stone-400 dark:text-stone-500">
              Search across active and archived contacts together
            </span>
          </div>

          <div className="flex items-center justify-between mt-4 pt-3 border-t border-stone-100 dark:border-stone-800">
            <p className="text-xs text-stone-400 dark:text-stone-500">
              {meta ? (
                <>Showing <strong className="text-stone-600 dark:text-stone-300">{meta.total}</strong> contacts matching filters</>
              ) : (
                "Loading..."
              )}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => router.replace("/contacts", { scroll: false })}
                className="text-xs text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-100"
              >
                Reset all
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
