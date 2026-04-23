"use client";

import { useState, useEffect, useRef, type ReactNode } from "react";
import {
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  MoreVertical,
  type Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { SyncDetails, SyncStatus } from "../_hooks/use-settings-controller";

/* ── Connection badge ── */
export function ConnectionBadge({ connected }: { connected: boolean }) {
  if (connected) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        Connected
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 border border-stone-200 dark:border-stone-700">
      Not connected
    </span>
  );
}

/* ── Success modal ── */
export function SuccessModal({ platform, onClose }: { platform: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-stone-900 rounded-xl p-6 w-full max-w-sm shadow-xl text-center">
        <div className="mx-auto w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-950 flex items-center justify-center mb-4">
          <CheckCircle2 className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
        </div>
        <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-1">{platform} Connected</h3>
        <p className="text-sm text-stone-500 dark:text-stone-400 mb-5">
          Your {platform} account has been successfully linked. You can now sync your data.
        </p>
        <button
          onClick={onClose}
          className="w-full px-4 py-2 text-sm font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors"
        >
          Done
        </button>
      </div>
    </div>
  );
}

/* ── Sync button wrapper ── */
export type SyncPhase = "idle" | "loading" | "success" | "error";

export function SyncButtonWrapper({
  phase,
  children,
}: {
  phase: SyncPhase;
  children: ReactNode;
}) {
  const [showSuccess, setShowSuccess] = useState(false);
  const [showError, setShowError] = useState(false);
  const prevPhase = useRef<SyncPhase>("idle");

  useEffect(() => {
    if (prevPhase.current === "loading" && phase === "success") {
      setShowSuccess(true);
      const t = setTimeout(() => setShowSuccess(false), 2000);
      return () => clearTimeout(t);
    }
    if (prevPhase.current === "loading" && phase === "error") {
      setShowError(true);
      const t = setTimeout(() => setShowError(false), 1500);
      return () => clearTimeout(t);
    }
    prevPhase.current = phase;
  }, [phase]);

  return (
    <div className="relative">
      {children}
      {phase === "loading" && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-b-lg overflow-hidden">
          <div
            className="h-full bg-white/60 rounded-full"
            style={{ animation: "shimmer 1.5s ease-in-out infinite", width: "40%" }}
          />
        </div>
      )}
      {showSuccess && (
        <div className="absolute inset-0 rounded-lg bg-emerald-500/20 pointer-events-none animate-[fadeOut_1.5s_ease-out_forwards]" />
      )}
      {showError && (
        <div className="absolute inset-0 rounded-lg bg-red-500/15 pointer-events-none animate-[fadeOut_1s_ease-out_forwards]" />
      )}
      <style>{`
        @keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(350%); } }
        @keyframes fadeOut { 0% { opacity: 1; } 100% { opacity: 0; } }
      `}</style>
    </div>
  );
}

