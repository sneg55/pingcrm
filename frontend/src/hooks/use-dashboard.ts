import { useQuery } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
import type { Suggestion } from "@/hooks/use-suggestions";

interface ContactStats {
  total: number;
  strong: number;
  active: number;
  dormant: number;
  interactions_this_week: number;
}

export interface OverdueContact {
  id: string;
  full_name: string | null;
  given_name: string | null;
  family_name: string | null;
  avatar_url: string | null;
  priority_level: string | null;
  last_interaction_at: string | null;
  days_overdue: number;
  relationship_score: number | null;
}

export interface ActivityEvent {
  type: string;
  contact_name: string;
  contact_id: string;
  contact_avatar_url: string | null;
  platform: string;
  direction: string;
  content_preview: string | null;
  timestamp: string;
}

export function useDashboardStats() {
  const suggestionsQuery = useQuery({
    queryKey: ["suggestions"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/suggestions");
      return data;
    },
  });

  const statsQuery = useQuery({
    queryKey: ["contacts", "stats"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/stats");
      return data;
    },
  });

  const overdueQuery = useQuery({
    queryKey: ["contacts", "overdue"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/overdue" as any, {
        params: { query: { limit: 5 } },
      });
      return data;
    },
  });

  const activityQuery = useQuery({
    queryKey: ["activity", "recent"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/activity/recent" as any, {
        params: { query: { limit: 5 } },
      });
      return data;
    },
  });

  const suggestions = (suggestionsQuery.data?.data ?? []) as Suggestion[];
  const stats = statsQuery.data?.data as ContactStats | undefined;
  const overdueContacts = (overdueQuery.data?.data ?? []) as OverdueContact[];
  const recentActivity = (activityQuery.data?.data ?? []) as ActivityEvent[];

  const isLoading =
    suggestionsQuery.isLoading ||
    statsQuery.isLoading ||
    overdueQuery.isLoading ||
    activityQuery.isLoading;

  const isError =
    suggestionsQuery.isError || statsQuery.isError ||
    overdueQuery.isError || activityQuery.isError;

  return {
    suggestions,
    stats: {
      total: stats?.total ?? 0,
      active: stats?.active ?? 0,
      strong: stats?.strong ?? 0,
      dormant: stats?.dormant ?? 0,
      interactionsThisWeek: stats?.interactions_this_week ?? 0,
    },
    overdueContacts,
    recentActivity,
    isLoading,
    isError,
  };
}
