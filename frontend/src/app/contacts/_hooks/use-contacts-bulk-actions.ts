"use client";

import { useQueryClient, useMutation } from "@tanstack/react-query";
import { client } from "@/lib/api-client";

interface UseContactsBulkActionsParams {
  onSuccess: () => void;
}

export function useContactsBulkActions({ onSuccess }: UseContactsBulkActionsParams) {
  const queryClient = useQueryClient();

  const bulkUpdate = useMutation({
    mutationFn: async (body: {
      contact_ids: string[];
      add_tags?: string[];
      remove_tags?: string[];
      priority_level?: string;
      company?: string;
    }) => {
      const { data, error } = await client.POST("/api/v1/contacts/bulk-update", { body });
      if (error) throw new Error((error as { detail?: string })?.detail ?? "Bulk update failed");
      return data;
    },
    onSuccess: () => {
      onSuccess();
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
      void queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });

  const mergeMutation = useMutation({
    mutationFn: async (contactIds: string[]) => {
      const [primaryId, ...otherIds] = contactIds;
      for (const otherId of otherIds) {
        await client.POST("/api/v1/contacts/{contact_id}/merge/{other_id}", {
          params: { path: { contact_id: primaryId, other_id: otherId } },
        });
      }
    },
    onSuccess: () => {
      onSuccess();
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (contactIds: string[]) => {
      for (const id of contactIds) {
        await client.DELETE("/api/v1/contacts/{contact_id}", {
          params: { path: { contact_id: id } },
        });
      }
    },
    onSuccess: () => {
      onSuccess();
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });

  const isPending = bulkUpdate.isPending || mergeMutation.isPending || deleteMutation.isPending;

  return {
    bulkUpdate,
    mergeMutation,
    deleteMutation,
    isPending,
  };
}
