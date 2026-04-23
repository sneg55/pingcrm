"use client";

import { useState, useEffect, useCallback } from "react";
import { Toggle } from "./shared";
import { Trash2, AlertTriangle, Users } from "lucide-react";
import { client } from "@/lib/api-client";

export function TelegramSyncSettings() {
  const [sync2ndTier, setSync2ndTier] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [tierCount, setTierCount] = useState<number | null>(null);
  const [showPurgeConfirm, setShowPurgeConfirm] = useState(false);
  const [isPurging, setIsPurging] = useState(false);
  const [purgeResult, setPurgeResult] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    try {
      const { data } = await client.GET("/api/v1/settings/telegram", {});
      setSync2ndTier(data?.data?.sync_2nd_tier ?? true);
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchCount = useCallback(async () => {
    try {
      const { data } = await client.GET("/api/v1/contacts/2nd-tier/count", {});
      const count = (data?.data as { count?: number } | undefined)?.count;
      setTierCount(count ?? 0);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void fetchSettings();
    void fetchCount();
  }, [fetchSettings, fetchCount]);

  // Escape key closes purge confirmation
  useEffect(() => {
    if (!showPurgeConfirm) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowPurgeConfirm(false);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [showPurgeConfirm]);

  const handleToggle = async (checked: boolean) => {
    setSync2ndTier(checked);
    try {
      await client.PUT("/api/v1/settings/telegram", {
        body: { sync_2nd_tier: checked },
      });
    } catch (err) {
      console.error("save telegram 2nd-tier setting failed", err);
      setSync2ndTier(!checked); // revert on error
    }
  };

  const handlePurge = async () => {
    setIsPurging(true);
    setPurgeResult(null);
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
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
      <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 mb-4">
        Telegram Sync Settings
      </h3>

      {/* 2nd Tier toggle */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-stone-700 dark:text-stone-300">
            Import 2nd Tier contacts
          </p>
          <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
            Sync group participants you haven&apos;t directly messaged
          </p>
        </div>
        <Toggle checked={sync2ndTier} onChange={(checked) => { void handleToggle(checked); }} />
      </div>

      {/* 2nd Tier count + purge */}
      {tierCount !== null && tierCount > 0 && (
        <div className="mt-4 pt-4 border-t border-stone-100 dark:border-stone-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-stone-400 dark:text-stone-500" />
              <p className="text-sm text-stone-600 dark:text-stone-400">
                {tierCount} 2nd Tier contact{tierCount !== 1 ? "s" : ""}
              </p>
            </div>
            <button
              onClick={() => setShowPurgeConfirm(true)}
              disabled={isPurging}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete all
            </button>
          </div>
        </div>
      )}

      {/* Purge result */}
      {purgeResult && (
        <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-3">{purgeResult}</p>
      )}

      {/* Purge confirmation dialog */}
      {showPurgeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" role="dialog" aria-modal="true">
          <div className="bg-white dark:bg-stone-900 rounded-xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-50 dark:bg-red-950 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-stone-900 dark:text-stone-100">
                  Delete 2nd Tier contacts
                </h3>
                <p className="text-sm text-stone-500 dark:text-stone-400">
                  This action cannot be undone.
                </p>
              </div>
            </div>
            <p className="text-sm text-stone-600 dark:text-stone-300 mb-5">
              This will permanently delete{" "}
              <strong>{tierCount}</strong> 2nd Tier contact{tierCount !== 1 ? "s" : ""} and
              all their associated data (interactions, suggestions, etc.).
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setShowPurgeConfirm(false)}
                className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
              >
                Cancel
              </button>
              <button
                onClick={() => void handlePurge()}
                disabled={isPurging}
                className="flex-1 px-3 py-2 text-sm rounded-lg bg-red-600 text-white font-medium hover:bg-red-700 disabled:opacity-50"
              >
                {isPurging ? "Deleting..." : `Delete ${tierCount} contacts`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
