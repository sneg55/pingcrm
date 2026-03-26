"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import {
  Users,
  HeartPulse,
  MessageCircle,
  Mail,
  Twitter,
  Sparkles,
  Clock,
  X,
  ChevronDown,
  UserPlus,
  Plug,
  FileDown,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { ContactAvatar } from "@/components/contact-avatar";
import { ScoreBadge } from "@/components/score-badge";
import { MessageEditor } from "@/components/message-editor";
import {
  useUpdateSuggestion,
  useSendMessage,
  type Suggestion,
} from "@/hooks/use-suggestions";
import {
  useDashboardStats,
  type OverdueContact,
  type ActivityEvent,
} from "@/hooks/use-dashboard";

type Channel = "email" | "telegram" | "twitter";

const channelIcons: Record<Channel, ReactNode> = {
  email: <Mail className="w-3.5 h-3.5" />,
  telegram: <MessageCircle className="w-3.5 h-3.5" />,
  twitter: <Twitter className="w-3.5 h-3.5" />,
};

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

function getScoreTier(score: number | null | undefined): { label: string; color: string } {
  if (score == null) return { label: "New", color: "bg-sky-50 dark:bg-sky-950 text-sky-600 dark:text-sky-400 border-sky-200 dark:border-sky-800" };
  if (score >= 70) return { label: "Strong", color: "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800" };
  if (score >= 30) return { label: "Warm", color: "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800" };
  return { label: "Cold", color: "bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800" };
}

