import { useQuery } from "@tanstack/react-query";
import { client } from "@/lib/api-client";

export type SyncProgress = {
  active: boolean;
  phase?: string;
  total_dialogs?: number;
  dialogs_processed?: number;
  batches_total?: number;
  batches_completed?: number;
  contacts_found?: number;
  messages_synced?: number;
  started_at?: string;
}

export function useTelegramSyncProgress() {
  return useQuery({
    queryKey: ["telegram-sync-progress"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/telegram/sync-progress", {});
      const raw = (data as { data?: Record<string, unknown> } | undefined)?.data;
      if (!raw?.active) return { active: false } as SyncProgress;
      const toInt = (v: unknown) => {
        const n = typeof v === "string" ? parseInt(v) : typeof v === "number" ? v : NaN;
        return Number.isFinite(n) ? n : 0;
      };
      return {
        active: raw.active === true || raw.active === "true",
        phase: typeof raw.phase === "string" ? raw.phase : undefined,
        total_dialogs: toInt(raw.total_dialogs),
        dialogs_processed: toInt(raw.dialogs_processed),
        batches_total: toInt(raw.batches_total),
        batches_completed: toInt(raw.batches_completed),
        contacts_found: toInt(raw.contacts_found),
        messages_synced: toInt(raw.messages_synced),
        started_at: typeof raw.started_at === "string" ? raw.started_at : undefined,
      } as SyncProgress;
    },
    refetchInterval: (query) => {
      const data = query.state.data as SyncProgress | undefined;
      return data?.active ? 3000 : false; // Poll every 3s when active
    },
  });
}
