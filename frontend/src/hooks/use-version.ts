import { useQuery } from "@tanstack/react-query";

import { client } from "@/lib/api-client";

export type VersionStatus = {
  current: string;
  latest: string | null;
  release_url: string | null;
  release_notes: string | null;
  update_available: boolean | null;
  checked_at: string | null;
  disabled: boolean;
};

export function useVersion() {
  return useQuery<VersionStatus | null>({
    queryKey: ["version"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/version");
      if (!data?.data) return null;
      return data.data as VersionStatus;
    },
    staleTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: false,
  });
}
