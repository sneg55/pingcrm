"use client";

import { useState } from "react";
import Link from "next/link";
import { Clock, X, ChevronDown } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { ContactAvatar } from "@/components/contact-avatar";
import { ScoreBadge } from "@/components/score-badge";
import { MessageEditor } from "@/components/message-editor";
import {
  useUpdateSuggestion,
  useSendMessage,
  type Suggestion,
} from "@/hooks/use-suggestions";

type Channel = "email" | "telegram" | "twitter";

const snoozeOptions = [
  { label: "2 weeks", days: 14 },
  { label: "1 month", days: 30 },
  { label: "3 months", days: 90 },
];

function getContactName(c: Suggestion["contact"]): string {
  if (!c) return "Unknown";
  return (
    c.full_name ??
    ([c.given_name, c.family_name].filter(Boolean).join(" ") || "Unknown")
  );
}

export function DashboardSuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  const queryClient = useQueryClient();
  const updateSuggestion = useUpdateSuggestion();
  const sendMessage = useSendMessage();
  const [expanded, setExpanded] = useState(false);
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [sendConfirm, setSendConfirm] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);

  const c = suggestion.contact;
  const name = getContactName(c);
  const channel = suggestion.suggested_channel;

  const triggerLabels: Record<string, string> = {
    time_based: "90+ days",
    event_based: "New event",
    scheduled: "Scheduled",
    birthday: "Birthday",
  };

  const handleSend = async (message: string, ch: Channel, scheduledFor?: string) => {
    setSendError(null);
    if (ch === "telegram" && c?.telegram_username) {
      try {
        await sendMessage.mutateAsync({
          contactId: suggestion.contact_id,
          message,
          channel: ch,
          scheduledFor,
        });
        updateSuggestion.mutate({
          id: suggestion.id,
          input: { status: "sent", suggested_message: message, suggested_channel: ch },
        });
        setSendConfirm(scheduledFor ? "Scheduled!" : "Sent via Telegram!");
        setTimeout(() => setSendConfirm(null), 3000);
      } catch (err) {
        setSendError(err instanceof Error ? err.message : "Failed to send");
      }
    } else {
      void navigator.clipboard.writeText(message).catch((err: unknown) => {
        console.error("clipboard write failed", err);
      });
      if (ch === "twitter" && c?.twitter_handle) {
        window.open(`https://x.com/${c.twitter_handle.replace(/^@/, "")}`, "_blank");
      }
      updateSuggestion.mutate({
        id: suggestion.id,
        input: { status: "sent", suggested_message: message, suggested_channel: ch },
      });
      setSendConfirm("Copied to clipboard");
      setTimeout(() => setSendConfirm(null), 3000);
    }
  };

  const handleSnooze = (days: number) => {
    const snoozeUntil = new Date(Date.now() + days * 86400000).toISOString();
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "snoozed", snooze_until: snoozeUntil },
    });
    setSnoozeOpen(false);
  };

  const handleDismiss = () => {
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "dismissed" },
    });
  };

  return (
    <div
      className={`bg-white dark:bg-stone-900 rounded-xl border p-4 transition-all cursor-pointer hover:shadow-md ${
        expanded
          ? "border-teal-200 dark:border-teal-800 shadow-md shadow-teal-50 dark:shadow-teal-950 cursor-default"
          : "border-stone-200 dark:border-stone-700 hover:border-stone-300 dark:hover:border-stone-600"
      }`}
      onClick={() => !expanded && setExpanded(true)}
    >
      {sendConfirm && (
        <div className="text-xs text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-md px-3 py-2 mb-3">
          {sendConfirm}
        </div>
      )}
      {sendError && (
        <div className="text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-md px-3 py-2 mb-3">
          {sendError}
        </div>
      )}

      <div className="flex items-start gap-3">
        <ContactAvatar
          avatarUrl={c?.avatar_url}
          name={name}
          size="sm"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Link
                href={`/contacts/${suggestion.contact_id}`}
                className="text-sm font-medium text-stone-900 dark:text-stone-100 hover:text-teal-700 dark:hover:text-teal-300"
                onClick={(e) => e.stopPropagation()}
              >
                {name}
              </Link>
              {c?.last_interaction_at && (
                <ScoreBadge
                  score={0}
                  lastInteractionAt={c.last_interaction_at}
                  className="text-[10px]"
                />
              )}
            </div>
            <span className="text-[11px] text-stone-400 dark:text-stone-500 shrink-0">
              {suggestion.trigger_type === "birthday"
                ? "Birthday"
                : triggerLabels[suggestion.trigger_type] ?? "Follow-up"}
            </span>
          </div>
          <p className="text-xs text-stone-500 dark:text-stone-400 mt-1 line-clamp-2">
            {suggestion.suggested_message}
          </p>

          {expanded && (
            <div
              className="mt-4 pt-4 border-t border-stone-100 dark:border-stone-800 animate-fade-in-up"
              onClick={(e) => e.stopPropagation()}
            >
              <MessageEditor
                suggestionId={suggestion.id}
                initialMessage={suggestion.suggested_message}
                initialChannel={channel}
                onSend={handleSend}
                onRegenerate={() => {
                  void queryClient.invalidateQueries({ queryKey: ["suggestions"] });
                }}
                disabledChannels={{
                  ...(c?.telegram_username ? {} : { telegram: "No Telegram" }),
                  ...(!c?.twitter_handle ? { twitter: "No Twitter" } : {}),
                }}
              />

              <div className="flex items-center gap-2 mt-3">
                <div className="relative">
                  <button
                    onClick={() => setSnoozeOpen((v) => !v)}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 hover:bg-amber-100 dark:hover:bg-amber-900 transition-colors"
                  >
                    <Clock className="w-3 h-3" /> Snooze <ChevronDown className="w-2.5 h-2.5" />
                  </button>
                  {snoozeOpen && (
                    <div className="absolute left-0 bottom-full mb-1 w-32 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg py-1 z-50">
                      {snoozeOptions.map((opt) => (
                        <button
                          key={opt.days}
                          onClick={() => handleSnooze(opt.days)}
                          className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
                        >
                          <Clock className="w-3 h-3 text-stone-400 dark:text-stone-500" /> {opt.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={handleDismiss}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md text-stone-400 dark:text-stone-500 border border-stone-200 dark:border-stone-700 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
                >
                  <X className="w-3 h-3" /> Dismiss
                </button>
                <button
                  onClick={() => setExpanded(false)}
                  className="ml-auto text-xs text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300"
                >
                  Collapse
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
