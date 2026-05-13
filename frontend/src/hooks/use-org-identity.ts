import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "@/lib/api-client";

export type OrgSummary = {
  id: string;
  name: string;
  domain: string | null;
  logo_url: string | null;
  linkedin_url: string | null;
  website: string | null;
  twitter_handle: string | null;
  contact_count: number;
};

export type OrgIdentityMatch = {
  id: string;
  match_score: number;
  match_method: string;
  status: string;
  org_a: OrgSummary;
  org_b: OrgSummary;
  created_at: string;
};

export function useOrgMatches() {
  return useQuery<OrgIdentityMatch[]>({
    queryKey: ["org-matches"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/organizations/duplicates");
      return (data?.data ?? []) as OrgIdentityMatch[];
    },
    staleTime: 30 * 1000,
  });
}

export function useScanOrgs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await client.POST("/api/v1/organizations/scan-duplicates");
      return data?.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["org-matches"] });
      void qc.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
}

export function useMergeOrgMatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ matchId, targetId }: { matchId: string; targetId: string }) => {
      const { data, error } = await client.POST(
        "/api/v1/organizations/duplicates/{match_id}/merge",
        {
          params: { path: { match_id: matchId } },
          body: { target_id: targetId },
        },
      );
      if (error) throw new Error("Merge failed");
      return data?.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["org-matches"] });
      void qc.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
}

export function useDismissOrgMatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (matchId: string) => {
      const { data, error } = await client.POST(
        "/api/v1/organizations/duplicates/{match_id}/dismiss",
        { params: { path: { match_id: matchId } } },
      );
      if (error) throw new Error("Dismiss failed");
      return data?.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["org-matches"] });
    },
  });
}
