import { useQuery } from "@tanstack/react-query";
import apiClient, { type ApiResponse } from "@/lib/api";
import type { Contact } from "@/hooks/use-contacts";
import type { Suggestion } from "@/hooks/use-suggestions";

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
    queryKey: ["contacts", { page: 1, page_size: 20 }],
    queryFn: async () => {
      const { data } = await apiClient.get<ApiResponse<Contact[]>>("/contacts", {
        params: { page: 1, page_size: 20 },
      });
      return data;
    },
  });

  const suggestions = suggestionsQuery.data?.data ?? [];
  const allContacts = contactsQuery.data?.data ?? [];
  const totalContacts = contactsQuery.data?.meta?.total ?? 0;

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

  const relationshipHealth = allContacts.reduce(
    (acc, contact) => {
      if (contact.relationship_score >= 8) acc.strong++;
      else if (contact.relationship_score >= 4) acc.active++;
      else acc.dormant++;
      return acc;
    },
    { strong: 0, active: 0, dormant: 0 }
  );

  const isLoading = suggestionsQuery.isLoading || contactsQuery.isLoading;
  const isError = suggestionsQuery.isError || contactsQuery.isError;

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
