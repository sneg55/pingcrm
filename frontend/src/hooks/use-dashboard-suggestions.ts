import { useQuery } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
import type { Suggestion } from "@/hooks/use-suggestions";

const DASHBOARD_REFETCH_MS = 5 * 60 * 1000; // 5 minutes

export function useDashboardSuggestions() {
  const suggestionsQuery = useQuery({
    queryKey: ["suggestions"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/suggestions");
      return data ?? null;
    },
    refetchInterval: DASHBOARD_REFETCH_MS,
  });

  return {
    suggestions: (suggestionsQuery.data?.data ?? []) as unknown as Suggestion[],
    isLoading: suggestionsQuery.isLoading,
    isError: suggestionsQuery.isError,
  };
}
