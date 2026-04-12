import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  useContact,
  useUpdateContact,
  useDeleteContact,
  useContactActivity,
  type Contact,
  type ActivityData,
} from "@/hooks/use-contacts";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/lib/api-client";

export interface InteractionResponse {
  id: string;
  platform: "email" | "telegram" | "twitter" | "linkedin" | "manual" | "meeting";
  direction: "inbound" | "outbound" | "mutual" | "event";
  content_preview: string | null;
  occurred_at: string;
  is_read_by_recipient?: boolean | null;
}

export function useContactDetailController(id: string) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: contactData, isLoading, isError } = useContact(id);
  const contact = contactData?.data as Contact | undefined;
  const updateContact = useUpdateContact();
  const deleteContact = useDeleteContact();
  const { data: activityData, isLoading: activityLoading } = useContactActivity(id);

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isAutoTagging, setIsAutoTagging] = useState(false);
  const [isPromoting, setIsPromoting] = useState(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; text: string; action?: { label: string; onClick: () => void } } | null>(null);

  // Interactions query
  const { data: interactionsData, refetch: refetchInteractions } = useQuery({
    queryKey: ["interactions", id],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/{contact_id}/interactions", {
        params: { path: { contact_id: id } },
      });
      return data;
    },
    enabled: Boolean(id),
  });

  // All tags for tag picker
  const { data: allTagsData } = useQuery({
    queryKey: ["tags"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/tags", {});
      return (data?.data as string[]) ?? [];
    },
  });
  const allTags = allTagsData ?? [];

  // Background bio refresh
  useQuery({
    queryKey: ["refresh-bios", id],
    queryFn: async () => {
      await client.POST("/api/v1/contacts/{contact_id}/refresh-bios", {
        params: { path: { contact_id: id } },
      });
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      return true;
    },
    enabled: Boolean(id),
    staleTime: Infinity,
    retry: false,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  // Background email sync
  const contactEmails = contact?.emails;
  useQuery({
    queryKey: ["sync-emails", id],
    queryFn: async () => {
      const res = await client.POST("/api/v1/contacts/{contact_id}/sync-emails" as any, {
        params: { path: { contact_id: id } },
      });
      const data = (res.data as any)?.data;
      if (data?.new_interactions > 0) {
        void queryClient.invalidateQueries({ queryKey: ["interactions", id] });
        void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
        void queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] });
        void queryClient.invalidateQueries({ queryKey: ["contacts", "overdue"] });
        void queryClient.invalidateQueries({ queryKey: ["activity", "recent"] });
      }
      return true;
    },
    enabled: Boolean(id) && Boolean(contactEmails?.length),
    staleTime: Infinity,
    retry: false,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  // Background avatar refresh
  useQuery({
    queryKey: ["refresh-avatar", id],
    queryFn: async () => {
      const res = await client.POST("/api/v1/contacts/{contact_id}/refresh-avatar" as any, {
        params: { path: { contact_id: id } },
      });
      if ((res.data as any)?.data?.changed)
        void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      return true;
    },
    enabled: Boolean(id),
    staleTime: Infinity,
    retry: false,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  // Background Telegram message sync
  const contactTelegram = contact?.telegram_username || contact?.telegram_user_id;
  useQuery({
    queryKey: ["sync-telegram", id],
    queryFn: async () => {
      const res = await client.POST("/api/v1/contacts/{contact_id}/sync-telegram" as any, {
        params: { path: { contact_id: id } },
      });
      const data = (res.data as any)?.data;
      if (data?.new_interactions > 0) {
        void queryClient.invalidateQueries({ queryKey: ["interactions", id] });
        void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
        void queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] });
        void queryClient.invalidateQueries({ queryKey: ["contacts", "overdue"] });
        void queryClient.invalidateQueries({ queryKey: ["activity", "recent"] });
      }
      return true;
    },
    enabled: Boolean(id) && Boolean(contactTelegram),
    staleTime: Infinity,
    retry: false,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  const handleRefreshDetails = async () => {
    if (!id || isRefreshing) return;
    setIsRefreshing(true);
    try {
      await Promise.allSettled([
        client.POST("/api/v1/contacts/{contact_id}/refresh-bios", {
          params: { path: { contact_id: id }, query: { force: true } },
        } as any),
        client.POST("/api/v1/contacts/{contact_id}/refresh-avatar" as any, {
          params: { path: { contact_id: id }, query: { force: true } },
        }),
        ...(contactEmails?.length
          ? [
              client.POST("/api/v1/contacts/{contact_id}/sync-emails" as any, {
                params: { path: { contact_id: id }, query: { force: true } },
              }),
            ]
          : []),
        ...(contact?.telegram_username
          ? [
              client.POST("/api/v1/contacts/{contact_id}/sync-telegram" as any, {
                params: { path: { contact_id: id }, query: { force: true } },
              }),
            ]
          : []),
        ...(contact?.twitter_handle
          ? [
              client.POST("/api/v1/contacts/{contact_id}/sync-twitter" as any, {
                params: { path: { contact_id: id }, query: { force: true } },
              }),
            ]
          : []),
      ]);
      if (contact?.telegram_username) {
        await client
          .GET("/api/v1/contacts/{contact_id}/telegram/common-groups", {
            params: { path: { contact_id: id }, query: { force: true } },
          } as any)
          .catch(() => {});
      }
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      void queryClient.invalidateQueries({ queryKey: ["interactions", id] });
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleEnrich = async () => {
    if (!id || isEnriching) return;
    setIsEnriching(true);
    setToast(null);
    try {
      const res = await client.POST("/api/v1/contacts/{contact_id}/enrich" as any, {
        params: { path: { contact_id: id } },
      });
      if (res.error) {
        const detail = (res.error as any)?.detail;
        setToast({ type: "error", text: detail || "Enrichment failed" });
        return;
      }
      const data = (res.data as any)?.data;
      const fields: string[] = data?.fields_updated ?? [];
      setToast({
        type: "success",
        text: fields.length > 0 ? `Updated: ${fields.join(", ")}` : "No new data found",
      });
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
    } catch (err: any) {
      setToast({ type: "error", text: err?.message || "Enrichment failed" });
    } finally {
      setIsEnriching(false);
      setTimeout(() => setToast(null), 5000);
    }
  };

  const handleExtractBio = async () => {
    if (!id || isExtracting) return;
    setIsExtracting(true);
    setToast(null);
    try {
      const res = await client.POST("/api/v1/contacts/{contact_id}/extract-bio" as any, {
        params: { path: { contact_id: id } },
      });
      const data = (res.data as any)?.data;
      const fields: string[] = data?.fields_updated ?? [];
      setToast({
        type: "success",
        text: fields.length > 0 ? `Updated: ${fields.join(", ")}` : "No new data extracted",
      });
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
    } catch (err: any) {
      const detail = (err as any)?.detail;
      setToast({ type: "error", text: detail || err?.message || "Bio extraction failed" });
    } finally {
      setIsExtracting(false);
      setTimeout(() => setToast(null), 5000);
    }
  };

  const handleAutoTag = async () => {
    if (!id || isAutoTagging) return;
    setIsAutoTagging(true);
    setToast(null);
    try {
      const { data: json, error } = await client.POST("/api/v1/contacts/{contact_id}/auto-tag", {
        params: { path: { contact_id: id } },
      });
      if (error) {
        setToast({ type: "error", text: (error as any)?.detail || "Auto-tagging failed" });
      } else {
        const tagsAdded = (json as any)?.data?.tags_added ?? [];
        setToast({
          type: "success",
          text: tagsAdded.length > 0 ? `Added: ${tagsAdded.join(", ")}` : "No new tags",
        });
        void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
        void queryClient.invalidateQueries({ queryKey: ["tags"] });
      }
    } catch {
      setToast({ type: "error", text: "Auto-tagging failed" });
    } finally {
      setIsAutoTagging(false);
      setTimeout(() => setToast(null), 5000);
    }
  };

  const handlePromote = async () => {
    if (!id || isPromoting) return;
    setIsPromoting(true);
    setToast(null);
    try {
      const { error } = await client.POST("/api/v1/contacts/{contact_id}/promote" as any, {
        params: { path: { contact_id: id } },
      });
      if (error) {
        setToast({ type: "error", text: (error as any)?.detail || "Failed to promote contact" });
      } else {
        setToast({ type: "success", text: "Contact promoted to 1st Tier" });
        void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
        void queryClient.invalidateQueries({ queryKey: ["tags"] });
      }
    } catch {
      setToast({ type: "error", text: "Failed to promote contact" });
    } finally {
      setIsPromoting(false);
      setTimeout(() => setToast(null), 5000);
    }
  };

  const handleDelete = () => {
    deleteContact.mutate(id, { onSuccess: () => router.push("/contacts") });
  };

  const addNoteMutation = useMutation({
    mutationFn: async (content: string) => {
      await client.POST("/api/v1/contacts/{contact_id}/interactions", {
        params: { path: { contact_id: id } },
        body: {
          platform: "manual",
          direction: "outbound",
          content_preview: content,
          occurred_at: new Date().toISOString(),
        },
      });
    },
    onSuccess: () => void refetchInteractions(),
  });

  const interactions = (interactionsData?.data ?? []) as InteractionResponse[];

  return {
    contact,
    interactions,
    activityData: activityData as ActivityData | undefined,
    activityLoading,
    allTags,
    isLoading,
    isError,
    isRefreshing,
    isEnriching,
    isExtracting,
    isAutoTagging,
    isPromoting,
    toast,
    setToast,
    handleRefreshDetails,
    handleEnrich,
    handleExtractBio,
    handleAutoTag,
    handlePromote,
    handleDelete,
    addNoteMutation,
    updateContact,
    deleteContact,
    queryClient,
  };
}
