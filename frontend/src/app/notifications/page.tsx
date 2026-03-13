"use client";

import { useState } from "react";
import {
  Bell,
  Copy,
  Check,
  Mail,
  Sparkles,
  Activity,
  Settings,
  CheckCheck,
  ScanSearch,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import {
  useNotifications,
  useMarkRead,
  useMarkAllRead,
} from "@/hooks/use-notifications";
import type { AppNotification } from "@/hooks/use-notifications";
import { formatDistanceToNow, isToday, isYesterday, differenceInDays } from "date-fns";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

/* ── Type → icon + color config ── */
interface TypeStyle {
  Icon: typeof Bell;
  bg: string;
  text: string;
}

const typeStyles: Record<string, TypeStyle> = {
  suggestion: { Icon: Sparkles, bg: "bg-teal-50", text: "text-teal-600" },
  event: { Icon: Activity, bg: "bg-amber-50", text: "text-amber-500" },
  digest: { Icon: Mail, bg: "bg-emerald-50", text: "text-emerald-600" },
  system: { Icon: Settings, bg: "bg-stone-100", text: "text-stone-500" },
  bio_change: { Icon: ScanSearch, bg: "bg-violet-50", text: "text-violet-500" },
  sync: { Icon: RefreshCw, bg: "bg-sky-50", text: "text-sky-500" },
};

const defaultStyle: TypeStyle = { Icon: Bell, bg: "bg-stone-100", text: "text-stone-500" };

function getStyle(type: string): TypeStyle {
  return typeStyles[type] ?? defaultStyle;
}

/* ── Filter tabs ── */
type FilterKey = "all" | "unread" | "suggestion" | "event" | "system";

const filters: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "suggestion", label: "Suggestions" },
  { key: "event", label: "Events" },
  { key: "system", label: "System" },
];

function matchesFilter(n: AppNotification, filter: FilterKey): boolean {
  if (filter === "all") return true;
  if (filter === "unread") return !n.read;
  if (filter === "suggestion") return n.notification_type === "suggestion" || n.notification_type === "digest";
  if (filter === "event") return n.notification_type === "event" || n.notification_type === "bio_change";
  if (filter === "system") return n.notification_type === "system" || n.notification_type === "sync";
  return true;
}

/* ── Date grouping ── */
function dateGroup(dateStr: string | null): string {
  if (!dateStr) return "Older";
  const d = new Date(dateStr);
  if (isToday(d)) return "Today";
  if (isYesterday(d)) return "Yesterday";
  if (differenceInDays(new Date(), d) <= 7) return "This Week";
  return "Older";
}

/* ── Detail parsing ── */
function parseBody(body: string | null): { summary: string; details: string } {
  if (!body) return { summary: "", details: "" };
  const idx = body.indexOf("\n\n");
  if (idx === -1) return { summary: body, details: "" };
  return { summary: body.slice(0, idx), details: body.slice(idx + 2) };
}

/* ── CTA label based on type ── */
function ctaLabel(type: string): string {
  switch (type) {
    case "suggestion": return "View suggestions";
    case "digest": return "View all contacts";
    case "event": return "View contact";
    case "bio_change": return "View contact";
    case "system":
    case "sync":
      return "Go to settings";
    default: return "View details";
  }
}

/* ═══════════════ NOTIFICATION ROW ═══════════════ */

