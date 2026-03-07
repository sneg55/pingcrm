import { useQuery } from "@tanstack/react-query";
import apiClient, { type ApiResponse } from "@/lib/api";
import type { Contact } from "@/hooks/use-contacts";
import type { Suggestion } from "@/hooks/use-suggestions";

interface ContactStats {
  total: number;
  strong: number;
  active: number;
  dormant: number;
}

export interface DashboardStats {
  suggestions: Suggestion[];
  recentContacts: Contact[];
  totalContacts: number;
  relationshipHealth: {
    strong: number;
    active: number;
    dormant: number;
  };
}

export function useDashboardStats() {
  const suggestionsQuery = useQuery({
    queryKey: ["suggestions"],
    queryFn: async () => {
      const { data } = await apiClient.get<ApiResponse<Suggestion[]>>(
        "/suggestions"
      );
      return data;
    },
  });

  const contactsQuery = useQuery({
    queryKey: ["contacts", { page: 1, page_size: 5 }],
    queryFn: async () => {
      const { data } = await apiClient.get<ApiResponse<Contact[]>>("/contacts", {
        params: { page: 1, page_size: 5 },
      });
      return data;
    },
  });

  const statsQuery = useQuery({
    queryKey: ["contacts", "stats"],
    queryFn: async () => {
      const { data } = await apiClient.get<ApiResponse<ContactStats>>(
        "/contacts/stats"
      );
      return data;
    },
  });

  const suggestions = suggestionsQuery.data?.data ?? [];
  const allContacts = contactsQuery.data?.data ?? [];
  const stats = statsQuery.data?.data;
  const totalContacts = stats?.total ?? contactsQuery.data?.meta?.total ?? 0;

  const recentContacts = [...allContacts]
    .sort((a, b) => {
      const aTime = a.last_interaction_at
        ? new Date(a.last_interaction_at).getTime()
        : 0;
      const bTime = b.last_interaction_at
        ? new Date(b.last_interaction_at).getTime()
        : 0;
      return bTime - aTime;
    })
    .slice(0, 5);

  const relationshipHealth = stats
    ? { strong: stats.strong, active: stats.active, dormant: stats.dormant }
    : { strong: 0, active: 0, dormant: 0 };

  const isLoading =
    suggestionsQuery.isLoading || contactsQuery.isLoading || statsQuery.isLoading;
  const isError =
    suggestionsQuery.isError || contactsQuery.isError || statsQuery.isError;

  return {
    data: {
      suggestions,
      recentContacts,
      totalContacts,
      relationshipHealth,
    } satisfies DashboardStats,
    isLoading,
    isError,
  };
}
