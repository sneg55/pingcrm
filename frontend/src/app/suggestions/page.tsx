"use client";

import { useState, type ReactNode } from "react";
import {
  Mail,
  MessageCircle,
  Twitter,
  Sparkles,
  Clock,
  X,
  ChevronDown,
  Timer,
  TimerOff,
  Cake,
  Calendar,
  CalendarClock,
  CheckCircle2,
  RefreshCw,
  Send,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useSuggestions,
  useUpdateSuggestion,
  useGenerateSuggestions,
  useSendMessage,
  type Suggestion,
} from "@/hooks/use-suggestions";
import { MessageEditor } from "@/components/message-editor";
import { ContactAvatar } from "@/components/contact-avatar";
import Link from "next/link";
import { cn } from "@/lib/utils";

type Channel = "email" | "telegram" | "twitter";

/* ── Helpers ── */

function displayName(c: Suggestion["contact"]): string {
  return (
    c?.full_name ??
    ([c?.given_name, c?.family_name].filter(Boolean).join(" ") || "Unknown contact")
  );
}

function daysAgo(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const diff = Date.now() - new Date(dateStr).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

function daysAgoLabel(days: number | null): string {
  if (days === null) return "";
  if (days >= 90) return "90+ days";
  return `${days} days ago`;
}

/* ── Relationship strength badge ── */
function strengthFromScore(score: number | null | undefined): { label: string; colors: string } {
  if (score == null || score <= 0) return { label: "New", colors: "bg-sky-50 dark:bg-sky-950 text-sky-600 dark:text-sky-400 border-sky-200 dark:border-sky-800" };
  if (score >= 70) return { label: "Strong", colors: "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800" };
  if (score >= 30) return { label: "Warm", colors: "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800" };
  return { label: "New", colors: "bg-sky-50 dark:bg-sky-950 text-sky-600 dark:text-sky-400 border-sky-200 dark:border-sky-800" };
}

function strengthDotColor(label: string): string {
  if (label === "Strong") return "bg-emerald-500";
  if (label === "Warm") return "bg-amber-400";
  return "bg-sky-400";
}

/* ── Trigger pill config ── */
interface TriggerConfig {
  icon: ReactNode;
  label: string;
  colors: string;
}

function triggerConfig(triggerType: string, days: number | null): TriggerConfig {
  switch (triggerType) {
    case "birthday":
      return { icon: <Cake className="w-2.5 h-2.5" />, label: "Birthday coming up", colors: "bg-violet-50 text-violet-500" };
    case "event_based":
      return { icon: <Calendar className="w-2.5 h-2.5" />, label: "New event detected", colors: "bg-blue-50 text-blue-500" };
    case "scheduled":
      return { icon: <CalendarClock className="w-2.5 h-2.5" />, label: "Scheduled follow-up", colors: "bg-teal-50 dark:bg-teal-950 text-teal-600 dark:text-teal-400" };
    case "time_based":
    default: {
      const d = days ?? 0;
      if (d >= 90) return { icon: <TimerOff className="w-2.5 h-2.5" />, label: `No interaction in 90+ days`, colors: "bg-red-50 dark:bg-red-950 text-red-500 dark:text-red-400" };
      return { icon: <Timer className="w-2.5 h-2.5" />, label: `No interaction in ${d} days`, colors: "bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400" };
    }
  }
}

/* ── Snooze options ── */
const snoozeOptions = [
  { label: "2 weeks", days: 14 },
  { label: "1 month", days: 30 },
  { label: "3 months", days: 90 },
];

/* ═══════════════ SUGGESTION CARD ═══════════════ */

function SuggestionCard({
  suggestion,
  expanded,
  onToggle,
}: {
  suggestion: Suggestion;
  expanded: boolean;
  onToggle: () => void;
}) {
  const queryClient = useQueryClient();
  const updateSuggestion = useUpdateSuggestion();
  const sendMessage = useSendMessage();
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [sendConfirm, setSendConfirm] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);

  const c = suggestion.contact;
  const name = displayName(c);
  const channel = suggestion.suggested_channel;
  const days = daysAgo(c?.last_interaction_at);
  const strength = strengthFromScore(null); // SuggestionContact doesn't have relationship_score
  const trigger = triggerConfig(suggestion.trigger_type, days);
  const isRevival = suggestion.trigger_type === "time_based" && (days ?? 0) >= 90;

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
        setSendConfirm(
          scheduledFor
            ? `Message scheduled for ${new Date(scheduledFor).toLocaleString()}!`
            : "Message sent via Telegram!"
        );
        setTimeout(() => setSendConfirm(null), 3000);
      } catch (err) {
        setSendError(err instanceof Error ? err.message : "Failed to send message");
      }
    } else {
      void navigator.clipboard.writeText(message).catch(() => {});
      if (ch === "twitter" && c?.twitter_handle) {
        window.open(`https://x.com/${c.twitter_handle.replace(/^@/, "")}`, "_blank");
      }
      updateSuggestion.mutate({
        id: suggestion.id,
        input: { status: "sent", suggested_message: message, suggested_channel: ch },
      });
      setSendConfirm("Message copied to clipboard");
      setTimeout(() => setSendConfirm(null), 3000);
    }
  };

  const handleSnooze = (snoozeDays: number) => {
    const snoozeUntil = new Date(Date.now() + snoozeDays * 24 * 60 * 60 * 1000).toISOString();
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "snoozed", snooze_until: snoozeUntil },
    });
    setSnoozeOpen(false);
  };

  const handleDismiss = () => {
    updateSuggestion.mutate({ id: suggestion.id, input: { status: "dismissed" } });
  };

  /* ── Send button label varies by channel ── */
  const sendLabel =
    channel === "email" ? "Send Email" : channel === "twitter" ? "Send DM" : "Send";
  const sendIcon =
    channel === "email" ? <Mail className="w-3.5 h-3.5" /> : channel === "twitter" ? <Send className="w-3.5 h-3.5" /> : <Send className="w-3.5 h-3.5" />;

  return (
    <div
      className={cn(
        "card-hover bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-4 transition-all duration-200",
        expanded
          ? "border-teal-200 dark:border-teal-800 shadow-[0_2px_16px_rgba(13,148,136,0.08)]"
          : "cursor-pointer hover:shadow-[0_2px_12px_rgba(0,0,0,0.06)] hover:border-stone-300 dark:hover:border-stone-600"
      )}
      onClick={() => { if (!expanded) onToggle(); }}
    >
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <ContactAvatar avatarUrl={suggestion.contact?.avatar_url || null} name={name} size="sm" />

        <div className="flex-1 min-w-0">
          {/* Header row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              <Link
                href={`/contacts/${suggestion.contact_id}`}
                className="text-sm font-medium text-stone-900 dark:text-stone-100 hover:text-teal-700 dark:hover:text-teal-300"
                onClick={(e) => e.stopPropagation()}
              >
                {name}
              </Link>
              {/* Strength badge */}
              <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border", strength.colors)}>
                <span className={cn("w-1.5 h-1.5 rounded-full", strengthDotColor(strength.label))} />
                {strength.label}
              </span>
              {/* Revival badge */}
              {isRevival && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 border border-stone-200 dark:border-stone-700">
                  Revival
                </span>
              )}
            </div>
            <span className="text-[11px] text-stone-400 dark:text-stone-500 shrink-0">
              {suggestion.trigger_type === "birthday"
                ? "🎂 Birthday soon"
                : daysAgoLabel(days)}
            </span>
          </div>

          {/* Trigger pill */}
          <div className="flex items-center gap-1.5 mt-1.5">
            <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium", trigger.colors)}>
              {trigger.icon} {trigger.label}
            </span>
          </div>

          {/* Message preview */}
          <p className="text-xs text-stone-500 dark:text-stone-400 mt-1.5 line-clamp-2">
            {suggestion.suggested_message}
          </p>

          {/* ── EXPANDED: Composer ── */}
          {expanded && (
            <div className="mt-4 pt-4 border-t border-stone-100 dark:border-stone-800" onClick={(e) => e.stopPropagation()}>
              {sendConfirm && (
                <div className="flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-md px-3 py-2 mb-3">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  {sendConfirm}
                </div>
              )}
              {sendError && (
                <div className="text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-md px-3 py-2 mb-3">
                  {sendError}
                </div>
              )}

              <MessageEditor
                suggestionId={suggestion.id}
                contactId={suggestion.contact_id}
                initialMessage={suggestion.suggested_message}
                initialChannel={channel}
                onSend={handleSend}
                onRegenerate={() => {
                  void queryClient.invalidateQueries({ queryKey: ["suggestions"] });
                }}
              />

              {/* Extra actions row */}
              <div className="flex flex-wrap items-center gap-2 mt-3">
                {/* Snooze */}
                <div className="relative inline-block">
                  <button
                    onClick={() => setSnoozeOpen((v) => !v)}
                    className="inline-flex items-center gap-1 px-2.5 py-2 min-h-[44px] text-xs rounded-md text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 hover:bg-amber-100 dark:hover:bg-amber-900 transition-colors"
                  >
                    <Clock className="w-3 h-3" /> Snooze <ChevronDown className="w-2.5 h-2.5" />
                  </button>
                  {snoozeOpen && (
                    <div className="absolute left-0 bottom-full mb-1 w-36 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg py-1 z-50">
                      {snoozeOptions.map((opt) => (
                        <button
                          key={opt.days}
                          onClick={() => handleSnooze(opt.days)}
                          className="w-full flex items-center gap-2 px-3 py-2 min-h-[44px] text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
                        >
                          <Clock className="w-3 h-3 text-stone-400 dark:text-stone-500" />
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {/* Dismiss */}
                <button
                  onClick={handleDismiss}
                  disabled={updateSuggestion.isPending}
                  className="inline-flex items-center gap-1 px-2.5 py-2 min-h-[44px] text-xs rounded-md text-stone-400 dark:text-stone-500 border border-stone-200 dark:border-stone-700 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
                >
                  <X className="w-3 h-3" /> Dismiss
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════ PAGE ═══════════════ */

export default function SuggestionsPage() {
  const { data, isLoading } = useSuggestions();
  const generateSuggestions = useGenerateSuggestions();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [toastDismissed, setToastDismissed] = useState(false);

  const allSuggestions = (data?.data ?? []) as unknown as Suggestion[];
  const pendingSuggestions = allSuggestions.filter((s) => s.status === "pending");

  const genMeta = generateSuggestions.data?.meta;
  const genResult = generateSuggestions.data?.data;
  const genCount =
    (genMeta as Record<string, number> | undefined)?.generated ?? (genResult as unknown[])?.length ?? 0;

  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950 overflow-x-hidden">
      {/* Success toast */}
      {generateSuggestions.isSuccess && !toastDismissed && (
        <div className="max-w-6xl mx-auto px-4 pt-4">
          <div className="flex items-center gap-3 px-4 py-3 bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-xl text-sm text-emerald-800 dark:text-emerald-300">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <span>
              Generation complete —{" "}
              <strong>
                {genCount > 0
                  ? `${genCount} new suggestion${genCount !== 1 ? "s" : ""}`
                  : "no new suggestions"}
              </strong>{" "}
              generated
            </span>
            <button onClick={() => setToastDismissed(true)} className="ml-auto text-emerald-500 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Generation error */}
      {generateSuggestions.isError && (
        <div className="max-w-6xl mx-auto px-4 pt-4">
          <div className="flex items-center gap-3 px-4 py-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-xl text-sm text-red-800 dark:text-red-300">
            Failed to generate suggestions. Please try again.
          </div>
        </div>
      )}

      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="animate-in stagger-1 flex flex-wrap items-start justify-between gap-3 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2.5">
              Suggestions Digest
              {pendingSuggestions.length > 0 && (
                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-300 text-xs font-bold font-mono">
                  {pendingSuggestions.length}
                </span>
              )}
            </h1>
            <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">AI-suggested follow-ups for your network</p>
          </div>
          <button
            onClick={() => { setToastDismissed(false); generateSuggestions.mutate(); }}
            disabled={generateSuggestions.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 min-h-[44px] rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm shrink-0"
          >
            <Sparkles className={cn("w-4 h-4", generateSuggestions.isPending && "animate-spin")} />
            {generateSuggestions.isPending ? "Generating..." : "Generate new suggestions"}
          </button>
        </div>

        {/* Generation progress */}
        {generateSuggestions.isPending && (
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-6 mb-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-8 h-8 rounded-full bg-teal-50 dark:bg-teal-950 flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-teal-600 dark:text-teal-400 animate-pulse" />
              </div>
              <div>
                <p className="text-sm font-medium text-stone-900 dark:text-stone-100">Generating follow-up suggestions...</p>
                <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">Analyzing recent interactions, relationship scores, and upcoming events</p>
              </div>
            </div>
            <div className="h-1.5 bg-stone-100 dark:bg-stone-800 rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-teal-500 w-1/4" style={{ animation: "suggestionsIndeterminate 1.5s ease-in-out infinite" }} />
              <style>{`
                @keyframes suggestionsIndeterminate {
                  0% { transform: translateX(-100%); }
                  100% { transform: translateX(400%); }
                }
              `}</style>
            </div>
          </div>
        )}

        {/* Content */}
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((n) => (
              <div key={n} className="h-28 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 animate-pulse" />
            ))}
          </div>
        ) : pendingSuggestions.length === 0 ? (
          /* Empty state */
          <div className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-700 px-6 py-10 sm:p-14 text-center mt-6">
            <div className="w-16 h-16 rounded-full bg-teal-50 dark:bg-teal-950 flex items-center justify-center mx-auto mb-4">
              <Sparkles className="w-8 h-8 text-teal-400" />
            </div>
            <h2 className="text-lg font-bold text-stone-900 dark:text-stone-100 mb-2">No pending suggestions</h2>
            <p className="text-sm text-stone-500 dark:text-stone-400 mb-6">
              Generate new suggestions to get started, or check back later — Ping runs analysis daily.
            </p>
            <button
              onClick={() => { setToastDismissed(false); generateSuggestions.mutate(); }}
              disabled={generateSuggestions.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 min-h-[44px] text-sm font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors shadow-sm"
            >
              <Sparkles className="w-4 h-4" /> Generate new suggestions
            </button>
          </div>
        ) : (
          /* Suggestion cards */
          <div className="animate-in stagger-2 space-y-3">
            {pendingSuggestions.map((suggestion) => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                expanded={expandedId === suggestion.id}
                onToggle={() => setExpandedId(expandedId === suggestion.id ? null : suggestion.id)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
