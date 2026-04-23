import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { client } from "@/lib/api-client";

export type Bbox = {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
}

export function useViewportContacts(bbox: Bbox | null) {
  return useQuery({
    queryKey: ["contacts", "map", bbox],
    enabled: bbox !== null,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      if (!bbox) return { data: [], meta: { total_in_bounds: 0 } };
      const param = `${bbox.minLng},${bbox.minLat},${bbox.maxLng},${bbox.maxLat}`;
      const { data } = await client.GET("/api/v1/contacts/map", {
        params: { query: { bbox: param, limit: 500 } },
      });
      return data ?? { data: [], meta: { total_in_bounds: 0 } };
    },
  });
}
