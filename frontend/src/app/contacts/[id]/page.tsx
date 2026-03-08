"use client";

import { useState, useRef, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  Mail,
  Phone,
  Building2,
  Tag,
  User,
  Briefcase,
  MessageCircle,
  Twitter,
  Linkedin,
  FileText,
  AtSign,
  Calendar,
  MapPin,
  MoreVertical,
  RefreshCw,
  Sparkles,
  Trash2,
  Users,
  Wand2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useContact, useUpdateContact, useDeleteContact, useContactDuplicates, useMergeContacts } from "@/hooks/use-contacts";
import { ScoreBadge } from "@/components/score-badge";
import { Timeline, type TimelineEntry } from "@/components/timeline";
import {
  EditableField,
  EditableListField,
  EditableTagsField,
} from "@/components/editable-field";
import { ContactAvatar } from "@/components/contact-avatar";
import { MessageEditor } from "@/components/message-editor";
import { useContactSuggestion, useUpdateSuggestion, useSendMessage } from "@/hooks/use-suggestions";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
import { formatDistanceToNow } from "date-fns";

interface InteractionResponse {
  id: string;
  platform: "email" | "telegram" | "twitter" | "linkedin" | "manual" | "meeting";
  direction: "inbound" | "outbound" | "mutual";
  content_preview: string | null;
  occurred_at: string;
}

interface NotificationItem {
  id: string;
  notification_type: string;
  title: string;
  body: string | null;
  read: boolean;
  link: string | null;
  created_at: string | null;
}

