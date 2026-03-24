"use client";

import { useState, useEffect, useCallback } from "react";
import { X } from "lucide-react";
import { Toggle } from "./shared";
import { client } from "@/lib/api-client";

interface PlatformSyncConfig {
  auto_sync: boolean;
  schedule: string;
}

interface SyncSettingsModalProps {
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
  const [isSaving, setIsSaving] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const { data } = await client.GET("/api/v1/settings/sync" as any, {});
      const all = (data as any)?.data;
      if (all?.[platform]) {
        setConfig(all[platform]);
      }
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  }, [platform]);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const save = async (updates: Partial<PlatformSyncConfig>) => {
    const newConfig = { ...config, ...updates };
    setConfig(newConfig);
    setIsSaving(true);
    try {
      await client.PUT("/api/v1/settings/sync" as any, {
        body: { [platform]: newConfig },
      });
    } catch {
      setConfig(config); // revert
    } finally {
      setIsSaving(false);
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
        </div>
      </div>
    </div>
  );
}
