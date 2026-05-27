"use client";

import { useCallback, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";

export function useContactsUrlState() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const searchFromUrl = searchParams.get("q") ?? "";
  const [searchInput, setSearchInput] = useState(searchFromUrl);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const search = searchFromUrl;
  const page = Number(searchParams.get("page") ?? "1");
  const scoreFilter = searchParams.get("score") ?? undefined;
  const priorityFilter = searchParams.get("priority") ?? undefined;
  const tagFilter = searchParams.get("tag") ?? "";
  const sourceFilter = searchParams.get("source") ?? "";
  const interactionFrom = searchParams.get("interaction_from") ?? "";
  const interactionTo = searchParams.get("interaction_to") ?? "";
  const includeArchived = searchParams.get("include_archived") === "1";
  const sortParam = searchParams.get("sort") ?? "score";
  const showFilters = searchParams.get("filters") === "1";
  const ghostedFilter = searchParams.get("ghosted") === "true";

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

  return {
    searchInput,
    setSearchInput,
    debounceRef,
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
    showFilters,
    ghostedFilter,
    setParams,
    router,
  };
}
