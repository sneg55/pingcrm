"use client";

export const dynamic = "force-dynamic";

import { Suspense, useState, useCallback, useRef, useMemo, memo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Search, Building2, CheckSquare, GitMerge, Trash2, BarChart3, MessageSquare, Clock, Users, ArrowDown, ArrowUpDown } from "lucide-react";
import Link from "next/link";
import { client } from "@/lib/api-client";
import { formatDistanceToNow } from "date-fns";

const EMPTY_SET = new Set<string>();

type SortKey = "name" | "contacts" | "score" | "interactions" | "activity";

interface Organization {
  id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  location: string | null;
  website: string | null;
  linkedin_url: string | null;
  twitter_handle: string | null;
  notes: string | null;
  contact_count: number;
  avg_relationship_score: number;
  total_interactions: number;
  last_interaction_at: string | null;
}

/* ── Favicon helper ── */

const OrgIcon = memo(function OrgIcon({ domain }: { domain: string | null }) {
  const [failed, setFailed] = useState(false);
  if (!domain || failed) {
    return <Building2 className="w-4 h-4 text-blue-600" />;
  }
  return (
    <img
      src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`}
      alt=""
      className="w-5 h-5 rounded-sm"
      onError={() => setFailed(true)}
    />
  );
});

/* ── Merge Modal ── */

function MergeModal({
  orgs,
  onMerge,
  onClose,
  isPending,
}: {
  orgs: Organization[];
  onMerge: (targetId: string) => void;
  onClose: () => void;
  isPending: boolean;
}) {
  const [targetId, setTargetId] = useState(orgs[0]?.id ?? "");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-4">
          <GitMerge className="w-5 h-5 text-blue-600" />
          <h2 className="text-lg font-bold text-gray-900">Merge Organizations</h2>
        </div>

        <p className="text-sm text-gray-600 mb-4">
          All contacts from the selected organizations will be moved under one organization. Select which to keep:
        </p>

        <div className="mb-5">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Keep as target organization:
          </label>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {orgs.map((org) => (
              <label
                key={org.id}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border cursor-pointer transition-colors ${
                  targetId === org.id
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 hover:bg-gray-50"
                }`}
              >
                <input
                  type="radio"
                  name="target"
                  checked={targetId === org.id}
                  onChange={() => setTargetId(org.id)}
                  className="text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-900">{org.name}</span>
                <span className="text-xs text-gray-400 ml-auto">{org.contact_count} contacts</span>
              </label>
            ))}
          </div>
        </div>

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => targetId && onMerge(targetId)}
            disabled={!targetId || isPending}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            <GitMerge className="w-4 h-4" />
            {isPending ? "Merging..." : "Merge"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Bulk Action Bar ── */

function BulkActionBar({
  selectedCount,
  onMergeOrgs,
  onDeleteOrgs,
  onClear,
  isPending,
}: {
  selectedCount: number;
  onMergeOrgs: () => void;
  onDeleteOrgs: () => void;
  onClear: () => void;
  isPending: boolean;
}) {
  return (
    <div className="sticky top-14 z-30 bg-blue-600 text-white px-4 py-2.5 rounded-lg mb-4 flex items-center gap-3 shadow-lg">
      <div className="flex items-center gap-2 flex-shrink-0">
        <CheckSquare className="w-4 h-4" />
        <span className="text-sm font-medium">{selectedCount} selected</span>
      </div>

      <div className="h-5 w-px bg-blue-400" />

      {selectedCount >= 2 && (
        <button
          onClick={onMergeOrgs}
          disabled={isPending}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-blue-500 hover:bg-blue-400 transition-colors disabled:opacity-50"
        >
          <GitMerge className="w-3 h-3" />
          Merge {selectedCount} Orgs
        </button>
      )}

      <button
        onClick={onDeleteOrgs}
        disabled={isPending}
        className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md bg-red-500/80 hover:bg-red-500 transition-colors disabled:opacity-50"
      >
        <Trash2 className="w-3 h-3" />
        Delete
      </button>

      <div className="flex-1" />

      <button
        onClick={onClear}
        className="text-xs text-blue-200 hover:text-white underline"
      >
        Clear selection
      </button>
    </div>
  );
}

/* ── Main Content ── */

function OrganizationsPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchFromUrl = searchParams.get("q") ?? "";
  const [searchInput, setSearchInput] = useState(searchFromUrl);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const page = Number(searchParams.get("page") ?? "1");

  const [selectedOrgIds, setSelectedOrgIds] = useState<Set<string>>(EMPTY_SET);
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("name");

  const setParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value) params.set(key, value);
        else params.delete(key);
      }
      if (!("page" in updates)) params.delete("page");
      router.replace(`/organizations?${params.toString()}`, { scroll: false });
    },
    [searchParams, router]
  );

  const { data, isLoading, isError } = useQuery({
    queryKey: ["organizations", searchFromUrl, page],
    queryFn: async () => {
      const params: Record<string, string> = { page: String(page), page_size: "50" };
      if (searchFromUrl) params.search = searchFromUrl;
      const { data } = await client.GET("/api/v1/organizations" as any, {
        params: { query: params },
      });
      return data as { data: Organization[]; meta: { total: number; page: number; page_size: number; total_pages: number } };
    },
  });

  const organizations = data?.data ?? [];
  const meta = data?.meta;

  const sortedOrganizations = useMemo(() => {
    const sorted = [...organizations];
    switch (sortKey) {
      case "name": sorted.sort((a, b) => a.name.localeCompare(b.name)); break;
      case "contacts": sorted.sort((a, b) => b.contact_count - a.contact_count); break;
      case "score": sorted.sort((a, b) => b.avg_relationship_score - a.avg_relationship_score); break;
      case "interactions": sorted.sort((a, b) => b.total_interactions - a.total_interactions); break;
      case "activity": sorted.sort((a, b) => {
        const aT = a.last_interaction_at ? new Date(a.last_interaction_at).getTime() : 0;
        const bT = b.last_interaction_at ? new Date(b.last_interaction_at).getTime() : 0;
        return bT - aT;
      }); break;
    }
    return sorted;
  }, [organizations, sortKey]);

  const mergeOrgs = useMutation({
    mutationFn: async (body: { source_ids: string[]; target_id: string }) => {
      const { data, error } = await client.POST("/api/v1/organizations/merge" as any, { body });
      if (error) throw new Error((error as { detail?: string })?.detail ?? "Merge failed");
      return data;
    },
    onSuccess: () => {
      setSelectedOrgIds(EMPTY_SET);
      setShowMergeModal(false);
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
  });

  const deleteOrg = useMutation({
    mutationFn: async (orgId: string) => {
      const { error } = await client.DELETE("/api/v1/organizations/{org_id}" as any, {
        params: { path: { org_id: orgId } },
      });
      if (error) throw new Error((error as { detail?: string })?.detail ?? "Delete failed");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
  });

  const toggleSelectOrg = (orgId: string) => {
    setSelectedOrgIds((prev) => {
      const next = new Set(prev);
      if (next.has(orgId)) next.delete(orgId);
      else next.add(orgId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedOrgIds.size === organizations.length) {
      setSelectedOrgIds(EMPTY_SET);
    } else {
      setSelectedOrgIds(new Set(organizations.map((o) => o.id)));
    }
  };

  const handleDeleteSelected = async () => {
    const count = selectedOrgIds.size;
    if (!confirm(`Delete ${count} organization${count > 1 ? "s" : ""}? Contacts will be unlinked but not deleted.`)) return;
    await Promise.all(
      Array.from(selectedOrgIds).map((id) => deleteOrg.mutateAsync(id))
    );
    setSelectedOrgIds(EMPTY_SET);
  };

  const handleDeleteSingle = (org: Organization) => {
    if (!confirm(`Delete "${org.name}"? Contacts will be unlinked but not deleted.`)) return;
    deleteOrg.mutate(org.id);
    setSelectedOrgIds((prev) => { const next = new Set(prev); next.delete(org.id); return next; });
  };

  const selectedMergeOrgs = organizations.filter((o) => selectedOrgIds.has(o.id));

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Organizations</h1>
            {meta && (
              <p className="text-sm text-gray-500 mt-0.5">
                {meta.total} organization{meta.total !== 1 ? "s" : ""}
              </p>
            )}
          </div>
        </div>

        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search organizations..."
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
        </div>

        {/* Bulk action bar */}
        {selectedOrgIds.size > 0 && (
          <BulkActionBar
            selectedCount={selectedOrgIds.size}
            isPending={mergeOrgs.isPending || deleteOrg.isPending}
            onMergeOrgs={() => setShowMergeModal(true)}
            onDeleteOrgs={handleDeleteSelected}
            onClear={() => setSelectedOrgIds(EMPTY_SET)}
          />
        )}

        {showMergeModal && selectedMergeOrgs.length >= 2 && (
          <MergeModal
            orgs={selectedMergeOrgs}
            isPending={mergeOrgs.isPending}
            onMerge={(targetId) => {
              const sourceIds = selectedMergeOrgs.map((o) => o.id).filter((id) => id !== targetId);
              mergeOrgs.mutate({ source_ids: sourceIds, target_id: targetId });
            }}
            onClose={() => setShowMergeModal(false)}
          />
        )}

        {isLoading && (
          <div className="text-center py-12 text-gray-400">Loading organizations...</div>
        )}

        {isError && (
          <div className="text-center py-12 text-red-500">
            Failed to load organizations.
          </div>
        )}

        {!isLoading && !isError && organizations.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No organizations found.
          </div>
        )}

        {organizations.length > 0 && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selectedOrgIds.size === organizations.length && organizations.length > 0}
                      ref={(el) => {
                        if (el) el.indeterminate = selectedOrgIds.size > 0 && selectedOrgIds.size < organizations.length;
                      }}
                      onChange={toggleSelectAll}
                      className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      aria-label="Select all organizations"
                    />
                  </th>
                  {([
                    { key: "name" as SortKey, label: "Organization", align: "text-left", icon: null },
                    { key: "contacts" as SortKey, label: "Contacts", align: "text-center", icon: Users },
                    { key: "score" as SortKey, label: "Avg Score", align: "text-center", icon: BarChart3 },
                    { key: "interactions" as SortKey, label: "Interactions", align: "text-center", icon: MessageSquare },
                    { key: "activity" as SortKey, label: "Last Activity", align: "text-right", icon: null },
                  ]).map((col) => (
                    <th
                      key={col.key}
                      className={`px-4 py-3 font-medium ${col.align} cursor-pointer select-none hover:text-blue-600 transition-colors group`}
                      onClick={() => setSortKey(col.key)}
                    >
                      <span className="inline-flex items-center gap-1">
                        {col.icon ? <col.icon className="w-3.5 h-3.5" /> : col.label}
                        {sortKey === col.key ? (
                          <ArrowDown className="w-3 h-3" />
                        ) : (
                          <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                        )}
                      </span>
                    </th>
                  ))}
                  <th className="w-10 px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {sortedOrganizations.map((org) => {
                  const isSelected = selectedOrgIds.has(org.id);
                  return (
                    <tr key={org.id} className={`hover:bg-gray-50 transition-colors ${isSelected ? "bg-blue-50/50" : ""}`}>
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectOrg(org.id)}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          aria-label={`Select ${org.name}`}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/organizations/${org.id}`}
                          className="flex items-center gap-3 group"
                        >
                          <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0 overflow-hidden">
                            <OrgIcon domain={org.domain} />
                          </div>
                          <div className="min-w-0">
                            <span className="text-sm font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                              {org.name}
                            </span>
                            {org.domain && (
                              <span className="ml-2 text-xs text-gray-400">{org.domain}</span>
                            )}
                          </div>
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-center text-sm text-gray-600">
                        {org.contact_count}
                      </td>
                      <td className="px-4 py-3 text-center text-sm text-gray-600">
                        {org.avg_relationship_score || "-"}
                      </td>
                      <td className="px-4 py-3 text-center text-sm text-gray-600">
                        {org.total_interactions || "-"}
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-gray-400">
                        {org.last_interaction_at
                          ? formatDistanceToNow(new Date(org.last_interaction_at), { addSuffix: true })
                          : "Never"}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => handleDeleteSingle(org)}
                          className="p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                          title={`Delete ${org.name}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
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

function PageLoading() {
  return <div className="min-h-screen bg-stone-50 flex items-center justify-center"><div className="animate-spin h-8 w-8 border-4 border-teal-500 border-t-transparent rounded-full" /></div>;
}

export default function OrganizationsPage() {
  return <Suspense fallback={<PageLoading />}><OrganizationsPageContent /></Suspense>;
}
