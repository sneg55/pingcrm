"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Archive,
  ArrowRight,
  Building2,
  Calendar,
  Check,
  ChevronDown,
  Clock,
  Copy,
  GitMerge,
  Mail,
  MessageCircle,
  Minus,
  MoreVertical,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  StickyNote,
  Trash2,
  Twitter,
  Users,
  Wand2,
  X,
} from "lucide-react";
import Link from "next/link";
import {
  useContact,
  useUpdateContact,
  useDeleteContact,
  useContactDuplicates,
  useMergeContacts,
  useContactActivity,
  useContacts,
  type Contact,
  type ActivityData,
} from "@/hooks/use-contacts";
import { MessageEditor } from "@/components/message-editor";
import { CompanyFavicon } from "@/components/company-favicon";
import { InlineListField } from "@/components/inline-list-field";
import {
  useContactSuggestion,
  useUpdateSuggestion,
  useSendMessage,
} from "@/hooks/use-suggestions";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
import { formatDistanceToNow, format, isToday, isYesterday, isSameDay } from "date-fns";
import { cn } from "@/lib/utils";

/* ── Types ── */

interface InteractionResponse {
  id: string;
  platform: "email" | "telegram" | "twitter" | "linkedin" | "manual" | "meeting";
  direction: "inbound" | "outbound" | "mutual";
  content_preview: string | null;
  occurred_at: string;
}

/* ── Helpers ── */

const URL_RE = /(https?:\/\/[^\s<]+)/g;
const URL_TEST = /^https?:\/\/[^\s<]+$/;

function Linkify({ text, className }: { text: string; className?: string }) {
  const parts = text.split(URL_RE);
  return (
    <span>
      {parts.map((part, i) =>
        URL_TEST.test(part) ? (
          <a key={i} href={part} target="_blank" rel="noopener noreferrer" className={cn("underline break-all", className)}>
            {part}
          </a>
        ) : (
          part
        )
      )}
    </span>
  );
}

function getInitials(name: string | null): string {
  if (!name) return "?";
  return name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
}

const avatarColors = [
  "bg-violet-100 text-violet-700",
  "bg-teal-100 text-teal-700",
  "bg-pink-100 text-pink-700",
  "bg-orange-100 text-orange-700",
  "bg-sky-100 text-sky-700",
  "bg-indigo-100 text-indigo-700",
  "bg-stone-200 text-stone-600",
  "bg-emerald-100 text-emerald-700",
];

function avatarColor(name: string | null): string {
  if (!name) return avatarColors[6];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return avatarColors[Math.abs(hash) % avatarColors.length];
}