function DuplicatesModal({
  contactId,
  contactName,
  onClose,
}: {
  contactId: string;
  contactName: string;
  onClose: () => void;
}) {
  const { data, isLoading } = useContactDuplicates(contactId, true);
  const duplicates = data?.data ?? [];
  const mergeContacts = useMergeContacts();
  const [mergeConfirmId, setMergeConfirmId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const router = useRouter();

  const handleMerge = (otherId: string) => {
    mergeContacts.mutate(
      { contactId, otherId },
      {
        onSuccess: (result) => {
          setMergeConfirmId(null);
          void queryClient.invalidateQueries({ queryKey: ["contacts"] });
          onClose();
          const survivingId = result?.data?.id;
          if (survivingId && survivingId !== contactId) {
            router.replace(`/contacts/${survivingId}`);
          }
        },
      }
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full mx-4 max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between p-5 border-b border-stone-200">
          <h3 className="text-lg font-display font-semibold text-stone-900">
            Possible duplicates of {contactName}
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-stone-100 transition-colors"
          >
            <X className="w-5 h-5 text-stone-500" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1 p-5">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((n) => (
                <div key={n} className="h-16 rounded-lg bg-gray-100 animate-pulse" />
              ))}
            </div>
          ) : duplicates.length === 0 ? (
            <div className="text-center py-10 text-gray-400">
              <Users className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">No possible duplicates found</p>
            </div>
          ) : (
            <div className="space-y-3">
              {duplicates.map((dup) => {
                const name =
                  dup.full_name ||
                  [dup.given_name, dup.family_name].filter(Boolean).join(" ") ||
                  "Unnamed";
                const isConfirming = mergeConfirmId === dup.id;
                return (
                  <div
                    key={dup.id}
                    className="flex items-center gap-3 p-3 rounded-lg border border-stone-200 hover:border-teal-300 hover:bg-teal-50/50 transition-colors"
                  >
                    <Link
                      href={`/contacts/${dup.id}`}
                      onClick={onClose}
                      className="flex items-center gap-3 min-w-0 flex-1"
                    >
                      <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-semibold text-sm flex-shrink-0">
                        {name
                          .split(" ")
                          .map((w) => w[0])
                          .slice(0, 2)
                          .join("")
                          .toUpperCase()}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-gray-900 truncate">{name}</p>
                        <p className="text-xs text-gray-500 truncate">
                          {[
                            dup.company,
                            dup.emails[0],
                            dup.twitter_handle ? `@${dup.twitter_handle}` : null,
                            dup.telegram_username ? `@${dup.telegram_username}` : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      </div>
                      <span className="text-sm font-semibold text-teal-600 font-mono-data flex-shrink-0">
                        {Math.round(dup.score * 100)}%
                      </span>
                    </Link>
                    {isConfirming ? (
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button
                          onClick={() => handleMerge(dup.id)}
                          disabled={mergeContacts.isPending}
                          className="px-2.5 py-1.5 text-xs font-medium rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                        >
                          {mergeContacts.isPending ? "Merging..." : "Confirm"}
                        </button>
                        <button
                          onClick={() => setMergeConfirmId(null)}
                          className="px-2.5 py-1.5 text-xs rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setMergeConfirmId(dup.id)}
                        className="px-3 py-1.5 text-xs font-medium rounded-md border border-indigo-200 text-indigo-600 hover:bg-indigo-50 transition-colors flex-shrink-0"
                      >
                        Merge
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ContactDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const { data: contactData, isLoading, isError } = useContact(id);
  const contact = contactData?.data;
  const updateContact = useUpdateContact();
  const deleteContact = useDeleteContact();

  const [menuOpen, setMenuOpen] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isAutoTagging, setIsAutoTagging] = useState(false);
  const [autoTagResult, setAutoTagResult] = useState<string | null>(null);
  const [enrichResult, setEnrichResult] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  const handleDelete = () => {
    deleteContact.mutate(id, {
      onSuccess: () => router.push("/contacts"),
    });
  };

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

  // Fetch notifications linked to this contact (bio changes, events)
  const { data: notificationsData } = useQuery({
    queryKey: ["contact-notifications", id],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/notifications", {
        params: { query: { page_size: 50, link: `/contacts/${id}` } },
      });
      return (data?.data as NotificationItem[]) ?? [];
    },
    enabled: Boolean(id),
  });
  const contactNotifications = notificationsData ?? [];

  // Fetch common Telegram groups
  const { data: commonGroupsData } = useQuery({
    queryKey: ["telegram-common-groups", id],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/{contact_id}/telegram/common-groups", {
        params: { path: { contact_id: id } },
      });
      return (data?.data as { id: number; title: string; link: string | null; participants_count: number | null }[]) ?? [];
    },
    enabled: Boolean(id),
  });
  const commonGroups = commonGroupsData ?? [];

  // Fetch all existing tags for the tag picker
  const { data: allTagsData } = useQuery({
    queryKey: ["tags"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/tags");
      return (data?.data as string[]) ?? [];
    },
  });
  const allTags = allTagsData ?? [];

  // Trigger background bio refresh (rate-limited to 1/24h on backend)
  const queryClient = useQueryClient();
  useQuery({
    queryKey: ["refresh-bios", id],
    queryFn: async () => {
      await client.POST("/api/v1/contacts/{contact_id}/refresh-bios", {
        params: { path: { contact_id: id } },
      });
      // Silently refresh contact data after bio update completes
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      return true;
    },
    enabled: Boolean(id),
    staleTime: Infinity,
    retry: false,
  });

  // Background email sync — fires once per contact if they have emails (rate-limited to 1/hr on backend)
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
      }
      return true;
    },
    enabled: Boolean(id) && Boolean(contactEmails?.length),
    staleTime: Infinity,
    retry: false,
  });

  // Background avatar refresh (rate-limited to 1/24h on backend)
  useQuery({
    queryKey: ["refresh-avatar", id],
    queryFn: async () => {
      const res = await client.POST("/api/v1/contacts/{contact_id}/refresh-avatar" as any, {
        params: { path: { contact_id: id } },
      });
      if ((res.data as any)?.data?.changed) {
        void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      }
      return true;
    },
    enabled: Boolean(id),
    staleTime: Infinity,
    retry: false,
  });

  // Manual "Refresh Details" — force-refreshes bios, avatar, emails, and common groups
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
          ? [client.POST("/api/v1/contacts/{contact_id}/sync-emails" as any, {
              params: { path: { contact_id: id }, query: { force: true } },
            })]
          : []),
      ]);
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      void queryClient.invalidateQueries({ queryKey: ["interactions", id] });
      void queryClient.invalidateQueries({ queryKey: ["telegram-common-groups", id] });
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleEnrich = async () => {
    if (!id || isEnriching) return;
    setIsEnriching(true);
    setEnrichResult(null);
    try {
      const res = await client.POST("/api/v1/contacts/{contact_id}/enrich" as any, {
        params: { path: { contact_id: id } },
      });
      const data = (res.data as any)?.data;
      const fields: string[] = data?.fields_updated ?? [];
      if (fields.length > 0) {
        setEnrichResult({ type: "success", text: `Updated: ${fields.join(", ")}` });
      } else {
        setEnrichResult({ type: "success", text: "No new data found on Apollo" });
      }
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
    } catch (err: any) {
      const detail = err?.message || "Enrichment failed";
      setEnrichResult({ type: "error", text: detail });
    } finally {
      setIsEnriching(false);
    }
  };

  const handleAutoTag = async () => {
    if (!id || isAutoTagging) return;
    setIsAutoTagging(true);
    setAutoTagResult(null);
    try {
      const res = await fetch(`/api/v1/contacts/${id}/auto-tag`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          "Content-Type": "application/json",
        },
      });
      const json = await res.json();
      if (!res.ok) {
        setAutoTagResult(json.detail || "Auto-tagging failed");
      } else {
        const tagsAdded = json.data?.tags_added ?? [];
        setAutoTagResult(
          tagsAdded.length > 0
            ? `Added: ${tagsAdded.join(", ")}`
            : "No new tags to add"
        );
        void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
        void queryClient.invalidateQueries({ queryKey: ["tags"] });
      }
      setTimeout(() => setAutoTagResult(null), 5000);
    } catch {
      setAutoTagResult("Auto-tagging failed");
      setTimeout(() => setAutoTagResult(null), 5000);
    } finally {
      setIsAutoTagging(false);
    }
  };

  const allInteractions = (interactionsData?.data ?? []) as InteractionResponse[];
  const meetings = allInteractions.filter((i) => i.platform === "meeting");
  const interactions: TimelineEntry[] = allInteractions.map((i) => ({
    id: i.id,
    platform: i.platform as TimelineEntry["platform"],
    direction: i.direction as TimelineEntry["direction"],
    content_preview: i.content_preview,
    occurred_at: i.occurred_at,
  }));

  // Follow-up suggestion for this contact
  const suggestion = useContactSuggestion(id);
  const updateSuggestion = useUpdateSuggestion();
  const sendMessageMutation = useSendMessage();
  const [suggestionSent, setSuggestionSent] = useState<string | null>(null);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);

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
    onSuccess: () => {
      void refetchInteractions();
    },
  });

  const saveField = (field: string, value: string | string[]) => {
    const input: Record<string, string | string[]> = { [field]: value };

    // Keep full_name in sync when given/family name changes
    if (field === "given_name" || field === "family_name") {
      const given = field === "given_name" ? (value as string) : (contact?.given_name ?? "");
      const family = field === "family_name" ? (value as string) : (contact?.family_name ?? "");
      input.full_name = [given, family].filter(Boolean).join(" ") || "";
    }

    updateContact.mutate({ id, input });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <p className="text-stone-400">Loading contact...</p>
      </div>
    );
  }

  if (isError || !contact) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">Contact not found.</p>
          <Link href="/contacts" className="text-teal-600 hover:underline">
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
    <div className="min-h-screen bg-stone-50">
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Breadcrumb + Menu */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.back()}
              className="p-1.5 rounded-md hover:bg-stone-200 transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-stone-600" />
            </button>
            <span className="text-sm text-stone-500">
              <Link href="/contacts" className="hover:underline">
                Contacts
              </Link>{" "}
              / {displayName}
            </span>
          </div>

          {/* Kebab menu */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="p-2 rounded-md hover:bg-stone-200 transition-colors"
              aria-label="Contact actions"
            >
              <MoreVertical className="w-5 h-5 text-stone-600" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 w-52 bg-white rounded-lg border border-stone-200 shadow-lg py-1 z-20">
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    handleRefreshDetails();
                  }}
                  disabled={isRefreshing}
                  className="w-full text-left px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 flex items-center gap-2.5 disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 text-stone-400 ${isRefreshing ? "animate-spin" : ""}`} />
                  {isRefreshing ? "Refreshing..." : "Refresh details"}
                </button>
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    handleEnrich();
                  }}
                  disabled={isEnriching || (!contact?.emails?.length && !contact?.linkedin_url)}
                  className="w-full text-left px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 flex items-center gap-2.5 disabled:opacity-50"
                >
                  <Sparkles className={`w-4 h-4 text-amber-500 ${isEnriching ? "animate-spin" : ""}`} />
                  {isEnriching ? "Enriching..." : "Enrich with Apollo"}
                </button>
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    handleAutoTag();
                  }}
                  disabled={isAutoTagging}
                  className="w-full text-left px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 flex items-center gap-2.5 disabled:opacity-50"
                >
                  <Wand2 className={`w-4 h-4 text-violet-500 ${isAutoTagging ? "animate-spin" : ""}`} />
                  {isAutoTagging ? "Tagging..." : "Auto-tag with AI"}
                </button>
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    setShowDuplicates(true);
                  }}
                  className="w-full text-left px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 flex items-center gap-2.5"
                >
                  <Users className="w-4 h-4 text-stone-400" />
                  Show possible duplicates
                </button>
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    setShowDeleteConfirm(true);
                  }}
                  className="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2.5"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete contact
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Delete confirmation dialog */}
        {showDeleteConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Delete contact?</h3>
              <p className="text-sm text-gray-600 mb-5">
                This will permanently delete <strong>{displayName}</strong> and all associated interactions. This action cannot be undone.
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-4 py-2 text-sm rounded-md border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleteContact.isPending}
                  className="px-4 py-2 text-sm rounded-md bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                >
                  {deleteContact.isPending ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Duplicates modal */}
        {showDuplicates && (
          <DuplicatesModal contactId={id} contactName={displayName} onClose={() => setShowDuplicates(false)} />
        )}

        {/* Enrich result toast */}
        {enrichResult && (
          <div className={`mb-4 px-4 py-3 rounded-lg text-sm flex items-center gap-2 ${
            enrichResult.type === "success"
              ? "bg-amber-50 border border-amber-200 text-amber-700"
              : "bg-red-50 border border-red-200 text-red-700"
          }`}>
            <Sparkles className="w-4 h-4 flex-shrink-0" />
            {enrichResult.text}
            <button onClick={() => setEnrichResult(null)} className="ml-auto p-0.5 hover:opacity-70">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Auto-tag result toast */}
        {autoTagResult && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-violet-50 border border-violet-200 text-sm text-violet-700 flex items-center gap-2">
            <Wand2 className="w-4 h-4 flex-shrink-0" />
            {autoTagResult}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: Contact properties */}
          <div className="lg:col-span-1 space-y-4">
            {/* Header card with name + score */}
            <div className="bg-white rounded-lg border border-stone-200 p-5">
              <div className="flex items-center gap-3 mb-3">
                <ContactAvatar
                  avatarUrl={contact.avatar_url}
                  name={displayName}
                  size="lg"
                  score={contact.relationship_score}
                />
                <div className="min-w-0">
                  <h1 className="text-lg font-display font-bold text-stone-900 truncate">
                    {displayName}
                  </h1>
                  {(contact.title || contact.company) && (
                    <p className="text-sm text-stone-500 truncate">
                      {[contact.title, contact.company]
                        .filter(Boolean)
                        .join(" at ")}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-stone-100">
                <ScoreBadge
                  score={contact.relationship_score}
                  className="text-sm"
                />
                {contact.last_interaction_at && (
                  <span className="text-xs text-stone-400">
                    Last contact{" "}
                    {formatDistanceToNow(
                      new Date(contact.last_interaction_at),
                      { addSuffix: true }
                    )}
                  </span>
                )}
              </div>
            </div>

            {/* Priority panel */}
            <div className="bg-white rounded-lg border border-stone-200 p-4">
              <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2.5">
                Priority
              </p>
              <div className="flex gap-2">
                {(["high", "medium", "low", "archived"] as const).map((level) => {
                  const isActive = contact.priority_level === level;
                  const colors: Record<string, string> = {
                    high: isActive ? "bg-red-100 text-red-700 border-red-300" : "text-stone-600 border-stone-200 hover:bg-red-50 hover:text-red-600",
                    medium: isActive ? "bg-amber-100 text-amber-700 border-amber-300" : "text-stone-600 border-stone-200 hover:bg-amber-50 hover:text-amber-600",
                    low: isActive ? "bg-teal-100 text-teal-700 border-teal-300" : "text-stone-600 border-stone-200 hover:bg-teal-50 hover:text-teal-600",
                    archived: isActive ? "bg-stone-200 text-stone-700 border-stone-400" : "text-stone-600 border-stone-200 hover:bg-stone-100",
                  };
                  return (
                    <button
                      key={level}
                      onClick={() => {
                        if (!isActive) {
                          updateContact.mutate({ id, input: { priority_level: level } });
                          if (level === "archived") {
                            router.push("/contacts");
                          }
                        }
                      }}
                      className={`flex-1 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors capitalize ${colors[level]}`}
                    >
                      {({ high: "🔥 High", medium: "⚡ Medium", low: "💤 Low", archived: "📦 Archive" } as Record<string, string>)[level]}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Editable properties card */}
            <div className="bg-white rounded-lg border border-stone-200 p-5">
              <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2 pl-3 border-l-[3px] border-teal-500">
                Contact Details
              </h2>
              <div className="divide-y divide-stone-100">
                <EditableField
                  label="First name"
                  value={contact.given_name}
                  onSave={(v) => saveField("given_name", v)}
                  placeholder="Add first name..."
                  icon={<User className="w-4 h-4" />}
                />
                <EditableField
                  label="Last name"
                  value={contact.family_name}
                  onSave={(v) => saveField("family_name", v)}
                  placeholder="Add last name..."
                  icon={<User className="w-4 h-4" />}
                />
                <EditableListField
                  label="Email"
                  values={contact.emails ?? []}
                  onSave={(v) => saveField("emails", v)}
                  placeholder="Add email..."
                  icon={<Mail className="w-4 h-4" />}
                  linkPrefix="mailto:"
                />
                <EditableListField
                  label="Phone"
                  values={contact.phones ?? []}
                  onSave={(v) => saveField("phones", v)}
                  placeholder="Add phone..."
                  icon={<Phone className="w-4 h-4" />}
                  linkPrefix="tel:"
                />
                <EditableField
                  label="Company"
                  value={contact.company}
                  onSave={(v) => saveField("company", v)}
                  placeholder="Add company..."
                  icon={<Building2 className="w-4 h-4" />}
                />
                <EditableField
                  label="Job title"
                  value={contact.title}
                  onSave={(v) => saveField("title", v)}
                  placeholder="Add job title..."
                  icon={<Briefcase className="w-4 h-4" />}
                />
                <EditableField
                  label="Location"
                  value={contact.location}
                  onSave={(v) => saveField("location", v)}
                  placeholder="Add location..."
                  icon={<MapPin className="w-4 h-4" />}
                />
                <EditableField
                  label="Birthday"
                  value={contact.birthday}
                  onSave={(v) => saveField("birthday", v)}
                  placeholder="Add birthday..."
                  icon={<Calendar className="w-4 h-4" />}
                />
              </div>
            </div>

            {/* Social & Messaging */}
            <div className="bg-stone-50 rounded-lg border border-stone-200 p-5">
              <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2 pl-3 border-l-[3px] border-teal-500">
                Social & Messaging
              </h2>
              <div className="divide-y divide-stone-100">
                <EditableField
                  label="Twitter"
                  value={contact.twitter_handle}
                  onSave={(v) => saveField("twitter_handle", v)}
                  placeholder="Add Twitter handle..."
                  icon={<Twitter className="w-4 h-4" />}
                  linkPrefix="https://x.com/"
                />
                {contact.twitter_bio && (
                  <div className="py-2.5 px-3 -mx-3">
                    <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">
                      Twitter Bio
                    </p>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">
                      {contact.twitter_bio}
                    </p>
                  </div>
                )}
                <EditableField
                  label="Telegram"
                  value={contact.telegram_username}
                  onSave={(v) => saveField("telegram_username", v)}
                  placeholder="Add Telegram username..."
                  icon={<MessageCircle className="w-4 h-4" />}
                  linkPrefix="https://t.me/"
                />
                {contact.telegram_bio && (
                  <div className="py-2.5 px-3 -mx-3">
                    <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">
                      Telegram Bio
                    </p>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">
                      {contact.telegram_bio}
                    </p>
                  </div>
                )}
                <EditableField
                  label="LinkedIn"
                  value={contact.linkedin_url}
                  onSave={(v) => saveField("linkedin_url", v)}
                  placeholder="Add LinkedIn URL..."
                  icon={<Linkedin className="w-4 h-4" />}
                  linkPrefix=""
                />
                {commonGroups.length > 0 && (
                  <div className="py-2.5 px-3 -mx-3">
                    <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">
                      Common Groups ({commonGroups.length})
                    </p>
                    <div className="space-y-1">
                      {commonGroups.map((g) => (
                        <div
                          key={g.id}
                          className="flex items-center gap-2 text-sm"
                        >
                          <span className="w-5 h-5 rounded bg-sky-100 text-sky-600 flex items-center justify-center text-xs flex-shrink-0">
                            #
                          </span>
                          {g.link ? (
                            <a
                              href={g.link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:underline truncate"
                            >
                              {g.title}
                            </a>
                          ) : (
                            <span className="text-gray-800 truncate">
                              {g.title}
                            </span>
                          )}
                          {g.participants_count != null && (
                            <span className="text-xs text-gray-400 flex-shrink-0">
                              {g.participants_count} members
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Labels & Notes */}
            <div className="bg-white rounded-lg border border-stone-200 p-5">
              <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2 pl-3 border-l-[3px] border-teal-500">
                Other
              </h2>
              <div className="divide-y divide-stone-100">
                <EditableTagsField
                  label="Labels"
                  values={contact.tags ?? []}
                  onSave={(v) => saveField("tags", v)}
                  icon={<Tag className="w-4 h-4" />}
                  allTags={allTags}
                />
                <EditableField
                  label="Notes"
                  value={contact.notes}
                  onSave={(v) => saveField("notes", v)}
                  placeholder="Add notes..."
                  type="textarea"
                  icon={<FileText className="w-4 h-4" />}
                />
                <EditableField
                  label="Source"
                  value={contact.source}
                  onSave={(v) => saveField("source", v)}
                  placeholder="e.g. telegram, twitter, manual"
                  icon={<AtSign className="w-4 h-4" />}
                />
              </div>
            </div>
          </div>

          {/* Right column: Suggestion + Meetings + Notifications + Interactions timeline */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-gradient-to-r from-teal-50 to-cyan-50 rounded-lg border border-teal-200 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-display font-semibold text-teal-800">
                  Reach out
                </h2>
                {suggestion && (
                  <span className="text-xs text-teal-500">
                    {suggestion.trigger_type === "birthday"
                      ? "🎂 Birthday coming up"
                      : suggestion.trigger_type === "time_based"
                        ? "No interaction in 90+ days"
                        : suggestion.trigger_type === "scheduled"
                          ? "Scheduled follow-up"
                          : "New event detected"}
                  </span>
                )}
              </div>
              {suggestionSent && (
                <div className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2 mb-3">
                  {suggestionSent}
                </div>
              )}
              {suggestionError && (
                <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2 mb-3">
                  {suggestionError}
                </div>
              )}
              <MessageEditor
                suggestionId={suggestion?.id}
                contactId={id}
                initialMessage={suggestion?.suggested_message ?? ""}
                initialChannel={suggestion?.suggested_channel}
                disabledChannels={{
                  ...(!contact.emails?.length ? { email: "No email address" } : {}),
                  ...(!contact.telegram_username ? { telegram: "No Telegram username" } : {}),
                  ...(!contact.twitter_handle ? { twitter: "No Twitter handle" } : {}),
                }}
                onSend={async (message, channel) => {
                  setSuggestionError(null);
                  if (channel === "telegram" && contact?.telegram_username) {
                    try {
                      await sendMessageMutation.mutateAsync({
                        contactId: id,
                        message,
                        channel,
                      });
                      if (suggestion) {
                        updateSuggestion.mutate({
                          id: suggestion.id,
                          input: { status: "sent", suggested_message: message, suggested_channel: channel },
                        });
                      }
                      setSuggestionSent("Message sent via Telegram!");
                      setTimeout(() => setSuggestionSent(null), 4000);
                    } catch (err) {
                      setSuggestionError(
                        err instanceof Error ? err.message : "Failed to send"
                      );
                    }
                  } else if (channel === "email" && contact?.emails?.length) {
                    const email = contact.emails[0];
                    const name = contact.given_name || contact.full_name || "";
                    const subject = encodeURIComponent(`Hey ${name}`.trim());
                    const body = encodeURIComponent(message);
                    window.open(`mailto:${email}?subject=${subject}&body=${body}`, "_blank");
                    if (suggestion) {
                      updateSuggestion.mutate({
                        id: suggestion.id,
                        input: { status: "sent", suggested_message: message, suggested_channel: channel },
                      });
                    }
                    setSuggestionSent("Email draft opened in your mail app");
                    setTimeout(() => setSuggestionSent(null), 4000);
                  } else if (channel === "twitter" && contact?.twitter_handle) {
                    const handle = contact.twitter_handle.replace(/^@/, "");
                    const text = encodeURIComponent(message);
                    window.open(`https://x.com/messages/compose?text=${text}`, "_blank");
                    void navigator.clipboard?.writeText(message).catch(() => {});
                    if (suggestion) {
                      updateSuggestion.mutate({
                        id: suggestion.id,
                        input: { status: "sent", suggested_message: message, suggested_channel: channel },
                      });
                    }
                    setSuggestionSent(`DM compose opened on X — search for @${handle}`);
                    setTimeout(() => setSuggestionSent(null), 5000);
                  } else {
                    void navigator.clipboard?.writeText(message).catch(() => {});
                    if (suggestion) {
                      updateSuggestion.mutate({
                        id: suggestion.id,
                        input: { status: "sent", suggested_message: message, suggested_channel: channel },
                      });
                    }
                    setSuggestionSent("Message copied to clipboard");
                    setTimeout(() => setSuggestionSent(null), 4000);
                  }
                }}
              />
            </div>

            {meetings.length > 0 && (
              <div className="bg-white rounded-lg border border-stone-200 p-5">
                <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-3">
                  Meetings ({meetings.length})
                </h2>
                <div className="space-y-2">
                  {meetings.map((m) => {
                    const meetingDate = new Date(m.occurred_at);
                    const isFuture = meetingDate > new Date();
                    return (
                      <div
                        key={m.id}
                        className={`flex items-start gap-3 p-3 rounded-lg border ${
                          isFuture
                            ? "border-blue-200 bg-blue-50"
                            : "border-gray-100 bg-gray-50"
                        }`}
                      >
                        <span className="mt-0.5 flex-shrink-0">
                          <Calendar
                            className={`w-4 h-4 ${
                              isFuture ? "text-blue-500" : "text-gray-400"
                            }`}
                          />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-gray-900">
                            {m.content_preview || "Meeting"}
                          </p>
                          <p className="text-xs text-gray-400 mt-0.5">
                            {isFuture ? "Upcoming" : "Past"} &middot;{" "}
                            {formatDistanceToNow(meetingDate, {
                              addSuffix: true,
                            })}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {contactNotifications.length > 0 && (
              <div className="bg-white rounded-lg border border-stone-200 p-5">
                <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-3">
                  Activity Alerts
                </h2>
                <div className="space-y-2">
                  {contactNotifications.map((n) => (
                    <div
                      key={n.id}
                      className={`flex items-start gap-3 p-3 rounded-lg border ${
                        n.read
                          ? "border-gray-100 bg-gray-50"
                          : "border-blue-200 bg-blue-50"
                      }`}
                    >
                      <span className="mt-0.5 flex-shrink-0">
                        {n.notification_type === "bio_change" ? (
                          <Twitter className="w-4 h-4 text-blue-500" />
                        ) : (
                          <AlertCircle className="w-4 h-4 text-amber-500" />
                        )}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-900">
                          {n.title}
                        </p>
                        {n.body && (
                          <p className="text-sm text-gray-600 mt-0.5">
                            {n.body}
                          </p>
                        )}
                        {n.created_at && (
                          <p className="text-xs text-gray-400 mt-1">
                            {formatDistanceToNow(new Date(n.created_at), {
                              addSuffix: true,
                            })}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="bg-white rounded-lg border border-stone-200 p-5">
              <Timeline
                interactions={interactions}
                onAddNote={(content) => addNoteMutation.mutate(content)}
                contactName={contact?.full_name || contact?.given_name || "Contact"}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