function CopyButton({ text: copyText }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    void navigator.clipboard.writeText(copyText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={handleCopy}
      title="Copy error message"
      className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs text-stone-400 hover:text-stone-600 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function NotificationRow({
  notification,
  expanded,
  onToggle,
}: {
  notification: AppNotification;
  expanded: boolean;
  onToggle: () => void;
}) {
  const router = useRouter();
  const markRead = useMarkRead();
  const { Icon, bg, text } = getStyle(notification.notification_type);
  const { summary, details } = parseBody(notification.body);
  const isRead = notification.read;
  const isSystem = notification.notification_type === "system" || notification.notification_type === "sync";

  const handleClick = () => {
    if (!isRead) markRead.mutate(notification.id);
    if (details) {
      onToggle();
    } else if (notification.link) {
      router.push(notification.link);
    }
  };

  const handleCta = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (notification.link) router.push(notification.link);
  };

  return (
    <div className={cn("notif-row", isRead && "read")}>
      <div
        className="flex items-start gap-4 px-5 py-4 cursor-pointer hover:bg-stone-50 transition-colors"
        onClick={handleClick}
      >
        {/* Icon */}
        <div className={cn("shrink-0 w-9 h-9 rounded-full flex items-center justify-center mt-0.5", bg, isRead && "opacity-65")}>
          <Icon className={cn("w-4 h-4", text)} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className={cn("text-sm", isRead ? "font-medium text-stone-700" : "font-semibold text-stone-900")}>
            {notification.title}
          </p>
          {summary && (
            <div className="flex items-start gap-1.5 mt-0.5">
              <p className={cn("text-sm text-stone-500 leading-snug flex-1", isRead && "opacity-60")}>
                {summary}
              </p>
              {isSystem && <CopyButton text={notification.body ?? notification.title} />}
            </div>
          )}
        </div>

        {/* Time + unread dot */}
        <div className="flex flex-col items-end gap-2 shrink-0">
          <span className={cn("text-xs text-stone-400 whitespace-nowrap", isRead && "opacity-50")}>
            {notification.created_at
              ? formatDistanceToNow(new Date(notification.created_at), { addSuffix: true })
              : ""}
          </span>
          {!isRead && <span className="w-2 h-2 rounded-full bg-teal-500" />}
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && details && (
        <div className="px-5 pb-4 ml-[52px]">
          <div className="bg-stone-50 rounded-lg p-3 border border-stone-100">
            <div className="flex items-start justify-between gap-2">
              <pre className="text-xs font-mono text-stone-600 whitespace-pre-wrap flex-1">{details}</pre>
              {isSystem && <CopyButton text={details} />}
            </div>
          </div>
          {notification.link && (
            <button
              onClick={handleCta}
              className="inline-flex items-center gap-1 mt-2 text-xs font-medium text-teal-600 hover:text-teal-700"
            >
              {ctaLabel(notification.notification_type)} <ArrowRight className="w-3 h-3" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════════ PAGE ═══════════════ */

export default function NotificationsPage() {
  const { data, isLoading } = useNotifications();
  const markAllRead = useMarkAllRead();
  const [filter, setFilter] = useState<FilterKey>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const allNotifications = (data?.data ?? []) as AppNotification[];
  const filtered = allNotifications.filter((n) => matchesFilter(n, filter));
  const unreadCount = allNotifications.filter((n) => !n.read).length;

  /* Group by date */
  const groups: { label: string; items: AppNotification[] }[] = [];
  const groupOrder = ["Today", "Yesterday", "This Week", "Older"];
  const groupMap = new Map<string, AppNotification[]>();

  for (const n of filtered) {
    const g = dateGroup(n.created_at);
    if (!groupMap.has(g)) groupMap.set(g, []);
    groupMap.get(g)!.push(n);
  }

  for (const label of groupOrder) {
    const items = groupMap.get(label);
    if (items && items.length > 0) groups.push({ label, items });
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <main className="max-w-3xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-stone-900">Notifications</h1>
            {unreadCount > 0 && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-teal-100 text-teal-700">
                {unreadCount} unread
              </span>
            )}
          </div>
          {unreadCount > 0 && (
            <button
              onClick={() => markAllRead.mutate()}
              disabled={markAllRead.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-teal-600 hover:bg-teal-50 rounded-lg transition-colors disabled:opacity-50"
            >
              <CheckCheck className="w-4 h-4" />
              Mark all as read
            </button>
          )}
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 mb-6">
          {filters.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                "px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors",
                filter === f.key
                  ? "bg-teal-600 text-white"
                  : "bg-stone-100 text-stone-600 hover:bg-stone-200"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {isLoading ? (
          <div className="bg-white rounded-xl border border-stone-200 divide-y divide-stone-100">
            {[1, 2, 3].map((n) => (
              <div key={n} className="h-20 animate-pulse" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          /* Empty state */
          <div className="bg-white rounded-xl border border-stone-200 p-12 text-center">
            <div className="w-14 h-14 rounded-full bg-teal-50 flex items-center justify-center mx-auto mb-4">
              <Bell className="w-7 h-7 text-teal-400" />
            </div>
            <h2 className="text-base font-bold text-stone-900 mb-1">You&apos;re all caught up</h2>
            <p className="text-sm text-stone-500 max-w-sm mx-auto">
              Notifications will appear here when there&apos;s activity in your network.
            </p>
          </div>
        ) : (
          /* Notification list */
          <div className="bg-white rounded-xl border border-stone-200 divide-y divide-stone-100 overflow-hidden">
            {groups.map((group, gi) => (
              <div key={group.label}>
                {/* Group header */}
                <div className={cn("px-5 py-2.5 bg-stone-50", gi === 0 && "rounded-t-xl")}>
                  <span className="text-xs font-semibold text-stone-400 uppercase tracking-wide">
                    {group.label}
                  </span>
                </div>
                {/* Rows */}
                {group.items.map((n) => (
                  <div key={n.id} className="border-t border-stone-100">
                    <NotificationRow
                      notification={n}
                      expanded={expandedId === n.id}
                      onToggle={() => setExpandedId(expandedId === n.id ? null : n.id)}
                    />
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
