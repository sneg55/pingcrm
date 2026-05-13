"use client";

import { Suspense } from "react";
import Link from "next/link";
import {
  Plus,
  ArrowUpDown,
  ArrowDown,
  SearchX,
} from "lucide-react";
import { ArchivedChip } from "@/components/archived-chip";
import { ContactAvatar } from "@/components/contact-avatar";
import { CompanyFavicon } from "@/components/company-favicon";
import { formatDistanceToNow } from "date-fns";
import { useContactsPage } from "./_hooks/use-contacts-page";
import { ContactsToolbar } from "./_components/contacts-toolbar";
import { BulkActionBar, Pagination } from "./_components/bulk-action-bar";
import { ScoreNumberBadge, PriorityBadge, PlatformIcons, DaysAgo } from "./_components/row-badges";

export const dynamic = "force-dynamic";

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

const ARCHIVED_PRIORITY = "archived";
const ARCHIVED_OPACITY_CLASS = "opacity-60";

// ---------------------------------------------------------------------------
// Score number badge
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Bulk Action Bar
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Main Content
// ---------------------------------------------------------------------------

function ContactsPageContent() {
  const {
    searchInput,
    setSearchInput,
    debounceRef,
    page,
    scoreFilter,
    priorityFilter,
    ghostedFilter,
    tagFilter,
    sourceFilter,
    interactionFrom,
    interactionTo,
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
          ghostedFilter={ghostedFilter}
          tagFilter={tagFilter}
          sourceFilter={sourceFilter}
          interactionFrom={interactionFrom}
          interactionTo={interactionTo}
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
            <h3 className="text-base font-display font-bold text-stone-900 dark:text-stone-100 mb-1">
              {ghostedFilter && activeFilterCount === 1 ? "No one's ghosting you" : "No contacts found"}
            </h3>
            <p className="text-sm text-stone-500 dark:text-stone-400 mb-5 max-w-sm mx-auto">
              {ghostedFilter && activeFilterCount === 1
                ? "Nice. Everyone you've messaged has replied within the last 3."
                : "Try adjusting your filters or search terms, or add a new contact."}
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
                  onChange={() => { void toggleSelectAll(); }}
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
                            contact.priority_level === ARCHIVED_PRIORITY ? ARCHIVED_OPACITY_CLASS : ""
                          }`}
                        >
                          {name}
                        </Link>
                        {contact.priority_level === ARCHIVED_PRIORITY && <ArchivedChip />}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {primaryEmail && (
                          <p className={`text-xs text-stone-400 dark:text-stone-500 truncate ${
                            contact.priority_level === ARCHIVED_PRIORITY ? ARCHIVED_OPACITY_CLASS : ""
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
                    contact.priority_level === ARCHIVED_PRIORITY ? ARCHIVED_OPACITY_CLASS : ""
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
                    {contact.interaction_count ?? 0}
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
                          contact.priority_level === ARCHIVED_PRIORITY ? ARCHIVED_OPACITY_CLASS : ""
                        }`}>
                          {name}
                        </p>
                        {contact.priority_level === ARCHIVED_PRIORITY && <ArchivedChip />}
                        <ScoreNumberBadge score={contact.relationship_score} />
                      </div>
                      <p className={`text-xs text-stone-500 dark:text-stone-400 truncate ${
                        contact.priority_level === ARCHIVED_PRIORITY ? ARCHIVED_OPACITY_CLASS : ""
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
            onArchive={() => bulkUpdate.mutate({ contact_ids: selectedArray, priority_level: ARCHIVED_PRIORITY })}
            onDelete={() => {
              // eslint-disable-next-line no-alert -- native confirm before destructive bulk delete
              if (confirm(`Delete ${selectedArray.length} contact${selectedArray.length > 1 ? "s" : ""}? This cannot be undone.`)) {
                deleteMutation.mutate(selectedArray);
              }
            }}
            onMerge={() => {
              // eslint-disable-next-line no-alert -- native confirm before destructive bulk merge
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
