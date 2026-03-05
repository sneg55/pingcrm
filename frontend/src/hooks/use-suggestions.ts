import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient, { type ApiResponse } from "@/lib/api";

export interface Suggestion {
  id: string;
  contact_id: string;
  contact_name: string | null;
  trigger_reason: string | null;
  suggested_message: string;
  suggested_channel: "email" | "telegram" | "twitter";
  status: "pending" | "sent" | "snoozed" | "dismissed";
  snooze_until: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface UpdateSuggestionInput {
  suggested_message?: string;
  suggested_channel?: "email" | "telegram" | "twitter";
  status?: "pending" | "sent" | "snoozed" | "dismissed";
  snooze_until?: string | null;
}

export function useSuggestions() {
  return useQuery({
    queryKey: ["suggestions"],
    queryFn: async () => {
      const { data } = await apiClient.get<ApiResponse<Suggestion[]>>(
        "/suggestions"
      );
      return data;
    },
  });
}

export function useUpdateSuggestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      input,
    }: {
      id: string;
      input: UpdateSuggestionInput;
    }) => {
      const { data } = await apiClient.put<ApiResponse<Suggestion>>(
        `/suggestions/${id}`,
        input
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["suggestions"] });
    },
  });
}

export function useGenerateSuggestions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<ApiResponse<Suggestion[]>>(
        "/suggestions/generate"
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["suggestions"] });
    },
  });
}
