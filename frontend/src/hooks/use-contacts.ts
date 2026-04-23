import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
import { extractErrorMessage } from "@/lib/api-errors";

export type Contact = {
  id: string;
  user_id: string;
  full_name: string | null;
  given_name: string | null;
  family_name: string | null;
  emails: string[];
  phones: string[];
  company: string | null;
  organization_id: string | null;
  title: string | null;
  twitter_handle: string | null;
  twitter_bio: string | null;
  telegram_username: string | null;
  telegram_user_id: string | null;
  telegram_bio: string | null;
  telegram_last_seen_at: string | null;
  location: string | null;
  latitude?: number | null;
  longitude?: number | null;
  birthday: string | null;
  linkedin_url: string | null;
  whatsapp_phone: string | null;
  avatar_url: string | null;
  tags: string[];
  notes: string | null;
  relationship_score: number;
  interaction_count: number;
  last_interaction_at: string | null;
  last_followup_at: string | null;
  priority_level: string;
  source: string | null;
  bcc_hash: string | null;
  created_at: string;
  updated_at: string | null;
}

export type ContactsParams = {
  page?: number;
  page_size?: number;
  search?: string;
  tag?: string;
  score?: string;
  priority?: string;
  source?: string;
  date_from?: string;
  date_to?: string;
  has_interactions?: boolean;
  interaction_days?: number;
  has_birthday?: boolean;
  archived_only?: boolean;
  include_archived?: boolean;
  sort?: string;
}

export type ContactCreateInput = {
  full_name?: string;
  given_name?: string;
  family_name?: string;
  emails?: string[];
  phones?: string[];
  company?: string;
  title?: string;
  twitter_handle?: string;
  twitter_bio?: string;
  telegram_username?: string;
  telegram_bio?: string;
  tags?: string[];
  notes?: string;
  priority_level?: string;
  source?: string;
  organization_id?: string;
}

export function useContacts(params: ContactsParams = {}) {
  return useQuery({
    queryKey: ["contacts", params],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts", {
        params: { query: params },
      });
      return data ?? null;
    },
  });
}

export function useContact(id: string) {
  return useQuery({
    queryKey: ["contacts", id],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/{contact_id}", {
        params: { path: { contact_id: id } },
      });
      return data ?? null;
    },
    enabled: Boolean(id),
  });
}

export function useCreateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: ContactCreateInput) => {
      const { data } = await client.POST("/api/v1/contacts", {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- local ContactCreateInput shape does not match generated ContactCreate schema exactly
        body: input as any,
      });
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });
}

export function useDeleteContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await client.DELETE("/api/v1/contacts/{contact_id}", {
        params: { path: { contact_id: id } },
      });
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });
}

export function useContactDuplicates(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["contact-duplicates", id],
    queryFn: async () => {
      const { data } = await client.GET(
        "/api/v1/contacts/{contact_id}/duplicates",
        { params: { path: { contact_id: id } } }
      );
      return data ?? { data: [], error: null };
    },
    enabled: Boolean(id) && enabled,
  });
}

export function useMergeContacts() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      contactId,
      otherId,
    }: {
      contactId: string;
      otherId: string;
    }) => {
      const { data, error } = await client.POST(
        "/api/v1/contacts/{contact_id}/merge/{other_id}",
        { params: { path: { contact_id: contactId, other_id: otherId } } }
      );
      if (error) {
        throw new Error(extractErrorMessage(error) ?? "Merge failed");
      }
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
      void queryClient.invalidateQueries({ queryKey: ["contact-duplicates"] });
    },
  });
}

export function useUpdateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      input,
    }: {
      id: string;
      input: Partial<ContactCreateInput>;
    }) => {
      const { data, error, response } = await client.PUT("/api/v1/contacts/{contact_id}", {
        params: { path: { contact_id: id } },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- local ContactCreateInput shape does not match generated ContactUpdate schema exactly
        body: input as any,
      });
      if (error) {
        const err = new Error("Update failed") as Error & { status?: number; detail?: unknown };
        err.status = response.status;
        // Preserve full structured detail (may include `conflicting_contact` for merge flows).
        err.detail = (error as { detail?: unknown }).detail;
        throw err;
      }
      return data;
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
      void queryClient.invalidateQueries({
        queryKey: ["contacts", variables.id],
      });
      // Re-trigger Telegram sync when username changes
      if ("telegram_username" in variables.input) {
        void queryClient.invalidateQueries({
          queryKey: ["sync-telegram", variables.id],
        });
      }
      // Re-trigger bio refresh when Twitter handle changes
      if ("twitter_handle" in variables.input) {
        void queryClient.invalidateQueries({
          queryKey: ["refresh-bios", variables.id],
        });
      }
    },
  });
}

export type ActivityData = {
  score: number;
  dimensions: {
    reciprocity: { value: number; max: number };
    recency: { value: number; max: number };
    frequency: { value: number; max: number };
    breadth: { value: number; max: number };
    tenure?: { value: number; max: number };
  };
  stats: {
    inbound_365d: number;
    outbound_365d: number;
    count_30d: number;
    count_90d: number;
    platforms: string[];
    interaction_count: number;
    first_interaction_at: string | null;
  };
  monthly_trend: Array<{ month: string; count: number }>;
}

export function useContactActivity(id: string) {
  return useQuery({
    queryKey: ["contact-activity", id],
    queryFn: async () => {
      const { data, error } = await client.GET(
        "/api/v1/contacts/{contact_id}/activity",
        { params: { path: { contact_id: id } } }
      );
      if (error || !data?.data) {
        throw new Error("Failed to fetch activity");
      }
      return data.data as unknown as ActivityData;
    },
    enabled: Boolean(id),
    retry: false,
  });
}
