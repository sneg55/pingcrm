import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { client } from "@/lib/api-client";

export type IdentityMatchContact = {
  id: string;
  full_name: string | null;
  given_name: string | null;
  family_name: string | null;
  emails: string[];
  phones: string[];
  company: string | null;
  title: string | null;
  twitter_handle: string | null;
  telegram_username: string | null;
  linkedin_url: string | null;
  tags: string[];
  notes: string | null;
  source: string | null;
}

export type IdentityMatch = {
  id: string;
  contact_a: IdentityMatchContact;
  contact_b: IdentityMatchContact;
  match_score: number;
  match_method: string;
  status: "pending_review" | "merged" | "rejected";
  created_at: string;
}

export function useIdentityMatches() {
  return useQuery({
    queryKey: ["identity", "matches"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/identity/matches", {});
      return data;
    },
  });
}

export function useMergeMatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (matchId: string) => {
      const { data, error } = await client.POST(
        "/api/v1/identity/matches/{match_id}/merge",
        { params: { path: { match_id: matchId } } }
      );
      if (error) {
        throw new Error((error as { detail?: string }).detail ?? "Merge failed");
      }
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
      const { data, error } = await client.POST(
        "/api/v1/identity/matches/{match_id}/reject",
        { params: { path: { match_id: matchId } } }
      );
      if (error) {
        throw new Error((error as { detail?: string }).detail ?? "Reject failed");
      }
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
      const { data } = await client.POST("/api/v1/identity/scan");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["identity"] });
    },
  });
}
