"use client";

import Link from "next/link";
import { MessageCircle, Mail, Twitter } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { type ReactNode } from "react";
import { ContactAvatar } from "@/components/contact-avatar";
import { type ActivityEvent } from "@/hooks/use-dashboard";

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

interface Props {
  isLoading: boolean;
  recentActivity: ActivityEvent[];
}

export function RecentActivityWidget({ isLoading, recentActivity }: Props) {
  return (
    <div className="animate-in stagger-3">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-display font-semibold text-stone-900 dark:text-stone-100">
          Recent Activity
        </h2>
        <Link
          href="/contacts?sort=interaction"
          className="text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300"
        >
          View all &rarr;
        </Link>
      </div>
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-16 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 shimmer"
            />
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
  );
}
