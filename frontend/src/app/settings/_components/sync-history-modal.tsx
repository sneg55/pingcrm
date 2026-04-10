"use client";

import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { X, CheckCircle2, AlertCircle, Clock, Copy, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";

interface SyncEvent {
  id: string;
  platform: string;
  sync_type: string;
  status: string;
  records_created: number;
  records_updated: number;
  records_failed: number;
  duration_ms: number | null;
  error_message: string | null;
  details: string | null;
  started_at: string;
  completed_at: string | null;
}

interface SyncHistoryModalProps {
  platform: string;
  onClose: () => void;
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
    " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

const statusConfig: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
  success: { icon: CheckCircle2, color: "text-emerald-500", label: "Success" },
  failed: { icon: AlertCircle, color: "text-red-500", label: "Failed" },
  started: { icon: Clock, color: "text-amber-500", label: "Running" },
  partial: { icon: AlertCircle, color: "text-amber-500", label: "Partial" },
};

export function SyncHistoryModal({ platform, onClose }: SyncHistoryModalProps) {
  const [events, setEvents] = useState<SyncEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const fetchEvents = useCallback(async () => {
    try {
      const { data } = await client.GET("/api/v1/sync-history", {
        params: { query: { platform, limit: 50 } },
      });
      setEvents(((data as any)?.data ?? []) as SyncEvent[]);
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  }, [platform]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const handleCopyError = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  const platformLabel = platform.charAt(0).toUpperCase() + platform.slice(1);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" role="dialog" aria-modal="true">
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100 dark:border-stone-800">
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">
            {platformLabel} Sync History
          </h3>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-auto flex-1 px-5 py-3">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-stone-100 dark:bg-stone-800 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : events.length === 0 ? (
            <p className="text-sm text-stone-400 dark:text-stone-500 text-center py-8">
              No sync events recorded yet. Sync events will appear here after the next sync.
            </p>
          ) : (
            <div className="space-y-2">
              {events.map((event) => {
                const cfg = statusConfig[event.status] || statusConfig.started;
                const StatusIcon = cfg.icon;
                const isExpanded = expandedId === event.id;

                return (
                  <div
                    key={event.id}
                    className="border border-stone-200 dark:border-stone-700 rounded-lg overflow-hidden"
                  >
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : event.id)}
                      className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-stone-50 dark:hover:bg-stone-800/50 transition-colors"
                    >
                      <StatusIcon className={cn("w-4 h-4 shrink-0", cfg.color)} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-stone-900 dark:text-stone-100">
                            {cfg.label}
                          </span>
                          <span className="text-[10px] text-stone-400 dark:text-stone-500 capitalize">
                            {event.sync_type}
                          </span>
                        </div>
                        <span className="text-[11px] text-stone-400 dark:text-stone-500">
                          {formatTime(event.started_at)}
                        </span>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-xs text-stone-600 dark:text-stone-300">
                          +{event.records_created}
                          {event.records_failed > 0 && (
                            <span className="text-red-500 ml-1">/{event.records_failed} err</span>
                          )}
                        </div>
                        <div className="text-[10px] text-stone-400 dark:text-stone-500">
                          {formatDuration(event.duration_ms)}
                        </div>
                      </div>
                      <ChevronDown className={cn(
                        "w-3.5 h-3.5 text-stone-400 transition-transform shrink-0",
                        isExpanded && "rotate-180"
                      )} />
                    </button>

                    {isExpanded && (
                      <div className="px-3 pb-3 pt-1 border-t border-stone-100 dark:border-stone-800 space-y-2">
                        <div className="grid grid-cols-3 gap-2 text-[11px]">
                          <div>
                            <span className="text-stone-400 dark:text-stone-500">Created</span>
                            <p className="font-medium text-stone-700 dark:text-stone-300">{event.records_created}</p>
                          </div>
                          <div>
                            <span className="text-stone-400 dark:text-stone-500">Updated</span>
                            <p className="font-medium text-stone-700 dark:text-stone-300">{event.records_updated}</p>
                          </div>
                          <div>
                            <span className="text-stone-400 dark:text-stone-500">Failed</span>
                            <p className="font-medium text-stone-700 dark:text-stone-300">{event.records_failed}</p>
                          </div>
                        </div>

                        {event.error_message && (
                          <div className="relative">
                            <pre className="text-[10px] bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300 rounded p-2 overflow-x-auto max-h-24">
                              {event.error_message}
                            </pre>
                            <button
                              onClick={() => handleCopyError(event.error_message!, event.id)}
                              className="absolute top-1 right-1 p-1 rounded bg-white/80 dark:bg-stone-900/80 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
                              title="Copy error"
                            >
                              {copiedId === event.id ? (
                                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
