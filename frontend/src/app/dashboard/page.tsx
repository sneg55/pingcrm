"use client";

import { type ReactNode } from "react";
import Link from "next/link";
import {
  Users,
  HeartPulse,
  MessageCircle,
  Mail,
  Twitter,
  Sparkles,
  Plug,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { ContactAvatar } from "@/components/contact-avatar";
import { AnimatedNumber } from "@/components/animated-number";
import { ScoreBadge } from "@/components/score-badge";
import {
  useDashboardStats,
  type OverdueContact,
  type ActivityEvent,
} from "@/hooks/use-dashboard";

import { DashboardSuggestionCard } from "./_components/suggestion-card";


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
      className="card-hover flex items-center gap-3 bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-3.5 hover:border-stone-300 dark:hover:border-stone-600 transition-colors overflow-hidden"
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
      className="card-hover flex items-center gap-3 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-md p-1 -mx-1 transition-colors"
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
// eslint-disable-next-line sonarjs/cognitive-complexity -- top-level page composes many widgets with conditional loading/empty states; refactor tracked separately
export default function DashboardPage() {
  const { suggestions, stats, statsReady, overdueContacts, recentActivity, isLoading } =
    useDashboardStats();

  const allPending = suggestions.filter((s) => s.status === "pending");
  const pendingSuggestions = allPending.slice(0, 5);

  // Only show empty state when stats API has confirmed total=0.
  // Without statsReady, a slow/failed stats fetch would flash the empty state.
  const isEmpty = statsReady && stats.total === 0 && !isLoading;

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
          <div className="animate-in stagger-1 grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
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
              <div className="animate-in stagger-2">
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
                      <div key={n} className="h-20 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 shimmer" />
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
              <div className="animate-in stagger-3">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-display font-semibold text-stone-900 dark:text-stone-100">
                    Recent Activity
                  </h2>
                  <Link href="/contacts?sort=interaction" className="text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300">
                    View all &rarr;
                  </Link>
                </div>
                {isLoading ? (
                  <div className="space-y-3">
                    {[1, 2, 3].map((n) => (
                      <div key={n} className="h-16 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 shimmer" />
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
            <div className="lg:col-span-2 space-y-6 animate-in stagger-2">
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
                      <div key={n} className="h-10 rounded-md bg-stone-100 dark:bg-stone-800 shimmer" />
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
          <span className="inline-block w-12 h-7 bg-stone-100 dark:bg-stone-800 rounded shimmer" />
        ) : (
          <AnimatedNumber value={value} className="font-mono-data text-2xl font-medium text-stone-900 dark:text-stone-100 tracking-tight" />
        )}
      </p>
      <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">{label}</p>
    </div>
  );
}
