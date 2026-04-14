import { useQuery } from "@tanstack/react-query";
import { client } from "@/lib/api-client";

export function useMapConfig() {
  return useQuery({
    queryKey: ["map", "config"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/map/config");
      return data?.data ?? { mapbox_public_token: "" };
    },
    staleTime: 5 * 60_000,
  });
}
