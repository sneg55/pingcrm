"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Globe,
  Linkedin,
  MapPin,
  Pencil,
  Trash2,
  Twitter,
  Users,
  BarChart3,
  MessageSquare,
  Clock,
} from "lucide-react";
import Link from "next/link";
import { client } from "@/lib/api-client";
import { ContactAvatar } from "@/components/contact-avatar";
import { ArchivedChip } from "@/components/archived-chip";
import { CompanyFavicon } from "@/components/company-favicon";
import { ScoreBadge } from "@/components/score-badge";
import { formatDistanceToNow } from "date-fns";

/* ── Helpers ── */

function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return /^https?:\/\//i.test(url) ? url : `https://${url}`;
}

/* ── Types ── */

type OrgContact = {
  id: string;
  full_name: string | null;
  given_name: string | null;
  family_name: string | null;
  title: string | null;
  avatar_url: string | null;
  relationship_score: number;
  priority_level: string;
  last_interaction_at: string | null;
}

type OrganizationData = {
  id: string;
  name: string;
  domain: string | null;
  logo_url: string | null;
  industry: string | null;
  location: string | null;
  website: string | null;
  linkedin_url: string | null;
  twitter_handle: string | null;
  notes: string | null;
  contact_count: number;
  avg_relationship_score: number;
  total_interactions: number;
  last_interaction_at: string | null;
  contacts: OrgContact[] | null;
}

/* ── Stat Card ── */

function StatCard({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
      <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{value}</div>
    </div>
  );
}

/* ── Inline editable field (org version) ── */

