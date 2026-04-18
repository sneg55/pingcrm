"use client";

export const dynamic = "force-dynamic";

import { Suspense, useState } from "react";
import Link from "next/link";
import {
  Plus,
  X,
  SlidersHorizontal,
  Tag,
  Archive,
  GitMerge,
  Trash2,
  ArrowUpDown,
  ArrowDown,
  Mail,
  MessageCircle,
  Twitter,
  SearchX,
  Building2,
} from "lucide-react";
import { ContactAvatar } from "@/components/contact-avatar";
import { CompanyFavicon } from "@/components/company-favicon";
import { formatDistanceToNow } from "date-fns";
import { useContactsPage } from "./_hooks/use-contacts-page";
import { ContactsToolbar } from "./_components/contacts-toolbar";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const sortColumns = [
  { key: "name", label: "Contact" },
  { key: "company", label: "Company" },
  { key: "score", label: "Score" },
  { key: "priority", label: "Priority" },
  { key: "activity", label: "Activity" },
  { key: "interaction", label: "Last Conversation" },
] as const;

// ---------------------------------------------------------------------------
// Score number badge
// ---------------------------------------------------------------------------

function ScoreNumberBadge({ score }: { score: number }) {
  let color = "bg-sky-50 dark:bg-sky-950 text-sky-700 dark:text-sky-400 border-sky-100 dark:border-sky-900";
  let dotColor = "bg-sky-400";
  if (score >= 8) { color = "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border-emerald-100 dark:border-emerald-900"; dotColor = "bg-emerald-500"; }
  else if (score >= 4) { color = "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border-amber-100 dark:border-amber-900"; dotColor = "bg-amber-400"; }
  else if (score >= 1) { color = "bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 border-red-100 dark:border-red-900"; dotColor = "bg-red-400"; }

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
  if (!icon) return <span className="text-stone-300 dark:text-stone-600">&mdash;</span>;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 border border-red-100 dark:border-red-900">
      {icon}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Platform icons for contact row
// ---------------------------------------------------------------------------

function PlatformIcons({ emails, telegram, twitter }: { emails: string[]; telegram?: string | null; twitter?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {emails.length > 0 && <span className="text-red-400" aria-label="Email"><Mail className="w-3 h-3" /></span>}
      {telegram && <span className="text-sky-400" aria-label="Telegram"><MessageCircle className="w-3 h-3" /></span>}
      {twitter && <span className="text-stone-400 dark:text-stone-500" aria-label="Twitter/X"><Twitter className="w-3 h-3" /></span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Days-ago label
// ---------------------------------------------------------------------------

function DaysAgo({ dateStr }: { dateStr?: string | null }) {
  if (!dateStr) return <span className="text-stone-300 dark:text-stone-600">&mdash;</span>;
  const days = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
  const isOverdue = days > 30;
  return (
    <span className={`font-mono-data text-xs ${isOverdue ? "font-medium text-red-500" : "text-stone-500 dark:text-stone-400"}`}>
      {days}d
    </span>
  );
}

// ---------------------------------------------------------------------------
// Archived chip
// ---------------------------------------------------------------------------

function ArchivedChip() {
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 border border-stone-200 dark:border-stone-700">
      Archived
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
  onSetPriority,
  onSetCompany,
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
  onSetPriority: (level: string) => void;
  onSetCompany: (company: string) => void;
  onClear: () => void;
  isPending: boolean;
}) {
  const [tagInput, setTagInput] = useState("");
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const [tagMode, setTagMode] = useState<"add" | "remove">("add");
  const [showPriorityDropdown, setShowPriorityDropdown] = useState(false);
  const [showCompanyInput, setShowCompanyInput] = useState(false);
  const [companyInput, setCompanyInput] = useState("");

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
          <div className="absolute left-0 bottom-full mb-1 w-56 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg z-50 p-2">
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
              className="w-full px-2.5 py-1.5 text-sm text-stone-900 dark:text-stone-100 rounded-md border border-stone-300 dark:border-stone-700 focus:outline-none focus:ring-2 focus:ring-teal-400 mb-1 bg-white dark:bg-stone-800 placeholder:text-stone-400 dark:placeholder:text-stone-500"
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
                  className="w-full text-left px-2.5 py-1.5 text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-md"
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
                  className="w-full text-left px-2.5 py-1.5 text-sm text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 rounded-md font-medium"
                >
                  + Create &quot;{tagInput.trim()}&quot;
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Priority dropdown */}
      <div className="relative">
        <button
          onClick={() => { setShowPriorityDropdown((v) => !v); setShowCompanyInput(false); setShowTagDropdown(false); }}
          disabled={isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" /> Priority
        </button>
        {showPriorityDropdown && (
          <div className="absolute left-0 bottom-full mb-1 w-40 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg z-50 p-1">
            {[
              { value: "high", label: "High", color: "text-red-600 dark:text-red-400" },
              { value: "medium", label: "Medium", color: "text-stone-700 dark:text-stone-300" },
              { value: "low", label: "Low", color: "text-stone-400 dark:text-stone-500" },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => { onSetPriority(opt.value); setShowPriorityDropdown(false); }}
                className={`w-full text-left px-2.5 py-1.5 text-sm ${opt.color} hover:bg-stone-100 dark:hover:bg-stone-800 rounded-md`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Company input */}
      <div className="relative">
        <button
          onClick={() => { setShowCompanyInput((v) => !v); setShowPriorityDropdown(false); setShowTagDropdown(false); }}
          disabled={isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
        >
          <Building2 className="w-3.5 h-3.5" /> Company
        </button>
        {showCompanyInput && (
          <div className="absolute left-0 bottom-full mb-1 w-56 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg z-50 p-2">
            <input
              type="text"
              placeholder="Set company name..."
              value={companyInput}
              onChange={(e) => setCompanyInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && companyInput.trim()) {
                  onSetCompany(companyInput.trim());
                  setCompanyInput("");
                  setShowCompanyInput(false);
                }
              }}
              className="w-full px-2.5 py-1.5 text-sm text-stone-900 dark:text-stone-100 rounded-md border border-stone-300 dark:border-stone-700 focus:outline-none focus:ring-2 focus:ring-teal-400 bg-white dark:bg-stone-800 placeholder:text-stone-400 dark:placeholder:text-stone-500"
              autoFocus
            />
          </div>
        )}
      </div>

      {selectedCount >= 2 && (
        <button
          onClick={onMerge}
          disabled={isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
        >
          <GitMerge className="w-3.5 h-3.5" /> Merge
        </button>
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
      <p className="text-xs text-stone-500 dark:text-stone-400">
        Showing <strong>{from}-{to}</strong> of <strong>{total}</strong>
      </p>
      <div className="flex items-center gap-1.5">
        <button
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:text-stone-300 dark:disabled:text-stone-600 disabled:bg-stone-50 dark:disabled:bg-stone-900 disabled:cursor-not-allowed transition-colors"
        >
          Previous
        </button>
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`dots-${i}`} className="text-xs text-stone-400 dark:text-stone-500 px-1">...</span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p)}
              className={`px-2.5 py-1.5 text-xs font-medium rounded-lg min-w-[32px] text-center transition-colors ${
                p === page
                  ? "bg-teal-600 text-white"
                  : "border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:text-stone-300 dark:disabled:text-stone-600 disabled:bg-stone-50 dark:disabled:bg-stone-900 disabled:cursor-not-allowed transition-colors"
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
  const {
    searchInput,
    setSearchInput,
    debounceRef,
    search,
    page,
    scoreFilter,
    priorityFilter,
    tagFilter,
    sourceFilter,
    dateFrom,
    dateTo,
    includeArchived,
    sortParam,
    showFilters,
    setParams,
    router,
    allTags,
    meta,
    isLoading,
    isError,
    contacts,
    activeFilterCount,
    stats,
    activeRelationships,
    totalCount,
    selectedIds,
    setSelectedIds,
    selectedArray,
    selectingAll,
    toggleSelect,
    toggleSelectAll,
    bulkUpdate,
    mergeMutation,
    deleteMutation,
    isPending,
  } = useContactsPage();

  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-2xl font-display font-bold text-stone-900 dark:text-stone-100">Contacts</h1>
            {stats && (
              <p className="text-sm text-stone-500 dark:text-stone-400 mt-0.5">
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
        <div className="animate-in stagger-1">
        <ContactsToolbar
          searchInput={searchInput}
          setSearchInput={setSearchInput}
          debounceRef={debounceRef}
          scoreFilter={scoreFilter}
          priorityFilter={priorityFilter}
          tagFilter={tagFilter}
          sourceFilter={sourceFilter}
          dateFrom={dateFrom}
          dateTo={dateTo}
          includeArchived={includeArchived}
          showFilters={showFilters}
          activeFilterCount={activeFilterCount}
          page={page}
          setParams={setParams}
          allTags={allTags}
          meta={meta}
        />
        </div>

        {/* Empty state */}
        {!isLoading && !isError && contacts.length === 0 && (
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-12 text-center mb-4">
            <div className="w-14 h-14 rounded-full bg-stone-100 dark:bg-stone-800 flex items-center justify-center mx-auto mb-4">
              <SearchX className="w-7 h-7 text-stone-400 dark:text-stone-500" />
            </div>
            <h3 className="text-base font-display font-bold text-stone-900 dark:text-stone-100 mb-1">No contacts found</h3>
            <p className="text-sm text-stone-500 dark:text-stone-400 mb-5 max-w-sm mx-auto">
              Try adjusting your filters or search terms, or add a new contact.
            </p>
            <div className="flex items-center justify-center gap-3">
              {activeFilterCount > 0 && (
                <button
                  onClick={() => router.replace("/contacts", { scroll: false })}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
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
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 overflow-hidden">
            <div className="bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 h-11" />
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-stone-100 dark:border-stone-800">
                <div className="w-4 h-4 rounded bg-stone-100 dark:bg-stone-800 animate-pulse" />
                <div className="w-9 h-9 rounded-full bg-stone-100 dark:bg-stone-800 animate-pulse" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3.5 w-32 bg-stone-100 dark:bg-stone-800 rounded animate-pulse" />
                  <div className="h-3 w-40 bg-stone-50 dark:bg-stone-800 rounded animate-pulse" />
                </div>
                <div className="h-3.5 w-20 bg-stone-100 dark:bg-stone-800 rounded animate-pulse" />
                <div className="h-5 w-14 bg-stone-100 dark:bg-stone-800 rounded-full animate-pulse" />
                <div className="h-5 w-10 bg-stone-100 dark:bg-stone-800 rounded-full animate-pulse" />
                <div className="h-3.5 w-10 bg-stone-100 dark:bg-stone-800 rounded animate-pulse" />
                <div className="h-3.5 w-8 bg-stone-100 dark:bg-stone-800 rounded animate-pulse" />
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
          <div className="animate-in stagger-2 bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 overflow-hidden">
            {/* Header row — desktop only */}
            <div className="hidden lg:grid grid-cols-[40px_1fr_120px_70px_70px_60px_100px] gap-2 px-4 py-3 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700 items-center">
              <div>
                <input
                  type="checkbox"
                  checked={selectedIds.size > 0 && selectedIds.size >= totalCount}
                  ref={(el) => { if (el) el.indeterminate = selectedIds.size > 0 && selectedIds.size < totalCount; }}
                  onChange={toggleSelectAll}
                  disabled={selectingAll}
                  className="w-3.5 h-3.5 rounded border-stone-300 dark:border-stone-600 text-teal-600"
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
                    className={`flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider cursor-pointer select-none transition-colors hover:text-teal-600 dark:hover:text-teal-400 ${
                      isActive ? "text-teal-600 dark:text-teal-400" : "text-stone-500 dark:text-stone-400"
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

            {/* Desktop rows */}
            {contacts.map((contact) => {
              const name =
                contact.full_name ??
                ([contact.given_name, contact.family_name].filter(Boolean).join(" ") || "Unnamed");
              const isSelected = selectedIds.has(contact.id);
              const primaryEmail = contact.emails?.[0];

              return (
                <div
                  key={contact.id}
                  className={`card-hover hidden lg:grid grid-cols-[40px_1fr_120px_70px_70px_60px_100px] gap-2 px-4 py-3 border-b border-stone-100 dark:border-stone-800 items-center transition-colors ${
                    isSelected ? "bg-teal-50 dark:bg-teal-950" : "hover:bg-stone-50/50 dark:hover:bg-stone-800/50"
                  }`}
                >
                  <div>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(contact.id)}
                      className="w-3.5 h-3.5 rounded border-stone-300 dark:border-stone-600 text-teal-600"
                      aria-label={`Select ${name}`}
                    />
                  </div>

                  {/* Contact: avatar + name + email + platform icons */}
                  <div className="flex items-center gap-3 min-w-0">
                    <ContactAvatar avatarUrl={contact.avatar_url} name={name} size="sm" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <Link
                          href={`/contacts/${contact.id}`}
                          className={`text-sm font-medium text-stone-900 dark:text-stone-100 hover:text-teal-700 dark:hover:text-teal-400 truncate block ${
                            contact.priority_level === "archived" ? "opacity-60" : ""
                          }`}
                        >
                          {name}
                        </Link>
                        {contact.priority_level === "archived" && <ArchivedChip />}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {primaryEmail && (
                          <p className={`text-xs text-stone-400 dark:text-stone-500 truncate ${
                            contact.priority_level === "archived" ? "opacity-60" : ""
                          }`}>{primaryEmail}</p>
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
                  <div className={`text-xs text-stone-600 dark:text-stone-300 truncate flex items-center gap-1.5 ${
                    contact.priority_level === "archived" ? "opacity-60" : ""
                  }`}>
                    {contact.company ? (
                      <>
                        <CompanyFavicon emails={contact.emails} size="w-3.5 h-3.5" className="shrink-0" />
                        <span className="truncate">{contact.company}</span>
                      </>
                    ) : (
                      <span className="text-stone-300 dark:text-stone-600">&mdash;</span>
                    )}
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
                  <div className="text-right font-mono-data text-xs text-stone-500 dark:text-stone-400">
                    {(contact as any).interaction_count ?? 0}
                  </div>

                  {/* Last interaction */}
                  <div className="text-right">
                    <DaysAgo dateStr={contact.last_interaction_at} />
                  </div>
                </div>
              );
            })}

            {/* Mobile card list — visible only on < lg screens */}
            <div className="lg:hidden divide-y divide-stone-100 dark:divide-stone-800">
              {contacts.map((contact) => {
                const name =
                  contact.full_name ??
                  ([contact.given_name, contact.family_name].filter(Boolean).join(" ") || "Unnamed");
                return (
                  <Link
                    key={contact.id}
                    href={`/contacts/${contact.id}`}
                    className="card-hover flex items-center gap-3 px-4 py-3 hover:bg-stone-50 dark:hover:bg-stone-800/50 transition-colors"
                  >
                    <ContactAvatar avatarUrl={contact.avatar_url} name={name} size="sm" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className={`text-sm font-medium text-stone-900 dark:text-stone-100 truncate ${
                          contact.priority_level === "archived" ? "opacity-60" : ""
                        }`}>
                          {name}
                        </p>
                        {contact.priority_level === "archived" && <ArchivedChip />}
                        <ScoreNumberBadge score={contact.relationship_score} />
                      </div>
                      <p className={`text-xs text-stone-500 dark:text-stone-400 truncate ${
                        contact.priority_level === "archived" ? "opacity-60" : ""
                      }`}>
                        {[contact.title, contact.company].filter(Boolean).join(" at ") || contact.emails?.[0] || ""}
                      </p>
                    </div>
                    {contact.last_interaction_at && (
                      <span className="text-[11px] text-stone-400 dark:text-stone-500 shrink-0">
                        {formatDistanceToNow(new Date(contact.last_interaction_at), { addSuffix: true })}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
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
            onSetPriority={(level) => bulkUpdate.mutate({ contact_ids: selectedArray, priority_level: level })}
            onSetCompany={(company) => bulkUpdate.mutate({ contact_ids: selectedArray, company })}
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
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="h-8 w-32 bg-stone-200 dark:bg-stone-800 rounded animate-pulse mb-6" />
        <div className="bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 overflow-hidden">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-stone-100 dark:border-stone-800">
              <div className="w-7 h-7 rounded-full bg-stone-100 dark:bg-stone-800 animate-pulse" />
              <div className="flex-1 h-4 bg-stone-100 dark:bg-stone-800 rounded animate-pulse" />
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
