"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Trash2, AlertTriangle, Users } from "lucide-react";
import { Toggle } from "./shared";
import { client } from "@/lib/api-client";

type PlatformSyncConfig = {
  auto_sync: boolean;
  schedule: string;
}

type SyncSettingsModalProps = {
  platform: string;
  onClose: () => void;
}

const scheduleOptions = [
  { value: "manual", label: "Manual only" },
  { value: "6h", label: "Every 6 hours" },
  { value: "12h", label: "Every 12 hours" },
  { value: "daily", label: "Once daily" },
];

export function SyncSettingsModal({ platform, onClose }: SyncSettingsModalProps) {
  const [config, setConfig] = useState<PlatformSyncConfig>({ auto_sync: true, schedule: "daily" });
  const [isLoading, setIsLoading] = useState(true);

  const fetchSettings = useCallback(async () => {
    try {
      const { data } = await client.GET("/api/v1/settings/sync", {});
      const all = data?.data as Record<string, PlatformSyncConfig> | undefined;
      if (all?.[platform]) {
        setConfig(all[platform]);
      }
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  }, [platform]);

  useEffect(() => { void fetchSettings(); }, [fetchSettings]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const save = async (updates: Partial<PlatformSyncConfig>) => {
    const newConfig = { ...config, ...updates };
    setConfig(newConfig);
    try {
      await client.PUT("/api/v1/settings/sync", {
        body: { [platform]: newConfig },
      });
    } catch (err) {
      console.error("save sync settings failed", err);
      setConfig(config); // revert
    }
  };

  const platformLabel = platform.charAt(0).toUpperCase() + platform.slice(1);

  if (isLoading) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" role="dialog" aria-modal="true">
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100 dark:border-stone-800">
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">
            {platformLabel} Sync Settings
          </h3>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* Auto-sync toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-stone-700 dark:text-stone-300">Auto-sync</p>
              <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
                Automatically sync on schedule
              </p>
            </div>
            <Toggle
              checked={config.auto_sync}
              onChange={(v) => void save({ auto_sync: v })}
            />
          </div>

          {/* Schedule selector */}
          {config.auto_sync && (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm text-stone-700 dark:text-stone-300">Schedule</p>
                <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
                  How often to sync automatically
                </p>
              </div>
              <select
                value={config.schedule}
                onChange={(e) => void save({ schedule: e.target.value })}
                className="w-full sm:w-auto text-sm border border-stone-200 dark:border-stone-700 rounded-lg px-3 py-1.5 text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-900 focus:outline-none focus:ring-2 focus:ring-teal-400"
              >
                {scheduleOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Telegram-specific: 2nd Tier contacts */}
          {platform === "telegram" && <TelegramSyncOptions />}
        </div>
      </div>
    </div>
  );
}

/* ── Telegram-specific sync options (2nd Tier toggle + purge) ── */

function TelegramSyncOptions() {
  const [sync2ndTier, setSync2ndTier] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [tierCount, setTierCount] = useState<number | null>(null);
  const [showPurgeConfirm, setShowPurgeConfirm] = useState(false);
  const [isPurging, setIsPurging] = useState(false);
  const [purgeResult, setPurgeResult] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const { data } = await client.GET("/api/v1/settings/telegram", {});
        setSync2ndTier(data?.data?.sync_2nd_tier ?? true);
      } catch (err) {
        console.error("load telegram settings failed", err);
      }
      try {
        const { data } = await client.GET("/api/v1/contacts/2nd-tier/count", {});
        const count = (data?.data as { count?: number } | undefined)?.count;
        setTierCount(count ?? 0);
      } catch (err) {
        console.error("load 2nd-tier count failed", err);
      }
      setIsLoading(false);
    })();
  }, []);

  const handleToggle = async (checked: boolean) => {
    setSync2ndTier(checked);
    try {
      await client.PUT("/api/v1/settings/telegram", {
        body: { sync_2nd_tier: checked },
      });
    } catch {
      setSync2ndTier(!checked);
    }
  };

  const handlePurge = async () => {
    setIsPurging(true);
    try {
      const { data } = await client.DELETE("/api/v1/contacts/2nd-tier", {});
      const count = (data?.data as { deleted_count?: number } | undefined)?.deleted_count ?? 0;
      setPurgeResult(`Deleted ${count} contact${count !== 1 ? "s" : ""}.`);
      setTierCount(0);
    } catch {
      setPurgeResult("Failed to delete contacts.");
    } finally {
      setIsPurging(false);
      setShowPurgeConfirm(false);
    }
  };

  if (isLoading) return null;

  return (
    <>
      <div className="pt-4 border-t border-stone-100 dark:border-stone-800">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-stone-700 dark:text-stone-300">Import 2nd Tier contacts</p>
            <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
              Sync group participants you haven&apos;t directly messaged
            </p>
          </div>
          <Toggle checked={sync2ndTier} onChange={(checked) => { void handleToggle(checked); }} />
        </div>

        {tierCount !== null && tierCount > 0 && (
          <div className="mt-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-stone-400 dark:text-stone-500" />
              <p className="text-xs text-stone-600 dark:text-stone-400">
                {tierCount} 2nd Tier contact{tierCount !== 1 ? "s" : ""}
              </p>
            </div>
            <button
              onClick={() => setShowPurgeConfirm(true)}
              disabled={isPurging}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-md border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3 h-3" />
              Delete all
            </button>
          </div>
        )}

        {purgeResult && (
          <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-2">{purgeResult}</p>
        )}
      </div>

      {showPurgeConfirm && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40" role="dialog" aria-modal="true">
          <div className="bg-white dark:bg-stone-900 rounded-xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-50 dark:bg-red-950 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-stone-900 dark:text-stone-100">Delete 2nd Tier contacts</h3>
                <p className="text-sm text-stone-500 dark:text-stone-400">This action cannot be undone.</p>
              </div>
            </div>
            <p className="text-sm text-stone-600 dark:text-stone-300 mb-5">
              This will permanently delete <strong>{tierCount}</strong> 2nd Tier contact{tierCount !== 1 ? "s" : ""}.
            </p>
            <div className="flex gap-2">
              <button onClick={() => setShowPurgeConfirm(false)} className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800">Cancel</button>
              <button onClick={() => void handlePurge()} disabled={isPurging} className="flex-1 px-3 py-2 text-sm rounded-lg bg-red-600 text-white font-medium hover:bg-red-700 disabled:opacity-50">
                {isPurging ? "Deleting..." : `Delete ${tierCount} contacts`}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
