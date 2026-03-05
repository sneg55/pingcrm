import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient, { type ApiResponse } from "@/lib/api";

export interface IdentityMatchContact {
  id: string;
  full_name: string | null;
  emails: string[];
  company: string | null;
  twitter_handle: string | null;
  telegram_username: string | null;
}

export interface IdentityMatch {
  id: string;
  contact_a: IdentityMatchContact;
  contact_b: IdentityMatchContact;
  match_score: number;
  match_method: string;
  status: "pending" | "merged" | "rejected";
  created_at: string;
}

export function useIdentityMatches() {
  return useQuery({
    queryKey: ["identity", "matches"],
    queryFn: async () => {
      const { data } = await apiClient.get<ApiResponse<IdentityMatch[]>>(
        "/identity/matches"
      );
      return data;
    },
  });
}

export function useMergeMatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (matchId: string) => {
      const { data } = await apiClient.post<ApiResponse<{ merged_contact_id: string }>>(
        `/identity/matches/${matchId}/merge`
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["identity"] });
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });
}

export function useRejectMatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (matchId: string) => {
      const { data } = await apiClient.post<ApiResponse<IdentityMatch>>(
        `/identity/matches/${matchId}/reject`
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["identity"] });
    },
  });
}

export function useScanIdentity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<ApiResponse<{ matches_found: number }>>(
        "/identity/scan"
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["identity"] });
    },
  });
}
