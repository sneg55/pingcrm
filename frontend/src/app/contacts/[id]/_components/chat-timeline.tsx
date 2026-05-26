"use client";

import { useState } from "react";
import { format } from "date-fns";
import {
  Calendar,
  ChevronDown,
  Mail,
  MessageCircle,
  MessageSquare,
  Pencil,
  StickyNote,
  Trash2,
  Twitter,
} from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import { extractErrorMessage } from "@/lib/api-errors";
import { avatarColor, getInitials } from "../_lib/formatters";
import { Linkify } from "./linkify";
import type { InteractionResponse } from "../_hooks/use-contact-detail-controller";
import { TimelineItem } from "./timeline-item";

const MSG_TRUNCATE_LEN = 400;

export function CollapsibleText({
  text,
  linkClassName,
}: {
  text: string;
  linkClassName?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const needsTruncate = text.length > MSG_TRUNCATE_LEN;
  const display = needsTruncate && !expanded ? `${text.slice(0, MSG_TRUNCATE_LEN)  }...` : text;

  return (
    <>
      <Linkify text={display} className={linkClassName} />
      {needsTruncate && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-0.5 mt-1 text-[11px] font-medium opacity-70 hover:opacity-100 transition-opacity"
        >
          <ChevronDown className={cn("w-3 h-3 transition-transform", expanded && "rotate-180")} />
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </>
  );
}

const TIMELINE_PAGE_SIZE = 50;

export const platformIconMap: Record<string, React.ReactNode> = {
  email: <Mail className="w-3 h-3 text-red-400" />,
  telegram: <MessageCircle className="w-3 h-3 text-sky-400" />,
  twitter: <Twitter className="w-3 h-3 text-stone-400" />,
  manual: <StickyNote className="w-3 h-3 text-amber-400" />,
  meeting: <Calendar className="w-3 h-3 text-teal-500" />,
  whatsapp: <MessageSquare className="w-3 h-3 text-green-500" />,
};

export function NoteItem({
  item,
  contactId,
}: {
  item: InteractionResponse;
  contactId: string;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.content_preview || "");

  const updateMutation = useMutation({
    mutationFn: async (content: string) => {
      const { error } = await client.PATCH(
        "/api/v1/contacts/{contact_id}/interactions/{interaction_id}",
        {
          params: { path: { contact_id: contactId, interaction_id: item.id } },
          body: { content_preview: content },
        }
      );
      if (error) throw new Error(extractErrorMessage(error) ?? "Update failed");
    },
    onSuccess: () => {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["interactions", contactId] });
      void queryClient.invalidateQueries({ queryKey: ["activity", "recent"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      const { error } = await client.DELETE(
        "/api/v1/contacts/{contact_id}/interactions/{interaction_id}",
        { params: { path: { contact_id: contactId, interaction_id: item.id } } }
      );
      if (error) throw new Error(extractErrorMessage(error) ?? "Delete failed");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["interactions", contactId] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", "overdue"] });
      void queryClient.invalidateQueries({ queryKey: ["activity", "recent"] });
    },
  });

  return (
    <div className="my-3 ml-2 pl-3 border-l-2 border-amber-300 py-1.5 group/note">
      <div className="flex items-start justify-between">
        {editing ? (
          <div className="flex-1 mr-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="w-full text-[13px] text-stone-700 dark:text-stone-300 leading-relaxed border border-stone-300 dark:border-stone-700 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none bg-white dark:bg-stone-800"
              rows={2}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  updateMutation.mutate(draft);
                }
                if (e.key === "Escape") {
                  setEditing(false);
                  setDraft(item.content_preview || "");
                }
              }}
            />
            <div className="flex gap-1.5 mt-1">
              <button
                onClick={() => updateMutation.mutate(draft)}
                disabled={updateMutation.isPending}
                className="text-[11px] px-2 py-0.5 bg-amber-500 text-white rounded hover:bg-amber-600 disabled:opacity-50"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setDraft(item.content_preview || "");
                }}
                className="text-[11px] px-2 py-0.5 text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-100"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            {item.content_preview && (
              <p className="text-[13px] text-stone-700 dark:text-stone-300 leading-relaxed flex-1">
                <Linkify text={item.content_preview} className="text-amber-700 hover:text-amber-900" />
              </p>
            )}
            <div className="flex items-center gap-1 opacity-0 group-hover/note:opacity-100 transition-opacity shrink-0 ml-2">
              <button
                onClick={() => setEditing(true)}
                className="p-1 rounded text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800"
              >
                <Pencil className="w-3 h-3" />
              </button>
              <button
                onClick={() => {
                  // eslint-disable-next-line no-alert -- native confirm before destructive delete
                  if (confirm("Delete this note?")) deleteMutation.mutate();
                }}
                className="p-1 rounded text-stone-400 dark:text-stone-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          </>
        )}
      </div>
      <div className="flex items-center gap-1.5 mt-1">
        {platformIconMap.manual}
        <span className="text-[10px] text-stone-400 dark:text-stone-500">
          Note &middot; {format(new Date(item.occurred_at), "MMM d")}
        </span>
      </div>
    </div>
  );
}

export function ChatTimeline({
  interactions,
  contactId,
  contactName,
}: {
  interactions: InteractionResponse[];
  contactId: string;
  contactName: string;
}) {
  const [visibleCount, setVisibleCount] = useState(TIMELINE_PAGE_SIZE);
  const visible = interactions.slice(0, visibleCount);
  const hasMore = visibleCount < interactions.length;

  if (interactions.length === 0) {
    return (
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-10 text-center">
        <div className="w-12 h-12 rounded-full bg-stone-100 dark:bg-stone-800 flex items-center justify-center mx-auto mb-3">
          <MessageCircle className="w-6 h-6 text-stone-400 dark:text-stone-500" />
        </div>
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 mb-1">No interactions yet</h3>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-4 max-w-xs mx-auto">
          Connect an account to sync messages, or add a note to get started.
        </p>
      </div>
    );
  }

  const initials = getInitials(contactName);
  const contactAvatarCls = avatarColor(contactName);

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-4 space-y-1">
      {visible.map((item, idx) => (
        <TimelineItem
          key={item.id}
          item={item}
          prevOccurredAt={idx > 0 ? (visible[idx - 1]?.occurred_at ?? null) : null}
          contactId={contactId}
          contactAvatarCls={contactAvatarCls}
          initials={initials}
        />
      ))}

      {hasMore && (
        <button
          onClick={() => setVisibleCount((c) => c + TIMELINE_PAGE_SIZE)}
          className="w-full mt-3 py-2 text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 hover:bg-teal-50 dark:hover:bg-teal-950 rounded-lg transition-colors"
        >
          Load more interactions...
        </button>
      )}
    </div>
  );
}
