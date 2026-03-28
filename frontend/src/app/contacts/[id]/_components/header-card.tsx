"use client";

import { useState, useRef, useEffect } from "react";
import {
  Archive,
  ArchiveRestore,
  ArrowUpCircle,
  MessageCircle,
  MoreVertical,
  Pencil,
  RefreshCw,
  Sparkles,
  Trash2,
  Twitter,
  Wand2,
  X,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import { type Contact } from "@/hooks/use-contacts";
import { scorePillClasses, avatarColor, getInitials } from "../_lib/formatters";

/* ── Tags pills ── */

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
    1: "bg-teal-50 dark:bg-teal-950 text-teal-700 dark:text-teal-300 border-teal-200 dark:border-teal-800",
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
          <button
            onClick={() => removeTag(tag)}
            className="opacity-0 group-hover/tag:opacity-100 transition-opacity -mr-0.5"
          >
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
            onKeyDown={(e) => {
              if (e.key === "Enter") addTag();
              if (e.key === "Escape") {
                setAdding(false);
                setDraft("");
              }
            }}
            placeholder="Tag name..."
            className="text-[11px] border border-teal-300 dark:border-teal-700 rounded-full px-2 py-0.5 w-24 focus:outline-none focus:ring-1 focus:ring-teal-400 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100"
            list="tag-suggestions"
          />
          <datalist id="tag-suggestions">
            {allTags
              .filter((t) => !tags.includes(t))
              .map((t) => (
                <option key={t} value={t} />
              ))}
          </datalist>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="px-2 py-0.5 rounded-full text-[11px] text-stone-400 dark:text-stone-500 border border-dashed border-stone-300 dark:border-stone-700 hover:bg-stone-50 dark:hover:bg-stone-800"
        >
          +
        </button>
      )}
    </div>
  );
}

/* ── Header Card ── */

