import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient, { type ApiResponse } from "@/lib/api";

export interface Contact {
  id: string;
  user_id: string;
  full_name: string | null;
  given_name: string | null;
  family_name: string | null;
  emails: string[];
  phones: string[];
  company: string | null;
  title: string | null;
  twitter_handle: string | null;
  telegram_username: string | null;
  tags: string[];
  notes: string | null;
  relationship_score: number;
  last_interaction_at: string | null;
  last_followup_at: string | null;
  priority_level: string;
  source: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ContactsParams {
  page?: number;
  page_size?: number;
  search?: string;
  tag?: string;
}

export interface ContactCreateInput {
  full_name?: string;
  given_name?: string;
  family_name?: string;
  emails?: string[];
  phones?: string[];
  company?: string;
  title?: string;
  twitter_handle?: string;
  telegram_username?: string;
  tags?: string[];
  notes?: string;
  priority_level?: string;
  source?: string;
}

export function useContacts(params: ContactsParams = {}) {
  return useQuery({
    queryKey: ["contacts", params],
    queryFn: async () => {
      const { data } = await apiClient.get<
        ApiResponse<Contact[]>
      >("/contacts", { params });
      return data;
    },
  });
}

export function useContact(id: string) {
  return useQuery({
    queryKey: ["contacts", id],
    queryFn: async () => {
      const { data } = await apiClient.get<ApiResponse<Contact>>(
        `/contacts/${id}`
      );
      return data;
    },
    enabled: Boolean(id),
  });
}

export function useCreateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: ContactCreateInput) => {
      const { data } = await apiClient.post<ApiResponse<Contact>>(
        "/contacts",
        input
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
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
      const { data } = await apiClient.put<ApiResponse<Contact>>(
        `/contacts/${id}`,
        input
      );
      return data;
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
      void queryClient.invalidateQueries({
        queryKey: ["contacts", variables.id],
      });
    },
  });
}
