"use client";

import { useQuery } from "@tanstack/react-query";
import { useContacts } from "@/hooks/use-contacts";
import { client } from "@/lib/api-client";
import { useContactsUrlState } from "./use-contacts-url-state";
import { useContactSelection } from "./use-contact-selection";
import { useContactsBulkActions } from "./use-contacts-bulk-actions";

export function useContactsPage() {
  const urlState = useContactsUrlState();
  const {
    search,
    page,
    scoreFilter,
    priorityFilter,
    tagFilter,
    sourceFilter,
    interactionFrom,
    interactionTo,
    includeArchived,
    sortParam,
    ghostedFilter,
  } = urlState;

  // Data queries
  const { data: allTags = [] } = useQuery({
    queryKey: ["tags"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/tags", {});
      return (data?.data as string[]) ?? [];
    },
  });

  const statsQuery = useQuery({
    queryKey: ["contacts", "stats"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/stats", {});
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
    interaction_from: interactionFrom || undefined,
    interaction_to: interactionTo || undefined,
    ghosted: ghostedFilter || undefined,
    include_archived: includeArchived || undefined,
    sort: sortParam,
  });

  const contacts = data?.data ?? [];
  const meta = data?.meta;
  const activeFilterCount = [tagFilter, sourceFilter, interactionFrom, interactionTo, scoreFilter, priorityFilter, includeArchived, ghostedFilter].filter(Boolean).length;
  const stats = statsQuery.data?.total != null ? statsQuery.data : null;
  const activeRelationships = stats ? (stats.strong ?? 0) + (stats.active ?? 0) : 0;
  const totalCount = meta?.total ?? contacts.length;

  // Selection sub-hook
  const {
    selectedIds,
    setSelectedIds,
    selectingAll,
    toggleSelect,
    toggleSelectAll,
  } = useContactSelection({
    search: search || undefined,
    tagFilter,
    sourceFilter,
    scoreFilter,
    priorityFilter,
    interactionFrom,
    interactionTo,
    ghostedFilter,
    includeArchived,
  });

  // Bulk actions sub-hook
  const { bulkUpdate, mergeMutation, deleteMutation, isPending } = useContactsBulkActions({
    onSuccess: () => setSelectedIds(new Set()),
  });

  const selectedArray = Array.from(selectedIds);

  return {
    // URL state
    ...urlState,
    // Queries
    allTags,
    isLoading,
    isError,
    // Derived
    contacts,
    meta,
    activeFilterCount,
    stats,
    activeRelationships,
    totalCount,
    // Selection
    selectedIds,
    setSelectedIds,
    selectedArray,
    selectingAll,
    toggleSelect,
    toggleSelectAll,
    // Mutations
    bulkUpdate,
    mergeMutation,
    deleteMutation,
    isPending,
  };
}
