import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface AppNotification {
  id: string;
  notification_type: string;
  title: string;
  body: string | null;
  read: boolean;
  link: string | null;
  created_at: string | null;
}

interface NotificationsResponse {
  data: AppNotification[];
  error: string | null;
  meta: { total: number; page: number; page_size: number; total_pages: number };
}

export function useNotifications(page = 1) {
  return useQuery<NotificationsResponse>({
    queryKey: ["notifications", page],
    queryFn: async () => {
      const { data } = await api.get("/notifications", { params: { page, page_size: 20 } });
      return data;
    },
  });
}

export function useUnreadCount() {
  return useQuery<{ data: { count: number } }>({
    queryKey: ["notifications", "unread-count"],
    queryFn: async () => {
      const { data } = await api.get("/notifications/unread-count");
      return data;
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.put(`/notifications/${id}/read`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.put("/notifications/read-all");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
