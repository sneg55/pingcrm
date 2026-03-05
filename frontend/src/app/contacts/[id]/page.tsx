"use client";

import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Edit, Mail, Phone, Building2, Tag } from "lucide-react";
import Link from "next/link";
import { useContact } from "@/hooks/use-contacts";
import { ScoreBadge } from "@/components/score-badge";
import { Timeline, type TimelineEntry } from "@/components/timeline";
import { useQuery, useMutation } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { formatDistanceToNow } from "date-fns";

interface InteractionResponse {
  id: string;
  platform: "email" | "telegram" | "twitter" | "manual";
  direction: "inbound" | "outbound" | "mutual";
  content_preview: string | null;
  occurred_at: string;
}

export default function ContactDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const { data: contactData, isLoading, isError } = useContact(id);
  const contact = contactData?.data;

  const { data: interactionsData, refetch: refetchInteractions } = useQuery({
    queryKey: ["interactions", id],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        data: InteractionResponse[];
        error: string | null;
      }>(`/contacts/${id}/interactions`);
      return data;
    },
    enabled: Boolean(id),
  });

  const interactions: TimelineEntry[] = (interactionsData?.data ?? []).map(
    (i) => ({
      id: i.id,
      platform: i.platform,
      direction: i.direction,
      content_preview: i.content_preview,
      occurred_at: i.occurred_at,
    })
  );

  const addNoteMutation = useMutation({
    mutationFn: async (content: string) => {
      await apiClient.post(`/contacts/${id}/interactions`, {
        platform: "manual",
        direction: "outbound",
        content_preview: content,
        occurred_at: new Date().toISOString(),
      });
    },
    onSuccess: () => {
      void refetchInteractions();
    },
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400">Loading contact...</p>
      </div>
    );
  }

  if (isError || !contact) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">Contact not found.</p>
          <Link href="/contacts" className="text-blue-600 hover:underline">
            Back to contacts
          </Link>
        </div>
      </div>
    );
  }

  const displayName =
    contact.full_name ??
    [contact.given_name, contact.family_name].filter(Boolean).join(" ") ??
    "Unnamed Contact";

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => router.back()}
            className="p-1.5 rounded-md hover:bg-gray-200 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </button>
          <span className="text-sm text-gray-500">
            <Link href="/contacts" className="hover:underline">
              Contacts
            </Link>{" "}
            / {displayName}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-1 space-y-4">
            <div className="bg-white rounded-lg border border-gray-200 p-5">
              <div className="flex items-start justify-between mb-3">
                <h1 className="text-xl font-bold text-gray-900">{displayName}</h1>
                <button className="p-1.5 rounded-md hover:bg-gray-100">
                  <Edit className="w-4 h-4 text-gray-500" />
                </button>
              </div>

              {(contact.title ?? contact.company) && (
                <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
                  <Building2 className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <span>
                    {[contact.title, contact.company].filter(Boolean).join(" at ")}
                  </span>
                </div>
              )}

              {contact.emails && contact.emails.length > 0 && (
                <div className="flex items-start gap-2 text-sm text-gray-600 mb-2">
                  <Mail className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div className="space-y-0.5">
                    {contact.emails.map((email) => (
                      <a
                        key={email}
                        href={`mailto:${email}`}
                        className="block text-blue-600 hover:underline"
                      >
                        {email}
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {contact.phones && contact.phones.length > 0 && (
                <div className="flex items-start gap-2 text-sm text-gray-600 mb-2">
                  <Phone className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div className="space-y-0.5">
                    {contact.phones.map((phone) => (
                      <span key={phone} className="block">
                        {phone}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {contact.tags && contact.tags.length > 0 && (
                <div className="flex items-start gap-2 mt-3">
                  <Tag className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div className="flex flex-wrap gap-1">
                    {contact.tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-block px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-100"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="bg-white rounded-lg border border-gray-200 p-5">
              <h2 className="text-sm font-semibold text-gray-700 mb-3">
                Relationship Health
              </h2>
              <ScoreBadge score={contact.relationship_score} className="text-base" />
              {contact.last_interaction_at && (
                <p className="text-xs text-gray-400 mt-2">
                  Last contact{" "}
                  {formatDistanceToNow(new Date(contact.last_interaction_at), {
                    addSuffix: true,
                  })}
                </p>
              )}
              {contact.priority_level && (
                <p className="text-xs text-gray-500 mt-1 capitalize">
                  Priority: {contact.priority_level}
                </p>
              )}
            </div>

            {contact.notes && (
              <div className="bg-white rounded-lg border border-gray-200 p-5">
                <h2 className="text-sm font-semibold text-gray-700 mb-2">Notes</h2>
                <p className="text-sm text-gray-600 whitespace-pre-wrap">
                  {contact.notes}
                </p>
              </div>
            )}
          </div>

          <div className="md:col-span-2">
            <div className="bg-white rounded-lg border border-gray-200 p-5">
              <Timeline
                interactions={interactions}
                onAddNote={(content) => addNoteMutation.mutate(content)}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
