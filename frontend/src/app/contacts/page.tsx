"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search, Plus, UserCircle, X, Filter } from "lucide-react";
import { useContacts } from "@/hooks/use-contacts";
import { ScoreBadge } from "@/components/score-badge";
import { formatDistanceToNow } from "date-fns";
import apiClient, { type ApiResponse } from "@/lib/api";

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

export default function ContactsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

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
  const showFilters = searchParams.get("filters") === "1";

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
      const { data } = await apiClient.get<ApiResponse<string[]>>("/contacts/tags");
      return data?.data ?? [];
    },
  });

  const activeFilterCount = [tagFilter, sourceFilter, dateFrom, dateTo, scoreFilter].filter(Boolean).length;

  const { data, isLoading, isError } = useContacts({
    search: search || undefined,
    page,
    page_size: 20,
    score: scoreFilter,
    tag: tagFilter || undefined,
    source: sourceFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  });

  const contacts = data?.data ?? [];
  const meta = data?.meta;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Contacts</h1>
            {meta && (
              <p className="text-sm text-gray-500 mt-0.5">
                {meta.total} total contacts
              </p>
            )}
          </div>
          <Link
            href="/contacts/new"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Contact
          </Link>
        </div>

        <div className="flex gap-2 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search by name or company..."
              value={searchInput}
              onChange={(e) => {
                const value = e.target.value;
                setSearchInput(value);
                if (debounceRef.current) clearTimeout(debounceRef.current);
                debounceRef.current = setTimeout(() => {
                  setParams({ q: value || undefined });
                }, 300);
              }}
              className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>
          <button
            onClick={() => setParams({ filters: showFilters ? undefined : "1", page: String(page) })}
            className={`inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
              showFilters || activeFilterCount > 0
                ? "bg-blue-50 border-blue-300 text-blue-700"
                : "bg-white border-gray-300 text-gray-600 hover:bg-gray-50"
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {activeFilterCount > 0 && (
              <span className="ml-0.5 inline-flex items-center justify-center w-5 h-5 text-xs rounded-full bg-blue-600 text-white">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {showFilters && (
          <div className="mb-4 p-4 bg-white rounded-lg border border-gray-200 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label htmlFor="filter-tag" className="block text-xs font-medium text-gray-500 mb-1">Tag</label>
              <select
                id="filter-tag"
                value={tagFilter}
                onChange={(e) => setParams({ tag: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                <option value="">All tags</option>
                {allTags.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="filter-source" className="block text-xs font-medium text-gray-500 mb-1">Source</label>
              <select
                id="filter-source"
                value={sourceFilter}
                onChange={(e) => setParams({ source: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                <option value="">All sources</option>
                {Object.entries(sourceLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="filter-from" className="block text-xs font-medium text-gray-500 mb-1">From</label>
              <input
                id="filter-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setParams({ date_from: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
            <div>
              <label htmlFor="filter-to" className="block text-xs font-medium text-gray-500 mb-1">To</label>
              <input
                id="filter-to"
                type="date"
                value={dateTo}
                onChange={(e) => setParams({ date_to: e.target.value || undefined })}
                className="w-full px-2.5 py-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
          </div>
        )}

        {activeFilterCount > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-4">
            {scoreFilter && scoreTierLabels[scoreFilter] && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                Score: {scoreTierLabels[scoreFilter]}
                <button onClick={() => setParams({ score: undefined })} className="ml-0.5 hover:text-blue-900">
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {tagFilter && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full bg-green-50 text-green-700 border border-green-200">
                Tag: {tagFilter}
                <button onClick={() => setParams({ tag: undefined })} className="ml-0.5 hover:text-green-900">
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {sourceFilter && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                Source: {sourceLabels[sourceFilter] ?? sourceFilter}
                <button onClick={() => setParams({ source: undefined })} className="ml-0.5 hover:text-purple-900">
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
                const params = new URLSearchParams();
                router.replace("/contacts", { scroll: false });
              }}
              className="text-xs text-gray-500 hover:text-gray-700 underline"
            >
              Clear all
            </button>
          </div>
        )}

        {isLoading && (
          <div className="text-center py-12 text-gray-400">Loading contacts...</div>
        )}

        {isError && (
          <div className="text-center py-12 text-red-500">
            Failed to load contacts. Is the backend running?
          </div>
        )}

        {!isLoading && !isError && contacts.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No contacts found.
          </div>
        )}

        {contacts.length > 0 && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Company</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Score</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Last Interaction</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {contacts.map((contact) => {
                  const name =
                    contact.full_name ??
                    [contact.given_name, contact.family_name].filter(Boolean).join(" ") ??
                    "Unnamed";
                  return (
                    <tr key={contact.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <Link
                          href={`/contacts/${contact.id}`}
                          className="flex items-center gap-2 text-blue-600 hover:text-blue-800 font-medium"
                        >
                          <UserCircle className="w-5 h-5 text-gray-400" />
                          {name}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {contact.company ?? "-"}
                      </td>
                      <td className="px-4 py-3">
                        <ScoreBadge score={contact.relationship_score} />
                      </td>
                      <td className="px-4 py-3 text-gray-500">
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
              className="px-3 py-1.5 text-sm rounded-md border border-gray-300 disabled:opacity-40 hover:bg-gray-100"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">
              Page {page} of {meta.total_pages}
            </span>
            <button
              disabled={page >= meta.total_pages}
              onClick={() => setParams({ page: String(page + 1) })}
              className="px-3 py-1.5 text-sm rounded-md border border-gray-300 disabled:opacity-40 hover:bg-gray-100"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