// ---------------------------------------------------------------------------
// SuggestionCard — expandable with inline composer
// ---------------------------------------------------------------------------
function DashboardSuggestionCard({ suggestion }: { suggestion: Suggestion }) {
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
  const tier = getScoreTier(null); // contact doesn't carry score in suggestion payload

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
      void navigator.clipboard.writeText(message).catch(() => {});
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

          {/* Expanded composer */}
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

              {/* Snooze / Dismiss row */}
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

// ---------------------------------------------------------------------------
// Activity timeline icons
// ---------------------------------------------------------------------------
const platformStyles: Record<string, { bg: string; icon: ReactNode }> = {
  telegram: {
    bg: "bg-sky-100 dark:bg-sky-900",
    icon: <MessageCircle className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />,
  },
  email: {
    bg: "bg-red-100 dark:bg-red-900",
    icon: <Mail className="w-3.5 h-3.5 text-red-500 dark:text-red-400" />,
  },
  twitter: {
    bg: "bg-stone-100 dark:bg-stone-800",
    icon: <Twitter className="w-3.5 h-3.5 text-stone-500 dark:text-stone-400" />,
  },
};

function ActivityItem({ event }: { event: ActivityEvent }) {
  const style = platformStyles[event.platform] ?? platformStyles.email;
  const dirLabel = event.direction === "inbound" ? "from" : "to";
  return (
    <Link
      href={`/contacts/${event.contact_id}`}
      className="flex items-center gap-3 bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-3.5 hover:border-stone-300 dark:hover:border-stone-600 transition-colors overflow-hidden"
    >
      <ContactAvatar
        avatarUrl={event.contact_avatar_url}
        name={event.contact_name || "?"}
        size="sm"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
          {event.contact_name}
        </p>
        <p className="text-xs text-stone-500 dark:text-stone-400 truncate">
          {event.content_preview || `${event.platform} ${dirLabel === "from" ? "message received" : "message sent"}`}
        </p>
      </div>
      <div className="flex flex-col items-end shrink-0 gap-1">
        <div className={`w-6 h-6 rounded-full ${style.bg} flex items-center justify-center`}>
          {style.icon}
        </div>
        <span className="text-[10px] text-stone-400 dark:text-stone-500">
          {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
        </span>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Overdue contact row
// ---------------------------------------------------------------------------
function OverdueRow({ contact }: { contact: OverdueContact }) {
  const name =
    contact.full_name ??
    ([contact.given_name, contact.family_name].filter(Boolean).join(" ") || "Unnamed");
  const daysLabel =
    contact.days_overdue <= 0
      ? "due today"
      : `${contact.days_overdue}d overdue`;
  const isUrgent = contact.days_overdue > 5;

  return (
    <Link
      href={`/contacts/${contact.id}`}
      className="flex items-center gap-3 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-md p-1 -mx-1 transition-colors"
    >
      <ContactAvatar
        avatarUrl={contact.avatar_url}
        name={name}
        size="xs"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">{name}</p>
        <p className="text-xs text-stone-400 dark:text-stone-500">
          {contact.last_interaction_at
            ? `${formatDistanceToNow(new Date(contact.last_interaction_at))} since last contact`
            : "No interactions"}
        </p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <span className={`w-1.5 h-1.5 rounded-full ${isUrgent ? "bg-red-400" : "bg-amber-400"}`} />
        <span className={`text-[11px] font-mono ${isUrgent ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400"}`}>
          {daysLabel}
        </span>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------
export default function DashboardPage() {
  const { suggestions, stats, overdueContacts, recentActivity, isLoading } =
    useDashboardStats();

  const allPending = suggestions.filter((s) => s.status === "pending");
  const pendingSuggestions = allPending.slice(0, 5);

  const isEmpty = stats.total === 0 && !isLoading;

  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950 overflow-x-hidden">
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-display font-bold text-stone-900 dark:text-stone-100">Dashboard</h1>
          <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">
            {pendingSuggestions.length > 0 || overdueContacts.length > 0 ? (
              <>
                You have{" "}
                {pendingSuggestions.length > 0 && (
                  <strong className="text-teal-700 dark:text-teal-400">
                    {allPending.length} pending suggestion{allPending.length !== 1 ? "s" : ""}
                  </strong>
                )}
                {pendingSuggestions.length > 0 && overdueContacts.length > 0 && " and "}
                {overdueContacts.length > 0 && (
                  <strong className="text-stone-700 dark:text-stone-300">
                    {overdueContacts.length} contact{overdueContacts.length !== 1 ? "s" : ""}
                  </strong>
                )}
                {overdueContacts.length > 0 && " need attention this week."}
              </>
            ) : (
              "Your networking overview"
            )}
          </p>
        </div>

        {/* Empty state — inline onboarding */}
        {isEmpty && (
          <div className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-700 p-8 mb-8">
            <div className="text-center mb-6">
              <h2 className="text-lg font-display font-bold text-stone-900 dark:text-stone-100 mb-1">Connect your accounts to get started</h2>
              <p className="text-sm text-stone-500 dark:text-stone-400">
                Ping will sync your contacts and interactions automatically.
              </p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <Link
                href="/settings"
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-stone-200 dark:border-stone-700 hover:border-teal-300 dark:hover:border-teal-700 hover:bg-teal-50 dark:hover:bg-teal-950 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" className="w-7 h-7">
                  <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.6 3-2.3 5.5-4.9 7.2v6h7.9c4.6-4.3 7.8-10.6 7.8-17.2z" />
                  <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.9-6c-2.1 1.4-4.8 2.3-8 2.3-6.1 0-11.3-4.1-13.1-9.7H2.7v6.2C6.7 43.1 14.8 48 24 48z" />
                  <path fill="#FBBC05" d="M10.9 28.8c-.5-1.4-.7-2.9-.7-4.8s.3-3.3.7-4.8v-6.2H2.7C1 16.4 0 20.1 0 24s1 7.6 2.7 11z" />
                  <path fill="#EA4335" d="M24 9.5c3.4 0 6.5 1.2 8.9 3.5l6.6-6.6C35.9 2.4 30.4 0 24 0 14.8 0 6.7 4.9 2.7 13l8.2 6.2C12.7 13.6 17.9 9.5 24 9.5z" />
                </svg>
                <span className="text-xs font-medium text-stone-700 dark:text-stone-300">Google</span>
              </Link>
              <Link
                href="/settings"
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-stone-200 dark:border-stone-700 hover:border-sky-300 dark:hover:border-sky-700 hover:bg-sky-50 dark:hover:bg-sky-950 transition-colors"
              >
                <MessageCircle className="w-7 h-7 text-sky-500" />
                <span className="text-xs font-medium text-stone-700 dark:text-stone-300">Telegram</span>
              </Link>
              <Link
                href="/settings"
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-stone-200 dark:border-stone-700 hover:border-stone-400 dark:hover:border-stone-500 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
              >
                <Twitter className="w-7 h-7 text-stone-600 dark:text-stone-400" />
                <span className="text-xs font-medium text-stone-700 dark:text-stone-300">Twitter/X</span>
              </Link>
              <Link
                href="/settings"
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-stone-200 dark:border-stone-700 hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950 transition-colors"
              >
                <Plug className="w-7 h-7 text-blue-600 dark:text-blue-400" />
                <span className="text-xs font-medium text-stone-700 dark:text-stone-300">LinkedIn</span>
              </Link>
            </div>
            <div className="text-center">
              <Link
                href="/settings"
                className="text-xs text-stone-400 dark:text-stone-500 hover:text-teal-600 dark:hover:text-teal-400"
              >
                or import a CSV file
              </Link>
            </div>
          </div>
        )}

        {/* Stat cards */}
        {!isEmpty && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
            <StatCard
              icon={<Users className="w-4 h-4 text-teal-600 dark:text-teal-400" />}
              iconBg="bg-teal-50 dark:bg-teal-950"
              value={stats.total}
              label="Total contacts"
              isLoading={isLoading}
            />
            <StatCard
              icon={<HeartPulse className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />}
              iconBg="bg-emerald-50 dark:bg-emerald-950"
              value={stats.active + stats.strong}
              label="Active relationships"
              isLoading={isLoading}
              delay="50ms"
              previousValue={stats.activeLastWeek}
            />
            <StatCard
              icon={<MessageCircle className="w-4 h-4 text-sky-600 dark:text-sky-400" />}
              iconBg="bg-sky-50 dark:bg-sky-950"
              value={stats.interactionsThisWeek}
              label="Interactions this week"
              isLoading={isLoading}
              delay="100ms"
              previousValue={stats.interactionsLastWeek}
            />
          </div>
        )}

        {/* Two-column layout */}
        {!isEmpty && (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 lg:gap-6">
            {/* LEFT 3/5: Pending Follow-ups + Recent Activity */}
            <div className="lg:col-span-3 space-y-6">
              {/* Pending Follow-ups */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-display font-semibold text-stone-900 dark:text-stone-100">
                    Pending Follow-ups
                  </h2>
                  <Link href="/suggestions" className="text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300">
                    View all &rarr;
                  </Link>
                </div>

                {isLoading ? (
                  <div className="space-y-3">
                    {[1, 2, 3].map((n) => (
                      <div key={n} className="h-20 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 animate-pulse" />
                    ))}
                  </div>
                ) : pendingSuggestions.length === 0 ? (
                  <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-8 text-center">
                    <Sparkles className="w-8 h-8 text-stone-200 dark:text-stone-700 mx-auto mb-2" />
                    <p className="text-sm text-stone-400 dark:text-stone-500">
                      No pending suggestions.{" "}
                      <Link href="/suggestions" className="text-teal-600 dark:text-teal-400 hover:underline">
                        Generate suggestions
                      </Link>
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {pendingSuggestions.map((s) => (
                      <DashboardSuggestionCard key={s.id} suggestion={s} />
                    ))}
                  </div>
                )}
              </div>

              {/* Recent Activity */}
              <div>
                <h2 className="text-sm font-display font-semibold text-stone-900 dark:text-stone-100 mb-3">
                  Recent Activity
                </h2>
                {isLoading ? (
                  <div className="space-y-3">
                    {[1, 2, 3].map((n) => (
                      <div key={n} className="h-16 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 animate-pulse" />
                    ))}
                  </div>
                ) : recentActivity.length === 0 ? (
                  <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-8 text-center">
                    <MessageCircle className="w-8 h-8 text-stone-200 dark:text-stone-700 mx-auto mb-2" />
                    <p className="text-sm text-stone-400 dark:text-stone-500">No recent activity</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {recentActivity.map((event) => (
                      <ActivityItem key={`${event.contact_id}-${event.timestamp}`} event={event} />
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* RIGHT 2/5: Needs Attention */}
            <div className="lg:col-span-2 space-y-6">
              <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-display font-semibold text-stone-900 dark:text-stone-100">
                    Needs Attention
                  </h2>
                  {overdueContacts.length > 0 && (
                    <span className="text-[11px] font-medium text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-950 px-2 py-0.5 rounded-full">
                      {overdueContacts.length} contact{overdueContacts.length !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
                <p className="text-xs text-stone-400 dark:text-stone-500 mb-4">High-priority contacts going silent</p>
                {isLoading ? (
                  <div className="space-y-3">
                    {[1, 2, 3].map((n) => (
                      <div key={n} className="h-10 rounded-md bg-stone-100 dark:bg-stone-800 animate-pulse" />
                    ))}
                  </div>
                ) : overdueContacts.length === 0 ? (
                  <p className="text-sm text-stone-400 dark:text-stone-500 text-center py-4">
                    All caught up!
                  </p>
                ) : (
                  <div className="space-y-3">
                    {overdueContacts.map((contact) => (
                      <OverdueRow key={contact.id} contact={contact} />
                    ))}
                  </div>
                )}
                {overdueContacts.length > 0 && (
                  <Link
                    href="/contacts?sort=overdue"
                    className="block text-center text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 mt-4 pt-3 border-t border-stone-100 dark:border-stone-800"
                  >
                    View all &rarr;
                  </Link>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat card sub-component
// ---------------------------------------------------------------------------
function TrendArrow({ current, previous }: { current: number; previous: number }) {
  if (previous === 0 || current === previous) return null;
  const isUp = current > previous;
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`w-5 h-5 ${isUp ? "text-teal-500 dark:text-teal-400" : "text-pink-500 dark:text-pink-400"}`}
    >
      {isUp ? (
        <path d="M7 17L17 7M17 7H10M17 7V14" />
      ) : (
        <path d="M7 7L17 17M17 17H10M17 17V10" />
      )}
    </svg>
  );
}

function StatCard({
  icon,
  iconBg,
  value,
  label,
  isLoading,
  delay,
  previousValue,
}: {
  icon: ReactNode;
  iconBg: string;
  value: number;
  label: string;
  isLoading: boolean;
  delay?: string;
  previousValue?: number;
}) {
  return (
    <div
      className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 transition-all hover:shadow-md hover:-translate-y-0.5 animate-fade-in-up"
      style={delay ? { animationDelay: delay } : undefined}
    >
      <div className="flex items-center justify-between mb-3">
        <div className={`w-9 h-9 rounded-lg ${iconBg} flex items-center justify-center`}>
          {icon}
        </div>
        {!isLoading && previousValue !== undefined && (
          <TrendArrow current={value} previous={previousValue} />
        )}
      </div>
      <p className="font-mono-data text-2xl font-medium text-stone-900 dark:text-stone-100 tracking-tight">
        {isLoading ? (
          <span className="inline-block w-12 h-7 bg-stone-100 dark:bg-stone-800 rounded animate-pulse" />
        ) : (
          value.toLocaleString()
        )}
      </p>
      <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">{label}</p>
    </div>
  );
}
