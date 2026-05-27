import type { Suggestion } from "@/hooks/use-suggestions";
import { useDashboardSuggestions } from "@/hooks/use-dashboard-suggestions";
import { useDashboardContacts } from "@/hooks/use-dashboard-contacts";
import { useDashboardActivity } from "@/hooks/use-dashboard-activity";

export type OverdueContact = {
  id: string;
  full_name: string | null;
  given_name: string | null;
  family_name: string | null;
  avatar_url: string | null;
  priority_level: string | null;
  last_interaction_at: string | null;
  days_overdue: number;
  relationship_score: number | null;
};

export type ActivityEvent = {
  type: string;
  contact_name: string;
  contact_id: string;
  contact_avatar_url: string | null;
  platform: string;
  direction: string;
  content_preview: string | null;
  timestamp: string;
};

export function useDashboardStats() {
  const suggestionsResult = useDashboardSuggestions();
  const contactsResult = useDashboardContacts();
  const activityResult = useDashboardActivity();

  const isLoading =
    suggestionsResult.isLoading ||
    contactsResult.isLoading ||
    activityResult.isLoading;

  const isError =
    suggestionsResult.isError ||
    contactsResult.isError ||
    activityResult.isError;

  return {
    suggestions: suggestionsResult.suggestions as Suggestion[],
    statsReady: contactsResult.statsReady,
    stats: contactsResult.stats,
    overdueContacts: contactsResult.overdueContacts,
    recentActivity: activityResult.recentActivity,
    isLoading,
    isError,
  };
}