function scorePillClasses(score: number): { bg: string; text: string; dot: string; label: string } {
  if (score >= 8) return { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500", label: "Strong" };
  if (score >= 4) return { bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-400", label: "Warm" };
  return { bg: "bg-red-50", text: "text-red-700", dot: "bg-red-400", label: "Cold" };
}

function dateSeparatorLabel(dateStr: string): string {
  const d = new Date(dateStr);
  if (isToday(d)) return "Today";
  if (isYesterday(d)) return "Yesterday";
  return format(d, "MMM d, yyyy");
}

function needsSeparator(current: string, prev: string | null): boolean {
  if (!prev) return true;
  return !isSameDay(new Date(current), new Date(prev));
}

const platformIconMap: Record<string, React.ReactNode> = {
  email: <Mail className="w-3 h-3 text-red-400" />,
  telegram: <MessageCircle className="w-3 h-3 text-sky-400" />,
  twitter: <Twitter className="w-3 h-3 text-stone-400" />,
  manual: <StickyNote className="w-3 h-3 text-amber-400" />,
  meeting: <Calendar className="w-3 h-3 text-teal-500" />,
};

function platformLabel(platform: string): string {
  return platform === "manual" ? "Note" : platform.charAt(0).toUpperCase() + platform.slice(1);
}

/* ── Clipboard helper ── */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        void navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className={cn(
        "p-0.5 rounded transition-opacity",
        copied ? "text-emerald-500 opacity-100" : "text-stone-300 hover:text-stone-500 opacity-0 group-hover/row:opacity-100"
      )}
      title="Copy"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

/* ── Editable inline field ── */

function InlineField({
  label,
  value,
  displayValue,
  onSave,
  copyable,
  isLink,
  linkPrefix,
  internalHref,
}: {
  label: string;
  value: string | null | undefined;
  displayValue?: string;
  onSave: (v: string) => void;
  copyable?: boolean;
  isLink?: boolean;
  linkPrefix?: string;
  internalHref?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

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

  const startEdit = () => {
    setDraft(value ?? "");
    setEditing(true);
  };

  return (
    <div className="group/row flex items-start justify-between gap-4 py-1.5">
      <span className="text-xs text-stone-500 shrink-0 mt-0.5">{label}</span>
      {editing ? (
        <div className="flex flex-col items-end gap-1.5 min-w-0 flex-1">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") cancel(); }}
            className="w-full text-xs border border-stone-300 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-teal-400 bg-white"
          />
          <div className="flex items-center gap-2">
            <button onClick={cancel} className="px-2.5 py-1 text-xs font-medium rounded-md text-stone-600 hover:bg-stone-100 border border-stone-200">Cancel</button>
            <button onClick={save} className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-600 text-white hover:bg-emerald-700">Save</button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 min-w-0">
          {value ? (
            internalHref ? (
              <Link
                href={internalHref}
                className="text-xs font-medium text-teal-600 hover:text-teal-700 truncate"
              >
                {displayValue ?? value}
              </Link>
            ) : isLink && linkPrefix !== undefined ? (
              <a
                href={`${linkPrefix}${value}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-teal-600 hover:text-teal-700 cursor-pointer truncate"
                onClick={(e) => e.stopPropagation()}
              >
                {displayValue ?? value}
              </a>
            ) : (
              <span className="text-xs font-medium text-stone-900 truncate">
                {displayValue ?? value}
              </span>
            )
          ) : (
            <span className="text-xs text-stone-400">—</span>
          )}
          {copyable && value && <CopyButton text={value} />}
          <button
            onClick={startEdit}
            className="p-0.5 rounded text-stone-300 hover:text-stone-500 opacity-0 group-hover/row:opacity-100 transition-opacity shrink-0"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Company autocomplete field ── */

interface OrgOption {
  id: string;
  name: string;
}

function CompanyAutocompleteField({
  value,
  organizationId,
  emails,
  onSave,
  onLinkOrg,
}: {
  value: string | null | undefined;
  organizationId: string | null | undefined;
  emails?: string[] | null;
  onSave: (v: string) => void;
  onLinkOrg: (orgId: string, orgName: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [options, setOptions] = useState<OrgOption[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchOptions = (query: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) { setOptions([]); setShowDropdown(false); return; }
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await client.GET("/api/v1/organizations" as any, {
          params: { query: { search: query, page_size: "8" } },
        });
        const orgs = ((res.data as any)?.data ?? []) as OrgOption[];
        setOptions(orgs);
        setShowDropdown(orgs.length > 0 || query.trim().length > 0);
      } catch {
        setOptions([]);
      }
    }, 200);
  };

  const save = () => {
    if (draft !== (value ?? "")) onSave(draft);
    setEditing(false);
    setShowDropdown(false);
  };

  const cancel = () => {
    setDraft(value ?? "");
    setEditing(false);
    setShowDropdown(false);
  };

  const selectOrg = (org: OrgOption) => {
    onLinkOrg(org.id, org.name);
    setEditing(false);
    setShowDropdown(false);
  };

  const startEdit = () => {
    setDraft(value ?? "");
    setEditing(true);
  };

  return (
    <div className="group/row flex items-start justify-between gap-4 py-1.5" ref={wrapperRef}>
      <span className="text-xs text-stone-500 shrink-0 mt-0.5">Company</span>
      {editing ? (
        <div className="flex flex-col items-end gap-1.5 min-w-0 flex-1 relative">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => { setDraft(e.target.value); fetchOptions(e.target.value); }}
            onKeyDown={(e) => { if (e.key === "Enter") { save(); } if (e.key === "Escape") cancel(); }}
            className="w-full text-xs border border-stone-300 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-teal-400 bg-white"
            autoComplete="off"
          />
          {showDropdown && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-stone-200 rounded-lg shadow-lg z-50 max-h-48 overflow-y-auto">
              {options.map((org) => (
                <button
                  key={org.id}
                  onClick={() => selectOrg(org)}
                  className="w-full text-left px-3 py-2 text-xs hover:bg-teal-50 flex items-center gap-2 transition-colors"
                >
                  <Building2 className="w-3 h-3 text-stone-400 shrink-0" />
                  <span className="text-stone-900 truncate">{org.name}</span>
                </button>
              ))}
              {draft.trim() && !options.some((o) => o.name.toLowerCase() === draft.toLowerCase()) && (
                <button
                  onClick={save}
                  className="w-full text-left px-3 py-2 text-xs hover:bg-emerald-50 flex items-center gap-2 border-t border-stone-100 transition-colors"
                >
                  <Plus className="w-3 h-3 text-emerald-500 shrink-0" />
                  <span className="text-emerald-700">Set as &quot;{draft.trim()}&quot;</span>
                </button>
              )}
            </div>
          )}
          <div className="flex items-center gap-2">
            <button onClick={cancel} className="px-2.5 py-1 text-xs font-medium rounded-md text-stone-600 hover:bg-stone-100 border border-stone-200">Cancel</button>
            <button onClick={save} className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-600 text-white hover:bg-emerald-700">Save</button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 min-w-0">
          {value ? (
            <>
              <CompanyFavicon emails={emails} size="w-3.5 h-3.5" />
              {organizationId ? (
                <Link
                  href={`/organizations/${organizationId}`}
                  className="text-xs font-medium text-teal-600 hover:text-teal-700 truncate"
                >
                  {value}
                </Link>
              ) : (
                <span className="text-xs font-medium text-stone-900 truncate">{value}</span>
              )}
            </>
          ) : (
            <span className="text-xs text-stone-400">—</span>
          )}
          <button
            onClick={startEdit}
            className="p-0.5 rounded text-stone-300 hover:text-stone-500 opacity-0 group-hover/row:opacity-100 transition-opacity shrink-0"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Tags in header ── */

function TagsPills({
  tags,
  allTags,
  onSave,
}: {
  tags: string[];
  allTags: string[];
  onSave: (tags: string[]) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (adding) inputRef.current?.focus();
  }, [adding]);

  const tagColors: Record<number, string> = {
    0: "bg-violet-50 text-violet-700 border-violet-200",
    1: "bg-teal-50 text-teal-700 border-teal-200",
    2: "bg-amber-50 text-amber-700 border-amber-200",
    3: "bg-sky-50 text-sky-700 border-sky-200",
    4: "bg-pink-50 text-pink-700 border-pink-200",
  };

  const addTag = () => {
    const tag = draft.trim().toLowerCase();
    if (tag && !tags.includes(tag)) {
      onSave([...tags, tag]);
    }
    setDraft("");
    setAdding(false);
  };

  const removeTag = (tag: string) => {
    onSave(tags.filter((t) => t !== tag));
  };

  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map((tag, i) => (
        <span
          key={tag}
          className={cn(
            "group/tag inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium border",
            tagColors[i % 5]
          )}
        >
          {tag}
          <button onClick={() => removeTag(tag)} className="opacity-0 group-hover/tag:opacity-100 transition-opacity -mr-0.5">
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      {adding ? (
        <div className="flex items-center gap-1">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addTag(); if (e.key === "Escape") { setAdding(false); setDraft(""); } }}
            placeholder="Tag name..."
            className="text-[11px] border border-teal-300 rounded-full px-2 py-0.5 w-24 focus:outline-none focus:ring-1 focus:ring-teal-400"
            list="tag-suggestions"
          />
          <datalist id="tag-suggestions">
            {allTags.filter((t) => !tags.includes(t)).map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="px-2 py-0.5 rounded-full text-[11px] text-stone-400 border border-dashed border-stone-300 hover:bg-stone-50"
        >
          +
        </button>
      )}
    </div>
  );
}

/* ── Relationship Health Card ── */

function RelationshipHealth({ activityData, contact }: { activityData: ActivityData; contact: Contact }) {
  const { dimensions, stats } = activityData;
  const score = contact.relationship_score;
  const s = scorePillClasses(score);

  return (
    <div className="bg-white rounded-xl border border-stone-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-stone-900">Relationship Health</h3>
        <span className={cn("font-mono text-lg font-bold", s.text)}>
          {score}<span className="text-stone-300 font-normal text-sm">/10</span>
        </span>
      </div>

      <div className="space-y-2.5 mb-5">
        {[
          { label: "Reciprocity", ...dimensions.reciprocity },
          { label: "Recency", ...dimensions.recency },
          { label: "Frequency", ...dimensions.frequency },
          { label: "Breadth", ...dimensions.breadth },
        ].map((dim) => (
          <div key={dim.label}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-stone-600">{dim.label}</span>
              <span className="font-mono text-[11px] text-stone-400">{dim.value}/{dim.max}</span>
            </div>
            <div className="h-1.5 bg-stone-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-teal-500 rounded-full transition-all"
                style={{ width: dim.max > 0 ? `${(dim.value / dim.max) * 100}%` : "0%" }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-stone-100 pt-4 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-stone-500">Last contacted</span>
          <div className="text-right">
            <span className="text-xs font-medium text-stone-900">
              {contact.last_interaction_at
                ? formatDistanceToNow(new Date(contact.last_interaction_at), { addSuffix: true })
                : "Never"}
            </span>
            {stats.platforms.length > 0 && (
              <span className="text-[10px] text-stone-400 ml-1">via {stats.platforms[0]}</span>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-stone-500">Total interactions</span>
          <div className="text-right">
            <span className="text-xs font-medium text-stone-900">{stats.interaction_count}</span>
            {(stats.inbound_365d > 0 || stats.outbound_365d > 0) && (
              <span className="text-[10px] text-stone-400 ml-1">{stats.outbound_365d} out / {stats.inbound_365d} in</span>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-stone-500">Since</span>
          <span className="text-xs font-medium text-stone-900">
            {format(new Date(contact.created_at), "MMM yyyy")}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Duplicate Row (shared between card and modal) ── */

function DuplicateRow({
  dup,
  contactId,
  onDismissed,
}: {
  dup: any;
  contactId: string;
  onDismissed?: () => void;
}) {
  const mergeContacts = useMergeContacts();
  const queryClient = useQueryClient();
  const router = useRouter();
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState(false);

  const name = dup.full_name || [dup.given_name, dup.family_name].filter(Boolean).join(" ") || "Unnamed";
  const score = typeof dup.score === "number" ? Math.round(dup.score * 100) : null;

  const handleMerge = () => {
    mergeContacts.mutate(
      { contactId, otherId: dup.id },
      {
        onSuccess: (result: any) => {
          void queryClient.invalidateQueries({ queryKey: ["contacts"] });
          void queryClient.invalidateQueries({ queryKey: ["contact-duplicates"] });
          const survivingId = result?.data?.id;
          if (survivingId && survivingId !== contactId) {
            router.replace(`/contacts/${survivingId}`);
          }
        },
      }
    );
  };

  const handleDismiss = async () => {
    setDismissing(true);
    try {
      await client.POST(`/api/v1/contacts/${contactId}/dismiss-duplicate/${dup.id}` as any, {});
      void queryClient.invalidateQueries({ queryKey: ["contact-duplicates", contactId] });
      onDismissed?.();
    } finally {
      setDismissing(false);
    }
  };

  return (
    <div className="border border-stone-200 rounded-lg overflow-hidden">
      {score !== null && (
        <div className="flex items-center justify-between px-3 py-2 bg-stone-50 border-b border-stone-100">
          <span className={cn(
            "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border",
            score >= 85 ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
            score >= 65 ? "bg-amber-50 text-amber-700 border-amber-200" :
            "bg-sky-50 text-sky-700 border-sky-200"
          )}>
            {score >= 85 ? "Strong match" : score >= 65 ? "Probable match" : "Possible match"}
          </span>
          <div className="flex items-center gap-1.5">
            <div className="w-12 h-1.5 bg-stone-200 rounded-full overflow-hidden">
              <div className={cn("h-full rounded-full", score >= 85 ? "bg-emerald-500" : score >= 65 ? "bg-amber-400" : "bg-sky-400")} style={{ width: `${score}%` }} />
            </div>
            <span className="font-mono text-xs font-bold text-stone-600">{score}%</span>
          </div>
        </div>
      )}

      <div className="px-3 py-3">
        <Link href={`/contacts/${dup.id}`} className="flex items-center gap-2.5 mb-2.5 group/dup">
          <div className={cn("w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-semibold shrink-0", avatarColor(name))}>
            {getInitials(name)}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-stone-900 group-hover/dup:text-teal-700 transition-colors">{name}</p>
            <p className="text-[10px] text-stone-400">{dup.source ? `Via ${dup.source}` : "Contact"}</p>
          </div>
        </Link>

        <div className="space-y-1.5 mb-3">
          {dup.emails?.[0] && (
            <div className="flex items-center gap-2">
              <Check className="w-3 h-3 text-emerald-500 shrink-0" />
              <span className="text-[11px] text-stone-600">Email: <strong className="text-stone-800">{dup.emails[0]}</strong></span>
            </div>
          )}
          {dup.company && (
            <div className="flex items-center gap-2">
              <Check className="w-3 h-3 text-emerald-500 shrink-0" />
              <span className="text-[11px] text-stone-600">Company: <strong className="text-stone-800">{dup.company}</strong></span>
            </div>
          )}
          {!dup.twitter_handle && !dup.telegram_username && (
            <div className="flex items-center gap-2">
              <Minus className="w-3 h-3 text-stone-300 shrink-0" />
              <span className="text-[11px] text-stone-400">No matching handles</span>
            </div>
          )}
        </div>

        {confirmId === dup.id ? (
          <div className="flex items-center gap-2">
            <button
              onClick={handleMerge}
              disabled={mergeContacts.isPending}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors"
            >
              {mergeContacts.isPending ? "Merging..." : "Confirm merge"}
            </button>
            <button
              onClick={() => setConfirmId(null)}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-stone-200 text-stone-600 hover:bg-stone-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button
              onClick={handleDismiss}
              disabled={dismissing}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-stone-200 text-stone-600 hover:bg-stone-50 disabled:opacity-50 transition-colors"
            >
              <X className="w-3 h-3" /> {dismissing ? "Dismissing..." : "Not the same"}
            </button>
            <button
              onClick={() => setConfirmId(dup.id)}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 transition-colors"
            >
              <GitMerge className="w-3 h-3" /> Merge
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Duplicates Inline Card ── */

function DuplicatesCard({ contactId }: { contactId: string }) {
  const { data, isLoading } = useContactDuplicates(contactId, true);
  const duplicates = (data?.data ?? []).filter((d: any) => d.id !== contactId);
  const [showModal, setShowModal] = useState(false);

  if (isLoading || duplicates.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-stone-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-stone-900">Possible Duplicates</h3>
        <span className="text-[11px] font-medium text-stone-400">{duplicates.length} pending</span>
      </div>

      <DuplicateRow dup={duplicates[0]} contactId={contactId} />

      {duplicates.length > 1 && (
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center justify-center gap-1 mt-3 w-full text-[11px] text-teal-600 hover:text-teal-700 font-medium"
        >
          View all duplicates ({duplicates.length}) <ArrowRight className="w-3 h-3" />
        </button>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowModal(false)}>
          <div
            className="bg-white rounded-xl border border-stone-200 shadow-xl w-full max-w-md max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
              <h3 className="text-sm font-semibold text-stone-900">
                All Duplicates ({duplicates.length})
              </h3>
              <button onClick={() => setShowModal(false)} className="p-1 rounded-md text-stone-400 hover:bg-stone-100 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="overflow-auto p-4 space-y-3">
              {duplicates.map((dup: any) => (
                <DuplicateRow key={dup.id} dup={dup} contactId={contactId} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Suggestion Card (collapsible) ── */

/* ── Add Note Input ── */

function AddNoteInput({ onSave }: { onSave: (content: string) => void }) {
  const [focused, setFocused] = useState(false);
  const [text, setText] = useState("");

  const handleSave = () => {
    if (!text.trim()) return;
    onSave(text.trim());
    setText("");
    setFocused(false);
  };

  return (
    <div className="bg-white rounded-xl border border-stone-200 p-3 flex items-start gap-3">
      <StickyNote className="w-4 h-4 text-amber-400 mt-1.5 shrink-0" />
      <div className="flex-1">
        <textarea
          rows={focused ? 3 : 1}
          placeholder="Add a note..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setFocused(true)}
          className="w-full text-sm border-0 resize-none focus:outline-none placeholder:text-stone-400 py-1"
        />
        {focused && (
          <div className="flex items-center justify-end gap-2 mt-2 pt-2 border-t border-stone-100">
            <button
              onClick={() => { setText(""); setFocused(false); }}
              className="px-3 py-1.5 text-xs text-stone-500 hover:bg-stone-50 rounded-md transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="px-3 py-1.5 text-xs font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 transition-colors"
            >
              Save note
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Unified Message Composer Card ── */
/* Shows follow-up suggestion context when available, otherwise plain "Write a message". */

function MessageComposerCard({ contact, contactId }: { contact: Contact; contactId: string }) {
  const suggestion = useContactSuggestion(contactId);
  const updateSuggestion = useUpdateSuggestion();
  const sendMessage = useSendMessage();
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSnooze, setShowSnooze] = useState(false);
  const snoozeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showSnooze) return;
    const handler = (e: MouseEvent) => {
      if (snoozeRef.current && !snoozeRef.current.contains(e.target as Node)) {
        setShowSnooze(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSnooze]);

  const hasSuggestion = Boolean(suggestion);

  const disabledChannels = {
    ...(!contact.emails?.length ? { email: "No email" as const } : {}),
    ...(!contact.telegram_username ? { telegram: "No Telegram" as const } : {}),
    ...(!contact.twitter_handle ? { twitter: "No Twitter" as const } : {}),
  };

  const handleSnooze = (days: number) => {
    if (!suggestion) return;
    const date = new Date();
    date.setDate(date.getDate() + days);
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "snoozed", snooze_until: date.toISOString() },
    });
    setShowSnooze(false);
  };

  const handleDismiss = () => {
    if (!suggestion) return;
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "dismissed" },
    });
  };

  const handleSend = async (message: string, channel: string, scheduledFor?: string) => {
    setError(null);
    try {
      if (channel === "telegram" && contact.telegram_username) {
        await sendMessage.mutateAsync({ contactId, message, channel, scheduledFor });
        setSent(scheduledFor ? `Scheduled for ${new Date(scheduledFor).toLocaleString()}` : "Sent via Telegram!");
      } else if (channel === "email" && contact.emails?.length) {
        const email = contact.emails[0];
        const name = contact.given_name || contact.full_name || "";
        window.open(`mailto:${email}?subject=${encodeURIComponent(`Hey ${name}`.trim())}&body=${encodeURIComponent(message)}`, "_blank");
        setSent("Email draft opened");
      } else if (channel === "twitter" && contact.twitter_handle) {
        window.open(`https://x.com/messages/compose?text=${encodeURIComponent(message)}`, "_blank");
        void navigator.clipboard?.writeText(message).catch(() => {});
        setSent(`DM compose opened — search for @${contact.twitter_handle.replace(/^@/, "")}`);
      } else {
        void navigator.clipboard?.writeText(message).catch(() => {});
        setSent("Copied to clipboard");
      }
      if (suggestion) {
        updateSuggestion.mutate({
          id: suggestion.id,
          input: { status: "sent", suggested_message: message, suggested_channel: channel as "email" | "telegram" | "twitter" },
        });
      }
      setExpanded(false);
      void queryClient.invalidateQueries({ queryKey: ["interactions", contactId] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", contactId] });
      setTimeout(() => setSent(null), 4000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    }
  };

  return (
    <div className={cn(
      "bg-white rounded-xl border overflow-hidden transition-all",
      expanded
        ? hasSuggestion ? "border-amber-200 shadow-sm" : "border-teal-200 shadow-sm"
        : "border-stone-200"
    )}>
      {/* Collapsed header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-stone-50 transition-colors"
      >
        {hasSuggestion ? (
          <div className="w-8 h-8 rounded-full bg-amber-50 flex items-center justify-center shrink-0 mt-0.5">
            <Sparkles className="w-4 h-4 text-amber-500" />
          </div>
        ) : (
          <Send className="w-4 h-4 text-teal-500 shrink-0 mt-0.5" />
        )}
        <div className="flex-1 min-w-0">
          {sent ? (
            <span className="text-sm text-green-600 font-medium">{sent}</span>
          ) : hasSuggestion ? (
            <span className="text-sm text-stone-700 line-clamp-1">
              <span className="font-medium text-stone-900">Follow-up suggested</span>
              {!expanded && suggestion?.suggested_message && (
                <span className="text-stone-400"> — {suggestion.suggested_message.slice(0, 60)}...</span>
              )}
            </span>
          ) : (
            <span className="text-sm text-stone-500">Write a message...</span>
          )}
        </div>
        <ChevronDown className={`w-4 h-4 text-stone-400 shrink-0 mt-0.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {/* Expanded editor */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-stone-100 pt-3" onClick={(e) => e.stopPropagation()}>
          {sent && (
            <div className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2 mb-3">{sent}</div>
          )}
          {error && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2 mb-3">{error}</div>
          )}
          <MessageEditor
            suggestionId={suggestion?.id}
            contactId={contactId}
            initialMessage={suggestion?.suggested_message ?? ""}
            initialChannel={suggestion?.suggested_channel}
            disabledChannels={disabledChannels}
            onSend={handleSend}
            autoFocus
          />
          {hasSuggestion && (
            <div className="flex items-center gap-2 mt-3">
              <div className="relative" ref={snoozeRef}>
                <button
                  onClick={() => setShowSnooze(!showSnooze)}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md text-amber-600 border border-amber-200 bg-amber-50 hover:bg-amber-100 transition-colors"
                >
                  <Clock className="w-3 h-3" /> Snooze <ChevronDown className="w-2.5 h-2.5" />
                </button>
                {showSnooze && (
                  <div className="absolute left-0 bottom-full mb-1 w-32 bg-white rounded-lg border border-stone-200 shadow-lg py-1 z-50">
                    <button onClick={() => handleSnooze(14)} className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 hover:bg-stone-50"><Clock className="w-3 h-3 text-stone-400" /> 2 weeks</button>
                    <button onClick={() => handleSnooze(30)} className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 hover:bg-stone-50"><Clock className="w-3 h-3 text-stone-400" /> 1 month</button>
                    <button onClick={() => handleSnooze(90)} className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 hover:bg-stone-50"><Clock className="w-3 h-3 text-stone-400" /> 3 months</button>
                  </div>
                )}
              </div>
              <button
                onClick={handleDismiss}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md text-stone-400 border border-stone-200 hover:bg-stone-50 transition-colors"
              >
                <X className="w-3 h-3" /> Dismiss
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Timeline ── */

const TIMELINE_PAGE_SIZE = 50;

function ChatTimeline({
  interactions,
  contactName,
  onAddNote,
}: {
  interactions: InteractionResponse[];
  contactName: string;
  onAddNote: (content: string) => void;
}) {
  const [visibleCount, setVisibleCount] = useState(TIMELINE_PAGE_SIZE);
  const visible = interactions.slice(0, visibleCount);
  const hasMore = visibleCount < interactions.length;

  if (interactions.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-stone-200 p-10 text-center">
        <div className="w-12 h-12 rounded-full bg-stone-100 flex items-center justify-center mx-auto mb-3">
          <MessageCircle className="w-6 h-6 text-stone-400" />
        </div>
        <h3 className="text-sm font-semibold text-stone-900 mb-1">No interactions yet</h3>
        <p className="text-xs text-stone-500 mb-4 max-w-xs mx-auto">Connect an account to sync messages, or add a note to get started.</p>
      </div>
    );
  }

  const initials = getInitials(contactName);
  const contactAvatarCls = avatarColor(contactName);

  return (
    <div className="bg-white rounded-xl border border-stone-200 p-4 space-y-1">
      {visible.map((item, idx) => {
        const prevItem = idx > 0 ? visible[idx - 1] : null;
        const showSeparator = needsSeparator(item.occurred_at, prevItem?.occurred_at ?? null);
        const isManual = item.platform === "manual";
        const isMeeting = item.platform === "meeting";
        const isOutbound = item.direction === "outbound";
        const time = format(new Date(item.occurred_at), "h:mm a");

        return (
          <div key={item.id}>
            {/* Date separator */}
            {showSeparator && (
              <div className="flex items-center gap-3 py-2 mt-1">
                <div className="flex-1 h-px bg-stone-100" />
                <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wider">
                  {dateSeparatorLabel(item.occurred_at)}
                </span>
                <div className="flex-1 h-px bg-stone-100" />
              </div>
            )}

            {/* Note */}
            {isManual && (
              <div className="my-3 ml-2 pl-3 border-l-2 border-amber-300 py-1.5 group/note">
                <div className="flex items-start justify-between">
                  {item.content_preview && (
                    <p className="text-[13px] text-stone-700 leading-relaxed">
                      <Linkify text={item.content_preview} className="text-amber-700 hover:text-amber-900" />
                    </p>
                  )}
                  <div className="flex items-center gap-1 opacity-0 group-hover/note:opacity-100 transition-opacity shrink-0 ml-2">
                    <button className="p-1 rounded text-stone-400 hover:text-stone-600 hover:bg-stone-100"><Pencil className="w-3 h-3" /></button>
                    <button className="p-1 rounded text-stone-400 hover:text-red-500 hover:bg-red-50"><Trash2 className="w-3 h-3" /></button>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 mt-1">
                  {platformIconMap.manual}
                  <span className="text-[10px] text-stone-400">
                    Note &middot; {format(new Date(item.occurred_at), "MMM d")}
                  </span>
                </div>
              </div>
            )}

            {/* Meeting event */}
            {isMeeting && (
              <div className="flex justify-center py-1">
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-stone-50 border border-stone-100">
                  <Calendar className="w-3.5 h-3.5 text-teal-500" />
                  <span className="text-[11px] text-stone-500">
                    Meeting{item.content_preview ? ` · ${item.content_preview}` : ""}
                  </span>
                </div>
              </div>
            )}

            {/* Regular message */}
            {!isManual && !isMeeting && (
              isOutbound ? (
                <div className="flex items-end gap-2 max-w-[85%] ml-auto flex-row-reverse">
                  <div className="w-6 h-6 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center text-[10px] font-semibold shrink-0">You</div>
                  <div>
                    <div className="bg-teal-600 text-white rounded-2xl rounded-br-md px-3.5 py-2.5">
                      {item.content_preview && (
                        <p className="text-[13px] leading-relaxed">
                          <Linkify text={item.content_preview} className="text-teal-100 hover:text-white" />
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1 mr-1 justify-end">
                      <span className="text-[10px] text-stone-400">{time} &middot; {platformLabel(item.platform)}</span>
                      {platformIconMap[item.platform]}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-end gap-2 max-w-[85%]">
                  <div className={cn("w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold shrink-0", contactAvatarCls)}>
                    {initials}
                  </div>
                  <div>
                    <div className="bg-stone-100 rounded-2xl rounded-bl-md px-3.5 py-2.5">
                      {item.content_preview && (
                        <p className="text-[13px] text-stone-800 leading-relaxed">
                          <Linkify text={item.content_preview} className="text-teal-600 hover:text-teal-800" />
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1 ml-1">
                      {platformIconMap[item.platform]}
                      <span className="text-[10px] text-stone-400">{platformLabel(item.platform)} &middot; {time}</span>
                    </div>
                  </div>
                </div>
              )
            )}
          </div>
        );
      })}

      {hasMore && (
        <button
          onClick={() => setVisibleCount((c) => c + TIMELINE_PAGE_SIZE)}
          className="w-full mt-3 py-2 text-xs font-medium text-teal-600 hover:text-teal-700 hover:bg-teal-50 rounded-lg transition-colors"
        >
          Load more interactions...
        </button>
      )}
    </div>
  );
}

/* ═══════════════ PAGE ═══════════════ */

export default function ContactDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;
  const queryClient = useQueryClient();

  const { data: contactData, isLoading, isError } = useContact(id);
  const contact = contactData?.data as Contact | undefined;
  const updateContact = useUpdateContact();
  const deleteContact = useDeleteContact();
  const { data: activityData, isLoading: activityLoading } = useContactActivity(id);

  const [menuOpen, setMenuOpen] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isAutoTagging, setIsAutoTagging] = useState(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  // Interactions query with pagination
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
      const { data } = await client.GET("/api/v1/contacts/tags");
      return (data?.data as string[]) ?? [];
    },
  });
  const allTags = allTagsData ?? [];

  // Background bio refresh
  useQuery({
    queryKey: ["refresh-bios", id],
    queryFn: async () => {
      await client.POST("/api/v1/contacts/{contact_id}/refresh-bios", { params: { path: { contact_id: id } } });
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      return true;
    },
    enabled: Boolean(id),
    staleTime: Infinity,
    retry: false,
  });

  // Background email sync
  const contactEmails = contact?.emails;
  useQuery({
    queryKey: ["sync-emails", id],
    queryFn: async () => {
      const res = await client.POST("/api/v1/contacts/{contact_id}/sync-emails" as any, { params: { path: { contact_id: id } } });
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

  // Background avatar refresh
  useQuery({
    queryKey: ["refresh-avatar", id],
    queryFn: async () => {
      const res = await client.POST("/api/v1/contacts/{contact_id}/refresh-avatar" as any, { params: { path: { contact_id: id } } });
      if ((res.data as any)?.data?.changed) void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
      return true;
    },
    enabled: Boolean(id),
    staleTime: Infinity,
    retry: false,
  });

  const handleRefreshDetails = async () => {
    if (!id || isRefreshing) return;
    setIsRefreshing(true);
    try {
      await Promise.allSettled([
        client.POST("/api/v1/contacts/{contact_id}/refresh-bios", { params: { path: { contact_id: id }, query: { force: true } } } as any),
        client.POST("/api/v1/contacts/{contact_id}/refresh-avatar" as any, { params: { path: { contact_id: id }, query: { force: true } } }),
        ...(contactEmails?.length ? [client.POST("/api/v1/contacts/{contact_id}/sync-emails" as any, { params: { path: { contact_id: id }, query: { force: true } } })] : []),
        ...(contact?.telegram_username ? [client.POST("/api/v1/contacts/{contact_id}/sync-telegram" as any, { params: { path: { contact_id: id }, query: { force: true } } })] : []),
        ...(contact?.twitter_handle ? [client.POST("/api/v1/contacts/{contact_id}/sync-twitter" as any, { params: { path: { contact_id: id }, query: { force: true } } })] : []),
      ]);
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
      const res = await client.POST("/api/v1/contacts/{contact_id}/enrich" as any, { params: { path: { contact_id: id } } });
      const data = (res.data as any)?.data;
      const fields: string[] = data?.fields_updated ?? [];
      setToast({ type: "success", text: fields.length > 0 ? `Updated: ${fields.join(", ")}` : "No new data found" });
      void queryClient.invalidateQueries({ queryKey: ["contacts", id] });
    } catch (err: any) {
      setToast({ type: "error", text: err?.message || "Enrichment failed" });
    } finally {
      setIsEnriching(false);
      setTimeout(() => setToast(null), 5000);
    }
  };

  const handleAutoTag = async () => {
    if (!id || isAutoTagging) return;
    setIsAutoTagging(true);
    setToast(null);
    try {
      const res = await fetch(`/api/v1/contacts/${id}/auto-tag`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}`, "Content-Type": "application/json" },
      });
      const json = await res.json();
      if (!res.ok) {
        setToast({ type: "error", text: json.detail || "Auto-tagging failed" });
      } else {
        const tagsAdded = json.data?.tags_added ?? [];
        setToast({ type: "success", text: tagsAdded.length > 0 ? `Added: ${tagsAdded.join(", ")}` : "No new tags" });
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

  const handleDelete = () => {
    deleteContact.mutate(id, { onSuccess: () => router.push("/contacts") });
  };

  const addNoteMutation = useMutation({
    mutationFn: async (content: string) => {
      await client.POST("/api/v1/contacts/{contact_id}/interactions", {
        params: { path: { contact_id: id } },
        body: { platform: "manual", direction: "outbound", content_preview: content, occurred_at: new Date().toISOString() },
      });
    },
    onSuccess: () => void refetchInteractions(),
  });

  const saveField = (field: string, value: string | string[]) => {
    const input: Record<string, string | string[]> = { [field]: value };
    if (field === "given_name" || field === "family_name") {
      const given = field === "given_name" ? (value as string) : (contact?.given_name ?? "");
      const family = field === "family_name" ? (value as string) : (contact?.family_name ?? "");
      input.full_name = [given, family].filter(Boolean).join(" ") || "";
    }
    updateContact.mutate({ id, input });
  };

  const allInteractions = (interactionsData?.data ?? []) as InteractionResponse[];

  if (isLoading) {
    return (
      <div className="min-h-screen bg-stone-50">
        <main className="max-w-6xl mx-auto px-4 py-8">
          <div className="bg-white rounded-xl border border-stone-200 p-6 mb-6 animate-pulse">
            <div className="flex items-start gap-6">
              <div className="w-20 h-20 rounded-full bg-stone-200" />
              <div className="flex-1 space-y-3">
                <div className="h-6 w-48 bg-stone-200 rounded" />
                <div className="h-4 w-72 bg-stone-100 rounded" />
                <div className="h-4 w-32 bg-stone-100 rounded" />
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (isError || !contact) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">Contact not found.</p>
          <Link href="/contacts" className="text-teal-600 hover:underline">Back to contacts</Link>
        </div>
      </div>
    );
  }

  const displayName = contact.full_name ?? [contact.given_name, contact.family_name].filter(Boolean).join(" ") ?? "Unnamed Contact";
  const sp = scorePillClasses(contact.relationship_score);
  const activePriority = contact.priority_level || "medium";

  return (
    <div className="min-h-screen bg-stone-50">
      <main className="max-w-6xl mx-auto px-4 py-8">

        {/* Toast */}
        {toast && (
          <div className={cn(
            "mb-4 px-4 py-3 rounded-lg text-sm flex items-center gap-2",
            toast.type === "success" ? "bg-teal-50 border border-teal-200 text-teal-700" : "bg-red-50 border border-red-200 text-red-700"
          )}>
            {toast.type === "success" ? <Sparkles className="w-4 h-4 flex-shrink-0" /> : <X className="w-4 h-4 flex-shrink-0" />}
            {toast.text}
            <button onClick={() => setToast(null)} className="ml-auto p-0.5 hover:opacity-70"><X className="w-3.5 h-3.5" /></button>
          </div>
        )}

        {/* ═══ TOP: Contact Header Card ═══ */}
        <div className="bg-white rounded-xl border border-stone-200 p-6 mb-6">
          <div className="flex items-start gap-6">
            {/* Avatar */}
            <div className="shrink-0">
              {contact.avatar_url ? (
                <img src={contact.avatar_url} alt={displayName} className="w-20 h-20 rounded-full object-cover" />
              ) : (
                <div className={cn("w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold", avatarColor(displayName))}>
                  {getInitials(displayName)}
                </div>
              )}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-0.5">
                <h1 className="text-xl font-bold text-stone-900">{displayName}</h1>
                <span className={cn(
                  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border",
                  sp.bg, sp.text, `border-current/20`
                )}>
                  <span className={cn("w-1.5 h-1.5 rounded-full", sp.dot)} />
                  {sp.label}
                </span>
              </div>

              {/* Bios */}
              <div className="space-y-1.5 mb-4">
                {contact.twitter_bio && (
                  <div className="flex items-start gap-2">
                    <Twitter className="w-3.5 h-3.5 text-stone-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-stone-600 leading-relaxed">{contact.twitter_bio}</p>
                  </div>
                )}
                {contact.telegram_bio && (
                  <div className="flex items-start gap-2">
                    <MessageCircle className="w-3.5 h-3.5 text-sky-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-stone-600 leading-relaxed">{contact.telegram_bio}</p>
                  </div>
                )}
                {!contact.twitter_bio && !contact.telegram_bio && (contact.title || contact.company) && (
                  <p className="text-xs text-stone-500">
                    {[contact.title, contact.company].filter(Boolean).join(" at ")}
                  </p>
                )}
              </div>

              {/* Tags */}
              <TagsPills
                tags={contact.tags ?? []}
                allTags={allTags}
                onSave={(tags) => saveField("tags", tags)}
              />
            </div>

            {/* Top-right: priority + archive + kebab */}
            <div className="flex items-center gap-1 shrink-0">
              {/* Priority toggle */}
              <div className="flex items-center rounded-lg border border-stone-200 overflow-hidden">
                {[
                  { level: "high", emoji: "\u{1F525}", colors: "bg-red-50 text-red-600" },
                  { level: "medium", emoji: "\u26A1", colors: "bg-amber-50 text-amber-600" },
                  { level: "low", emoji: "\u{1F4A4}", colors: "bg-sky-50 text-sky-600" },
                ].map(({ level, emoji, colors }, i) => (
                  <button
                    key={level}
                    onClick={() => updateContact.mutate({ id, input: { priority_level: level } })}
                    className={cn(
                      "px-2.5 py-1.5 text-xs transition-colors",
                      i < 2 && "border-r border-stone-200",
                      activePriority === level ? colors : "text-stone-400 hover:bg-stone-50"
                    )}
                    title={level.charAt(0).toUpperCase() + level.slice(1)}
                  >
                    {emoji}
                  </button>
                ))}
              </div>

              {/* Archive */}
              <button
                onClick={() => {
                  updateContact.mutate({ id, input: { priority_level: "archived" } });
                  router.push("/contacts");
                }}
                className="p-2 rounded-lg text-stone-400 hover:text-amber-600 hover:bg-amber-50 transition-colors"
                title="Archive contact"
              >
                <Archive className="w-4 h-4" />
              </button>

              {/* Kebab menu */}
              <div className="relative" ref={menuRef}>
                <button
                  onClick={() => setMenuOpen((v) => !v)}
                  className="p-2 rounded-lg text-stone-400 hover:bg-stone-100 transition-colors"
                >
                  <MoreVertical className="w-4 h-4" />
                </button>
                {menuOpen && (
                  <div className="absolute right-0 top-full mt-1 w-52 bg-white rounded-lg border border-stone-200 shadow-lg py-1 z-50">
                    <button
                      onClick={() => { setMenuOpen(false); handleRefreshDetails(); }}
                      disabled={isRefreshing}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 hover:bg-stone-50 disabled:opacity-50"
                    >
                      <RefreshCw className={cn("w-4 h-4 text-stone-400", isRefreshing && "animate-spin")} />
                      {isRefreshing ? "Refreshing..." : "Refresh details"}
                    </button>
                    <button
                      onClick={() => { setMenuOpen(false); handleEnrich(); }}
                      disabled={isEnriching || (!contact.emails?.length && !contact.linkedin_url)}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 hover:bg-stone-50 disabled:opacity-50"
                    >
                      <Sparkles className={cn("w-4 h-4 text-amber-500", isEnriching && "animate-spin")} />
                      {isEnriching ? "Enriching..." : "Enrich with Apollo"}
                    </button>
                    <button
                      onClick={() => { setMenuOpen(false); handleAutoTag(); }}
                      disabled={isAutoTagging}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 hover:bg-stone-50 disabled:opacity-50"
                    >
                      <Wand2 className={cn("w-4 h-4 text-violet-500", isAutoTagging && "animate-spin")} />
                      {isAutoTagging ? "Tagging..." : "Auto-tag with AI"}
                    </button>
                    <div className="my-1 h-px bg-stone-100" />
                    <button
                      onClick={() => { setMenuOpen(false); setShowDeleteConfirm(true); }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                    >
                      <Trash2 className="w-4 h-4" /> Delete contact
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Delete confirmation */}
        {showDeleteConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(28,25,23,0.4)", backdropFilter: "blur(2px)" }}>
            <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-sm w-full mx-4">
              <h3 className="text-lg font-bold text-stone-900 mb-2">Delete contact?</h3>
              <p className="text-sm text-stone-600 mb-5">
                This will permanently delete <strong>{displayName}</strong> and all associated interactions.
              </p>
              <div className="flex gap-3 justify-end">
                <button onClick={() => setShowDeleteConfirm(false)} className="px-4 py-2 text-sm rounded-lg border border-stone-200 text-stone-700 hover:bg-stone-50 transition-colors">Cancel</button>
                <button onClick={handleDelete} disabled={deleteContact.isPending} className="px-4 py-2 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors">
                  {deleteContact.isPending ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ═══ TWO COLUMN GRID ═══ */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Main content (2/3) — DOM order 2, visual order 2 on desktop */}
          <div className="lg:col-span-2 lg:order-2 space-y-4">
            {/* Message composer — shows suggestion context when available, otherwise plain composer */}
            <MessageComposerCard contact={contact} contactId={id} />

            {/* Add note input */}
            <AddNoteInput onSave={(content) => addNoteMutation.mutate(content)} />

            {/* Timeline */}
            <ChatTimeline
              interactions={allInteractions}
              contactName={contact.full_name || contact.given_name || "Contact"}
              onAddNote={(content) => addNoteMutation.mutate(content)}
            />
          </div>

          {/* Sidebar (1/3) — DOM order 1, visual order 1 on desktop */}
          <div className="lg:order-1 space-y-6">
            {/* Contact Details */}
            <div className="bg-white rounded-xl border border-stone-200 p-5">
              <h3 className="text-sm font-semibold text-stone-900 mb-4">Contact Details</h3>
              <div className="space-y-0.5">
                <InlineField label="First name" value={contact.given_name} onSave={(v) => saveField("given_name", v)} />
                <InlineField label="Last name" value={contact.family_name} onSave={(v) => saveField("family_name", v)} />
                <InlineField label="Title" value={contact.title} onSave={(v) => saveField("title", v)} />
                <CompanyAutocompleteField
                  value={contact.company}
                  organizationId={contact.organization_id}
                  emails={contact.emails}
                  onSave={(v) => saveField("company", v)}
                  onLinkOrg={(orgId, orgName) => {
                    updateContact.mutate({ id, input: { company: orgName, organization_id: orgId } });
                  }}
                />
                <InlineField label="Location" value={contact.location} onSave={(v) => saveField("location", v)} />
                <InlineField label="Birthday" value={contact.birthday} onSave={(v) => saveField("birthday", v)} />

                <div className="my-2 h-px bg-stone-100" />

                <InlineListField label="Email" values={contact.emails ?? []} onSave={(v) => saveField("emails", v)} copyable isLink linkPrefix="mailto:" />
                <InlineField label="Telegram" value={contact.telegram_username} onSave={(v) => saveField("telegram_username", v)} copyable isLink linkPrefix="https://t.me/" />
                <InlineField label="Twitter" value={contact.twitter_handle} onSave={(v) => saveField("twitter_handle", v)} copyable isLink linkPrefix="https://x.com/" />
                <InlineField
                  label="LinkedIn"
                  value={contact.linkedin_url}
                  displayValue={contact.linkedin_url?.replace(/^https?:\/\/(www\.)?linkedin\.com\/in\//, "")?.replace(/\/$/, "")}
                  onSave={(v) => saveField("linkedin_url", v)}
                  isLink
                  linkPrefix=""
                  copyable
                />
                <InlineListField label="Phone" values={contact.phones ?? []} onSave={(v) => saveField("phones", v)} copyable isLink linkPrefix="tel:" />
              </div>
            </div>

            {/* Relationship Health */}
            {activityLoading ? (
              <div className="bg-white rounded-xl border border-stone-200 p-5 animate-pulse">
                <div className="h-4 w-40 bg-stone-200 rounded mb-4" />
                <div className="space-y-3">
                  {[1, 2, 3, 4].map((i) => <div key={i} className="h-1.5 bg-stone-100 rounded-full" />)}
                </div>
              </div>
            ) : activityData ? (
              <RelationshipHealth activityData={activityData} contact={contact} />
            ) : null}

            {/* Possible Duplicates */}
            <DuplicatesCard contactId={id} />
          </div>
        </div>
      </main>
    </div>
  );
}
