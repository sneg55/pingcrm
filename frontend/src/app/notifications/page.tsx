"use client";

import { Bell, Mail, Sparkles, Activity, Settings, CheckCheck, ScanSearch, RefreshCw } from "lucide-react";
import { useNotifications, useMarkRead, useMarkAllRead } from "@/hooks/use-notifications";
import type { AppNotification } from "@/hooks/use-notifications";
import { EmptyState } from "@/components/empty-state";
import { formatDistanceToNow } from "date-fns";
import { useRouter } from "next/navigation";

const typeIcons: Record<string, typeof Bell> = {
  suggestion: Sparkles,
  event: Activity,
  digest: Mail,
  system: Settings,
  bio_change: ScanSearch,
  sync: RefreshCw,
};

function NotificationRow({ notification }: { notification: AppNotification }) {
  const router = useRouter();
  const markRead = useMarkRead();
  const Icon = typeIcons[notification.notification_type] || Bell;

  const handleClick = () => {
    if (!notification.read) {
      markRead.mutate(notification.id);
    }
    if (notification.link) {
      router.push(notification.link);
    }
  };

  return (
    <button
      onClick={handleClick}
      className={`w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors border-b border-gray-100 ${
        notification.read ? "opacity-60" : ""
      }`}
    >
      <div className={`mt-0.5 p-2 rounded-full ${notification.read ? "bg-gray-100" : "bg-blue-50"}`}>
        <Icon className={`w-4 h-4 ${notification.read ? "text-gray-400" : "text-blue-600"}`} />
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-sm ${notification.read ? "text-gray-600" : "text-gray-900 font-medium"}`}>
          {notification.title}
        </p>
        {notification.body && (
          <p className="text-sm text-gray-500 mt-0.5 line-clamp-2">{notification.body}</p>
        )}
        {notification.created_at && (
          <p className="text-xs text-gray-400 mt-1">
            {formatDistanceToNow(new Date(notification.created_at), { addSuffix: true })}
          </p>
        )}
      </div>
      {!notification.read && <div className="w-2 h-2 rounded-full bg-blue-600 mt-2 shrink-0" />}
    </button>
  );
}

export default function NotificationsPage() {
  const { data, isLoading } = useNotifications();
  const markAllRead = useMarkAllRead();

  const notifications = data?.data ?? [];
  const hasUnread = notifications.some((n) => !n.read);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Notifications</h1>
          {hasUnread && (
            <button
              onClick={() => markAllRead.mutate()}
              disabled={markAllRead.isPending}
              className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800"
            >
              <CheckCheck className="w-4 h-4" />
              Mark all as read
            </button>
          )}
        </div>

        {isLoading && (
          <div className="text-center py-12 text-gray-400">Loading...</div>
        )}

        {!isLoading && notifications.length === 0 && (
          <EmptyState
            icon={Bell}
            title="No notifications"
            description="You're all caught up. Notifications will appear here when there's activity in your network."
          />
        )}

        {notifications.length > 0 && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            {notifications.map((n) => (
              <NotificationRow key={n.id} notification={n} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
