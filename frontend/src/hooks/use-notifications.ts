import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/lib/api-client";

export type AppNotification = {
  id: string;
  notification_type: string;
  title: string;
  body: string | null;
  read: boolean;
  link: string | null;
  created_at: string | null;
}

type NotificationsResponse = {
  data: AppNotification[];
  error: string | null;
  meta: { total: number; page: number; page_size: number; total_pages: number };
}

export function useNotifications(page = 1) {
  return useQuery<NotificationsResponse | null>({
    queryKey: ["notifications", page],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/notifications", {
        params: { query: { page, page_size: 20 } },
      });
      return (data as NotificationsResponse | undefined) ?? null;
    },
  });
}

export function useUnreadCount() {
  return useQuery<{ data: { count: number } } | null>({
    queryKey: ["notifications", "unread-count"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/notifications/unread-count");
      return (data as { data: { count: number } } | undefined) ?? null;
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await client.PUT(
        "/api/v1/notifications/{notification_id}/read",
        { params: { path: { notification_id: id } } }
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await client.PUT("/api/v1/notifications/read-all");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