/* ── Sync result panel ── */
export function SyncResultPanel({
  details,
  status,
}: {
  details: SyncDetails;
  status: SyncStatus;
}) {
  if (status === "idle" || status === "loading") return null;

  const hasStats =
    details.created !== undefined ||
    details.updated !== undefined ||
    details.new_interactions !== undefined;
  const hasErrors = details.errors && details.errors.length > 0;

  return (
    <div
      className={`mt-3 rounded-lg p-3 text-xs ${
        status === "error"
          ? "bg-red-50 dark:bg-red-950 border border-red-100 dark:border-red-800"
          : "bg-emerald-50 dark:bg-emerald-950 border border-emerald-100 dark:border-emerald-800"
      }`}
    >
      {hasStats && (
        <div className="flex items-center gap-3 mb-1">
          {details.new_interactions !== undefined && (
            <span className="text-emerald-700 dark:text-emerald-400">
              {details.new_interactions} new interaction
              {details.new_interactions !== 1 ? "s" : ""}
            </span>
          )}
          {details.created !== undefined && details.created > 0 && (
            <span className="text-teal-700 dark:text-teal-400">
              +{details.created} new contact{details.created !== 1 ? "s" : ""}
            </span>
          )}
          {details.updated !== undefined && details.updated > 0 && (
            <span className="text-teal-700 dark:text-teal-400">{details.updated} updated</span>
          )}
          {details.elapsed !== undefined && (
            <span className="text-stone-500 dark:text-stone-400 ml-auto">{details.elapsed}s</span>
          )}
        </div>
      )}
      {details.errors && details.errors.length > 0 && (
        <div className="mt-2 space-y-1">
          <p className="font-medium text-red-600 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" />
            {details.errors.length} error{details.errors.length > 1 ? "s" : ""}
          </p>
          <ul className="text-red-500 dark:text-red-400 space-y-0.5 max-h-20 overflow-y-auto">
            {details.errors.map((err, i) => (
              <li key={i} className="truncate">
                {err}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!hasStats && !hasErrors && status === "error" && (
        <p className="text-red-600 dark:text-red-400">{details.message || "Sync failed"}</p>
      )}
    </div>
  );
}

/* ── Telegram sync progress card ── */
const PHASE_LABELS: Record<string, string> = {
  chats: "Collecting dialogs...",
  messages: "Syncing messages...",
  groups: "Scanning groups...",
  bios: "Checking bios...",
  done: "Done!",
};

export function TelegramSyncProgressCard({
  progress,
}: {
  progress: {
    active: boolean;
    phase?: string;
    total_dialogs?: number;
    dialogs_processed?: number;
    contacts_found?: number;
    messages_synced?: number;
    started_at?: string;
  };
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!progress.started_at) return;
    const start = new Date(progress.started_at).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [progress.started_at]);

  const phase = progress.phase ?? "";
  const phaseLabel = PHASE_LABELS[phase] ?? phase;
  const total = progress.total_dialogs ?? 0;
  const processed = progress.dialogs_processed ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
  const isDone = phase === "done";

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const elapsedStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

  return (
    <div
      className={cn(
        "mt-3 rounded-lg border p-3 text-xs transition-all",
        isDone
          ? "bg-emerald-50 dark:bg-emerald-950 border-emerald-100 dark:border-emerald-800"
          : "bg-sky-50 dark:bg-sky-950 border-sky-100 dark:border-sky-800"
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span
          className={cn(
            "font-medium flex items-center gap-1.5",
            isDone ? "text-emerald-700 dark:text-emerald-400" : "text-sky-700 dark:text-sky-400"
          )}
        >
          {isDone ? (
            <CheckCircle2 className="w-3.5 h-3.5" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          )}
          {phaseLabel}
        </span>
        {progress.started_at && <span className="text-stone-400 dark:text-stone-500">{elapsedStr}</span>}
      </div>
      {total > 0 && (
        <div className="mb-2">
          <div className="flex justify-between text-stone-500 dark:text-stone-400 mb-1">
            <span>
              {processed} / {total} dialogs
            </span>
            <span>{pct}%</span>
          </div>
          <div className="w-full h-1.5 bg-stone-200 dark:bg-stone-700 rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                isDone ? "bg-emerald-500" : "bg-sky-400 animate-pulse"
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}
      <div className="flex items-center gap-3 text-stone-500 dark:text-stone-400">
        <span>{progress.contacts_found ?? 0} contacts</span>
        <span className="text-stone-300 dark:text-stone-600">·</span>
        <span>{progress.messages_synced ?? 0} messages</span>
      </div>
    </div>
  );
}

/* ── Toggle switch ── */
export function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-[22px] w-10 shrink-0 cursor-pointer rounded-full transition-colors duration-200",
        checked ? "bg-teal-600" : "bg-stone-300 dark:bg-stone-600"
      )}
    >
      <span
        className={cn(
          "pointer-events-none inline-block h-[18px] w-[18px] rounded-full bg-white shadow-sm transition-transform duration-200",
          checked ? "translate-x-[20px]" : "translate-x-[2px]",
          "mt-[2px]"
        )}
      />
    </button>
  );
}

/* ── Kebab menu ── */
export function KebabMenu({
  items,
}: {
  items: Array<{
    icon: typeof Settings;
    label: string;
    danger?: boolean;
    onClick?: () => void;
  }>;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="p-1.5 rounded-md text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
      >
        <MoreVertical className="w-4 h-4" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-52 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg py-1 z-50">
          {items.map((item, i) =>
            item.label === "---" ? (
              <div key={i} className="my-1 h-px bg-stone-100 dark:bg-stone-800" />
            ) : (
              <button
                key={i}
                onClick={() => {
                  setOpen(false);
                  item.onClick?.();
                }}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 text-sm w-full text-left",
                  item.danger
                    ? "text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950"
                    : "text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
                )}
              >
                <item.icon
                  className={cn("w-4 h-4", item.danger ? "" : "text-stone-400 dark:text-stone-500")}
                />
                {item.label}
              </button>
            )
          )}
        </div>
      )}
    </div>
  );
}

/* ── Platform SVG icons ── */
export function GmailIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path d="M2 6l10 7 10-7" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" />
      <rect x="2" y="4" width="20" height="16" rx="2" stroke="#dc2626" strokeWidth="2" fill="none" />
    </svg>
  );
}

export function TelegramIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path
        d="M21 3L9.5 13.5M21 3l-7 18-3.5-7.5L3 10l18-7z"
        stroke="#0284c7"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function TwitterIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="text-stone-500 dark:text-stone-400">
      <path
        d="M4 4l11.7 16h4.3L8.3 4H4zm1.7 0L20 20M20 4l-7.3 8"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function WhatsAppIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path
        d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"
        fill="#25D366"
      />
      <path
        d="M12 2C6.477 2 2 6.477 2 12c0 1.89.525 3.66 1.438 5.168L2 22l4.832-1.438A9.955 9.955 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2z"
        stroke="#25D366"
        strokeWidth="2"
        fill="none"
      />
    </svg>
  );
}