export function HeaderCard({
  contact,
  allTags,
  isRefreshing,
  isEnriching,
  isAutoTagging,
  onSaveField,
  onUpdateContact,
  onRefreshDetails,
  onEnrich,
  onAutoTag,
  onShowDeleteConfirm,
  onArchive,
  onPromote,
  isPromoting,
}: {
  contact: Contact;
  allTags: string[];
  isRefreshing: boolean;
  isEnriching: boolean;
  isAutoTagging: boolean;
  onSaveField: (field: string, value: string | string[]) => void;
  onUpdateContact: (input: Record<string, unknown>) => void;
  onRefreshDetails: () => void;
  onEnrich: () => void;
  onAutoTag: () => void;
  onShowDeleteConfirm: () => void;
  onArchive: () => void;
  onPromote?: () => void;
  isPromoting?: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Fetch follow-up intervals from settings for tooltip display
  const { data: priorityData } = useQuery({
    queryKey: ["settings", "priority"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/settings/priority");
      return (data as any)?.data as { high: number; medium: number; low: number } | undefined;
    },
    staleTime: 5 * 60 * 1000,
  });
  const intervals = { high: priorityData?.high ?? 30, medium: priorityData?.medium ?? 60, low: priorityData?.low ?? 180 };

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  const displayName =
    contact.full_name ??
    [contact.given_name, contact.family_name].filter(Boolean).join(" ") ??
    "Unnamed Contact";
  const sp = scorePillClasses(contact.relationship_score);
  const activePriority = contact.priority_level || "medium";
  const is2ndTier = (contact.tags ?? []).some(
    (t) => t.toLowerCase() === "2nd tier"
  );

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-6 mb-6">
      <div className="flex items-start gap-6">
        {/* Avatar */}
        <div className="shrink-0">
          {contact.avatar_url ? (
            <img
              src={contact.avatar_url}
              alt={displayName}
              className="w-20 h-20 rounded-full object-cover"
            />
          ) : (
            <div
              className={cn(
                "w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold",
                avatarColor(displayName)
              )}
            >
              {getInitials(displayName)}
            </div>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-0.5">
            <h1 className="text-xl font-bold text-stone-900 dark:text-stone-100">{displayName}</h1>
            <span
              className={cn(
                "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border",
                sp.bg,
                sp.text,
                "border-current/20"
              )}
            >
              <span className={cn("w-1.5 h-1.5 rounded-full", sp.dot)} />
              {sp.label}
            </span>
            {is2ndTier && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border bg-stone-50 dark:bg-stone-800 text-stone-500 dark:text-stone-400 border-stone-200 dark:border-stone-700">
                2nd Tier
              </span>
            )}
          </div>

          {/* Bios */}
          <div className="space-y-1.5 mb-4">
            {contact.twitter_bio && (
              <div className="flex items-start gap-2">
                <Twitter className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 mt-0.5 shrink-0" />
                <p className="text-xs text-stone-600 dark:text-stone-300 leading-relaxed">{contact.twitter_bio}</p>
              </div>
            )}
            {contact.telegram_bio && (
              <div className="flex items-start gap-2">
                <MessageCircle className="w-3.5 h-3.5 text-sky-400 mt-0.5 shrink-0" />
                <p className="text-xs text-stone-600 dark:text-stone-300 leading-relaxed">{contact.telegram_bio}</p>
              </div>
            )}
            {!contact.twitter_bio &&
              !contact.telegram_bio &&
              (contact.title || contact.company) && (
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {[contact.title, contact.company].filter(Boolean).join(" at ")}
                </p>
              )}
          </div>

          {/* Tags */}
          <TagsPills
            tags={contact.tags ?? []}
            allTags={allTags}
            onSave={(tags) => onSaveField("tags", tags)}
          />
        </div>

        {/* Top-right: priority + archive + kebab */}
        <div className="flex items-center gap-1 shrink-0">
          {/* Priority toggle */}
          <div className="flex items-center rounded-lg border border-stone-200 dark:border-stone-700 overflow-hidden">
            {[
              { level: "high", emoji: "\u{1F525}", colors: "bg-red-50 dark:bg-red-950 text-red-600", tooltip: `High priority — follow up every ${intervals.high} days` },
              { level: "medium", emoji: "\u26A1", colors: "bg-amber-50 dark:bg-amber-950 text-amber-600", tooltip: `Medium priority — follow up every ${intervals.medium} days` },
              { level: "low", emoji: "\u{1F4A4}", colors: "bg-sky-50 dark:bg-sky-950 text-sky-600", tooltip: `Low priority — follow up every ${intervals.low} days` },
            ].map(({ level, emoji, colors, tooltip }, i) => (
              <button
                key={level}
                onClick={() => onUpdateContact({ priority_level: level })}
                className={cn(
                  "px-2.5 py-1.5 text-xs transition-colors",
                  i < 2 && "border-r border-stone-200 dark:border-stone-700",
                  activePriority === level ? colors : "text-stone-400 dark:text-stone-500 hover:bg-stone-50 dark:hover:bg-stone-800"
                )}
                title={tooltip}
              >
                {emoji}
              </button>
            ))}
          </div>

          {/* Archive / Unarchive */}
          {contact.priority_level === "archived" ? (
            <button
              onClick={onArchive}
              className="p-2 rounded-lg text-amber-500 bg-amber-50 dark:bg-amber-950 hover:text-amber-600 hover:bg-amber-100 dark:hover:bg-amber-900 transition-colors"
              title="Unarchive contact"
            >
              <ArchiveRestore className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={onArchive}
              className="p-2 rounded-lg text-stone-400 dark:text-stone-500 hover:text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950 transition-colors"
              title="Archive contact"
            >
              <Archive className="w-4 h-4" />
            </button>
          )}

          {/* Kebab menu */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="p-2 rounded-lg text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              title="More actions"
            >
              <MoreVertical className="w-4 h-4" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 w-52 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg py-1 z-50">
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onRefreshDetails();
                  }}
                  disabled={isRefreshing}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50"
                >
                  <RefreshCw
                    className={cn("w-4 h-4 text-stone-400 dark:text-stone-500", isRefreshing && "animate-spin")}
                  />
                  {isRefreshing ? "Refreshing..." : "Refresh details"}
                </button>
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onEnrich();
                  }}
                  disabled={isEnriching || (!contact.emails?.length && !contact.linkedin_url)}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50"
                >
                  <Sparkles
                    className={cn("w-4 h-4 text-amber-500", isEnriching && "animate-spin")}
                  />
                  {isEnriching ? "Enriching..." : "Enrich with Apollo"}
                </button>
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onAutoTag();
                  }}
                  disabled={isAutoTagging}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50"
                >
                  <Wand2
                    className={cn("w-4 h-4 text-violet-500", isAutoTagging && "animate-spin")}
                  />
                  {isAutoTagging ? "Tagging..." : "Auto-tag with AI"}
                </button>
                {is2ndTier && onPromote && (
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      onPromote();
                    }}
                    disabled={isPromoting}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 disabled:opacity-50"
                  >
                    <ArrowUpCircle className="w-4 h-4" />
                    {isPromoting ? "Promoting..." : "Promote to 1st Tier"}
                  </button>
                )}
                <div className="my-1 h-px bg-stone-100 dark:bg-stone-800" />
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onShowDeleteConfirm();
                  }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
                >
                  <Trash2 className="w-4 h-4" /> Delete contact
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
