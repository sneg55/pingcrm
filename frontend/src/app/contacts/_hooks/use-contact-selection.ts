"use client";

import { useState } from "react";
import { client } from "@/lib/api-client";

interface UseContactSelectionParams {
  search: string | undefined;
  tagFilter: string;
  sourceFilter: string;
  scoreFilter: string | undefined;
  priorityFilter: string | undefined;
  interactionFrom: string;
  interactionTo: string;
  ghostedFilter: boolean;
  includeArchived: boolean;
}

export function useContactSelection({
  search,
  tagFilter,
  sourceFilter,
  scoreFilter,
  priorityFilter,
  interactionFrom,
  interactionTo,
  ghostedFilter,
  includeArchived,
}: UseContactSelectionParams) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectingAll, setSelectingAll] = useState(false);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = async () => {
    if (selectedIds.size > 0) {
      setSelectedIds(new Set());
      return;
    }
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
            interaction_from: interactionFrom || undefined,
            interaction_to: interactionTo || undefined,
            ghosted: ghostedFilter || undefined,
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

  return {
    selectedIds,
    setSelectedIds,
    selectingAll,
    toggleSelect,
    toggleSelectAll,
  };
}