function OrgInlineField({
  icon: Icon,
  label,
  value,
  onSave,
  href,
}: {
  icon: typeof Globe;
  label: string;
  value: string | null;
  onSave: (v: string) => void;
  href?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value ?? "");
  }, [value, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft !== (value ?? "")) onSave(draft);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(value ?? "");
    setEditing(false);
  };

  return (
    <div className="group/field flex items-center gap-2 text-sm py-1">
      <Icon className="h-4 w-4 shrink-0 text-zinc-400 dark:text-zinc-500" />
      <span className="text-zinc-500 dark:text-zinc-400 shrink-0">{label}:</span>
      {editing ? (
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") cancel(); }}
            onBlur={save}
            className="flex-1 min-w-0 text-sm rounded border border-zinc-300 dark:border-zinc-700 px-2 py-0.5 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-teal-400"
          />
        </div>
      ) : (
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          {value ? (
            href ? (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-teal-600 dark:text-teal-400 hover:underline truncate">
                {value}
              </a>
            ) : (
              <span className="text-zinc-900 dark:text-zinc-100 truncate">{value}</span>
            )
          ) : (
            <span className="italic text-zinc-400 dark:text-zinc-500">—</span>
          )}
          <button
            onClick={() => { setDraft(value ?? ""); setEditing(true); }}
            className="p-0.5 rounded text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 opacity-0 group-hover/field:opacity-100 transition-opacity shrink-0"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Inline editable notes ── */

function OrgNotesField({ value, onSave }: { value: string | null; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value ?? "");
  }, [value, editing]);

  useEffect(() => {
    if (editing) textareaRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft !== (value ?? "")) onSave(draft);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(value ?? "");
    setEditing(false);
  };

  return (
    <div className="group/field mt-4">
      <label className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">Notes</label>
      {editing ? (
        <div className="space-y-2">
          <textarea
            ref={textareaRef}
            className="w-full rounded border border-zinc-300 dark:border-zinc-700 px-3 py-2 text-sm bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-teal-400"
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
          />
          <div className="flex items-center gap-2 justify-end">
            <button onClick={cancel} className="px-2.5 py-1 text-xs font-medium rounded-md text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">Cancel</button>
            <button onClick={save} className="px-2.5 py-1 text-xs font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700">Save</button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-1.5">
          <p className="text-sm text-zinc-600 dark:text-zinc-400 flex-1">
            {value || <span className="italic text-zinc-400 dark:text-zinc-500">No notes</span>}
          </p>
          <button
            onClick={() => { setDraft(value ?? ""); setEditing(true); }}
            className="p-0.5 rounded text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 opacity-0 group-hover/field:opacity-100 transition-opacity shrink-0 mt-0.5"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Inline editable org name ── */

function OrgNameField({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft.trim() && draft !== value) onSave(draft.trim());
    setEditing(false);
  };

  return (
    <div className="group/field flex items-center gap-2">
      {editing ? (
        <input
          ref={inputRef}
          className="rounded border border-zinc-300 dark:border-zinc-700 px-2 py-1 text-2xl font-bold bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-teal-400"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") { setDraft(value); setEditing(false); } }}
          onBlur={save}
        />
      ) : (
        <>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">{value}</h1>
          <button
            onClick={() => { setDraft(value); setEditing(true); }}
            className="p-1 rounded text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 opacity-0 group-hover/field:opacity-100 transition-opacity"
          >
            <Pencil className="w-4 h-4" />
          </button>
        </>
      )}
    </div>
  );
}

/* ── Main Page ── */

export default function OrganizationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [sortBy, setSortBy] = useState<"score" | "name" | "recent">("score");
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["organization", id],
    queryFn: async () => {
      const res = await client.GET("/api/v1/organizations/{org_id}", {
        params: { path: { org_id: id } },
      });
      if (res.error) throw new Error("Failed to load organization");
      return res.data?.data as unknown as OrganizationData;
    },
  });

  const updateMutation = useMutation({
    mutationFn: async (updates: Partial<OrganizationData>) => {
      const res = await client.PATCH("/api/v1/organizations/{org_id}", {
        params: { path: { org_id: id } },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- local OrganizationData has fields not in generated OrganizationUpdate schema
        body: updates as any,
      });
      return res.data?.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["organization", id] });
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      await client.DELETE("/api/v1/organizations/{org_id}", {
        params: { path: { org_id: id } },
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
      router.push("/organizations");
    },
  });

  const contacts = data?.contacts ?? [];
  const sortedContacts = useMemo(() => {
    const byActiveSort = (a: OrgContact, b: OrgContact) => {
      if (sortBy === "score") return b.relationship_score - a.relationship_score;
      if (sortBy === "name") return (a.full_name ?? "").localeCompare(b.full_name ?? "");
      if (sortBy === "recent") {
        const aDate = a.last_interaction_at ? new Date(a.last_interaction_at).getTime() : 0;
        const bDate = b.last_interaction_at ? new Date(b.last_interaction_at).getTime() : 0;
        return bDate - aDate;
      }
      return 0;
    };
    const active = contacts.filter((c) => c.priority_level !== "archived").sort(byActiveSort);
    const archived = contacts.filter((c) => c.priority_level === "archived").sort(byActiveSort);
    return [...active, ...archived];
  }, [contacts, sortBy]);

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-zinc-500 dark:text-zinc-400">
        Loading organization...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-red-500">
        Organization not found.
      </div>
    );
  }

  const org = data;
  const saveField = (field: string, value: string) => {
    updateMutation.mutate({ [field]: value } as Partial<OrganizationData>);
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            aria-label="Back to organizations"
            onClick={() => router.push("/organizations")}
            className="rounded-md p-1 text-zinc-400 dark:text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-600 dark:hover:text-zinc-300"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50 dark:bg-teal-900 overflow-hidden">
            <CompanyFavicon logoUrl={org.logo_url} domain={org.domain} size="h-6 w-6" />
          </div>
          <OrgNameField value={org.name} onSave={(v) => saveField("name", v)} />
        </div>

        <button
          aria-label="Delete organization"
          onClick={() => setShowDeleteModal(true)}
          className="rounded-md px-3 py-1.5 text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
        >
          <Trash2 className="mr-1 inline h-4 w-4" /> Delete
        </button>
      </div>

      {/* Stats Row */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard icon={Users} label="Contacts" value={org.contact_count} />
        <StatCard icon={BarChart3} label="Avg Score" value={org.avg_relationship_score} />
        <StatCard icon={MessageSquare} label="Interactions" value={org.total_interactions} />
        <StatCard
          icon={Clock}
          label="Last Activity"
          value={org.last_interaction_at ? formatDistanceToNow(new Date(org.last_interaction_at), { addSuffix: true }) : "Never"}
        />
      </div>

      {/* Info Panel — inline editable */}
      <div className="mb-6 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          Details
        </h2>
        <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
          <OrgInlineField icon={Globe} label="Website" value={org.website ?? org.domain} onSave={(v) => saveField("website", v)} href={safeHref(org.website ?? org.domain)} />
          <OrgInlineField icon={MapPin} label="Location" value={org.location} onSave={(v) => saveField("location", v)} />
          <OrgInlineField icon={Linkedin} label="LinkedIn" value={org.linkedin_url} onSave={(v) => saveField("linkedin_url", v)} href={safeHref(org.linkedin_url)} />
          <OrgInlineField icon={Twitter} label="Twitter" value={org.twitter_handle} onSave={(v) => saveField("twitter_handle", v)} href={org.twitter_handle ? (org.twitter_handle.startsWith("http") ? org.twitter_handle : `https://x.com/${org.twitter_handle.replace(/^@/, "")}`) : undefined} />
        </div>

        <OrgNotesField value={org.notes} onSave={(v) => saveField("notes", v)} />
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-6 shadow-xl">
            <h3 className="mb-2 text-base font-semibold text-zinc-900 dark:text-zinc-100">
              Delete organization?
            </h3>
            <p className="mb-5 text-sm text-zinc-500 dark:text-zinc-400">
              Contacts will be unlinked but not deleted. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowDeleteModal(false)}
                className="rounded-md border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-sm font-medium text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  deleteMutation.mutate();
                }}
                disabled={deleteMutation.isPending}
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Contacts Table */}
      <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
        <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 px-5 py-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Contacts ({contacts.length})
          </h2>
          <div className="flex items-center gap-1 text-xs">
            <span className="text-zinc-400 dark:text-zinc-500">Sort:</span>
            {(["score", "name", "recent"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={`rounded px-2 py-1 ${
                  sortBy === s
                    ? "bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-400"
                    : "text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                }`}
              >
                {s === "score" ? "Score" : s === "name" ? "Name" : "Recent"}
              </button>
            ))}
          </div>
        </div>

        {contacts.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-zinc-400 dark:text-zinc-500">No contacts in this organization.</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-100 dark:border-zinc-800 text-left text-xs text-zinc-500 dark:text-zinc-400">
                <th scope="col" className="px-5 py-2 font-medium">Name</th>
                <th scope="col" className="px-5 py-2 font-medium">Title</th>
                <th scope="col" className="px-5 py-2 font-medium text-center">Score</th>
                <th scope="col" className="px-5 py-2 font-medium text-right">Last Interaction</th>
              </tr>
            </thead>
            <tbody>
              {sortedContacts.map((contact) => {
                const isArchived = contact.priority_level === "archived";
                const mutedText = isArchived ? "opacity-60" : "";
                return (
                  <tr
                    key={contact.id}
                    className="border-b border-zinc-50 dark:border-zinc-800/50 hover:bg-zinc-50 dark:hover:bg-zinc-800/30"
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <Link
                          href={`/contacts/${contact.id}`}
                          className={`flex items-center gap-3 text-sm font-medium text-zinc-900 dark:text-zinc-100 hover:text-teal-600 dark:hover:text-teal-400 min-w-0 ${mutedText}`}
                        >
                          <ContactAvatar
                            avatarUrl={contact.avatar_url}
                            name={contact.full_name ?? ""}
                            size="sm"
                          />
                          <span className="truncate">{contact.full_name || "Unknown"}</span>
                        </Link>
                        {isArchived && <ArchivedChip />}
                      </div>
                    </td>
                    <td className={`px-5 py-3 text-sm text-zinc-500 dark:text-zinc-400 ${mutedText}`}>
                      {contact.title || "-"}
                    </td>
                    <td className="px-5 py-3 text-center">
                      <ScoreBadge score={contact.relationship_score} />
                    </td>
                    <td className={`px-5 py-3 text-right text-sm text-zinc-500 dark:text-zinc-400 ${mutedText}`}>
                      {contact.last_interaction_at
                        ? formatDistanceToNow(new Date(contact.last_interaction_at), { addSuffix: true })
                        : "Never"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
