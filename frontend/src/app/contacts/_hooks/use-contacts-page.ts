"use client";

import { useCallback, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useContacts } from "@/hooks/use-contacts";
import { client } from "@/lib/api-client";

export function useContactsPage() {
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
  const includeArchived = searchParams.get("include_archived") === "1";
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
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    include_archived: includeArchived || undefined,
    sort: sortParam,
  });

  const contacts = data?.data ?? [];
  const meta = data?.meta;
  const activeFilterCount = [tagFilter, sourceFilter, dateFrom, dateTo, scoreFilter, priorityFilter, includeArchived].filter(Boolean).length;
  const stats = statsQuery.data?.total != null ? statsQuery.data : null;
  const activeRelationships = stats ? (stats.strong ?? 0) + (stats.active ?? 0) : 0;

  // Bulk mutations
  const bulkUpdate = useMutation({
    mutationFn: async (body: {
      contact_ids: string[];
      add_tags?: string[];
      remove_tags?: string[];
      priority_level?: string;
      company?: string;
    }) => {
      const { data, error } = await client.POST("/api/v1/contacts/bulk-update", { body });
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
        await client.POST("/api/v1/contacts/{contact_id}/merge/{other_id}", {
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

  const [selectingAll, setSelectingAll] = useState(false);
  const totalCount = meta?.total ?? contacts.length;

  const toggleSelectAll = async () => {
    if (selectedIds.size > 0) {
      setSelectedIds(new Set());
      return;
    }
    // Fetch ALL matching IDs across all pages
    setSelectingAll(true);
    try {
      const { data: idsData } = await client.GET("/api/v1/contacts/ids", {
        params: {
          query: {
            search: search || undefined,
            tag: tagFilter || undefined,
            source: sourceFilter || undefined,
            score: scoreFilter || undefined,
            priority: priorityFilter || undefined,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
            include_archived: includeArchived || undefined,
          },
        },
      });
      const allIds: string[] = idsData?.data ?? [];
      setSelectedIds(new Set(allIds));
    } finally {
      setSelectingAll(false);
    }
  };

  const selectedArray = Array.from(selectedIds);
  const isPending = bulkUpdate.isPending || mergeMutation.isPending || deleteMutation.isPending;

  return {
    // URL state
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
