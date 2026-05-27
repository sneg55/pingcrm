import { useQuery } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
import type { OverdueContact } from "@/hooks/use-dashboard";

type ContactStats = {
  total: number;
  strong: number;
  active: number;
  dormant: number;
  interactions_this_week: number;
  interactions_last_week: number;
  active_last_week: number;
};

const DASHBOARD_REFETCH_MS = 5 * 60 * 1000; // 5 minutes

function mapStats(raw: ContactStats | undefined) {
  return {
    total: raw?.total ?? 0,
    active: raw?.active ?? 0,
    strong: raw?.strong ?? 0,
    dormant: raw?.dormant ?? 0,
    interactionsThisWeek: raw?.interactions_this_week ?? 0,
    interactionsLastWeek: raw?.interactions_last_week ?? 0,
    activeLastWeek: raw?.active_last_week ?? 0,
  };
}

export function useDashboardContacts() {
  const statsQuery = useQuery({
    queryKey: ["contacts", "stats"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/stats");
      return data ?? null;
    },
    refetchInterval: DASHBOARD_REFETCH_MS,
  });

  const overdueQuery = useQuery({
    queryKey: ["contacts", "overdue"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/overdue", {
        params: { query: { limit: 5 } },
      });
      return data ?? { data: [], error: null };
    },
    refetchInterval: DASHBOARD_REFETCH_MS,
  });

  return {
    statsReady: statsQuery.data?.data != null,
    stats: mapStats(statsQuery.data?.data as ContactStats | undefined),
    overdueContacts: (overdueQuery.data?.data ?? []) as OverdueContact[],
    isLoading: statsQuery.isLoading || overdueQuery.isLoading,
    isError: statsQuery.isError || overdueQuery.isError,
  };
}
