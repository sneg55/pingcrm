"use client";

import { useState } from "react";
import { RefreshCw, Check, AlertCircle, Link2, Settings, Key, History, Unplug } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import { SyncHistoryModal } from "../sync-history-modal";
import { SyncSettingsModal } from "../sync-settings-modal";
import {
  ConnectionBadge,
  SyncButtonWrapper,
  SyncResultPanel,
  KebabMenu,
  TwitterIcon,
} from "../shared";
import type { ConnectedAccounts, SyncState } from "../../_hooks/use-settings-controller";

export interface TwitterCardProps {
  connected: ConnectedAccounts;
  twitterConnect: SyncState;
  twitterSync: SyncState;
  handleTwitterConnect: () => Promise<void>;
  handleTwitterSync: () => Promise<void>;
}

export function TwitterCard({
  connected,
  twitterConnect,
  twitterSync,
  handleTwitterConnect,
  handleTwitterSync,
}: TwitterCardProps) {
  const [showSyncHistory, setShowSyncHistory] = useState(false);
  const [showSyncSettings, setShowSyncSettings] = useState(false);

  return (
    <>
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div className="w-11 h-11 rounded-lg bg-stone-100 dark:bg-stone-800 flex items-center justify-center shrink-0">
            <TwitterIcon />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Twitter / X — DMs</h3>
              <ConnectionBadge connected={connected.twitter} />
            </div>
            <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
              Sync direct messages via the X API (OAuth).
            </p>
            {connected.twitter && connected.twitter_username && (
              <p className="text-xs text-teal-600 dark:text-teal-400 mt-1">
                Connected as <strong>@{connected.twitter_username}</strong>
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {connected.twitter ? (
            <>
              <SyncButtonWrapper phase={twitterSync.status}>
                <button
                  onClick={() => void handleTwitterSync()}
                  disabled={twitterSync.status === "loading"}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors disabled:opacity-50"
                >
                  {twitterSync.status === "loading" ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : twitterSync.status === "success" ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <RefreshCw className="w-3.5 h-3.5" />
                  )}
                  {twitterSync.status === "loading"
                    ? "Syncing..."
                    : twitterSync.status === "success"
                    ? "Done"
                    : "Sync now"}
                </button>
              </SyncButtonWrapper>
              <KebabMenu
                items={[
                  { icon: Settings, label: "Sync settings", onClick: () => setShowSyncSettings(true) },
                  {
                    icon: Key,
                    label: "Re-authorize",
                    onClick: () => void handleTwitterConnect(),
                  },
                  { icon: History, label: "Sync history", onClick: () => setShowSyncHistory(true) },
                  { icon: Unplug, label: "---" },
                  { icon: Unplug, label: "Disconnect Twitter", danger: true, onClick: async () => {
                    if (confirm("Disconnect Twitter? Your synced messages will be kept but no new data will sync.")) {
                      await client.DELETE("/api/v1/auth/twitter/disconnect" as any, {});
                      window.location.reload();
                    }
                  }},
                ]}
              />
            </>
          ) : (
            <button
              onClick={() => void handleTwitterConnect()}
              disabled={twitterConnect.status === "loading"}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
            >
              {twitterConnect.status === "loading" ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Link2 className="w-3.5 h-3.5" />
              )}
              Connect
            </button>
          )}
        </div>
      </div>
      {twitterConnect.message && (
        <p
          className={cn(
            "text-xs mt-3 flex items-center gap-1",
            twitterConnect.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
          )}
        >
          {twitterConnect.status === "error" ? (
            <AlertCircle className="w-3 h-3" />
          ) : (
            <Check className="w-3 h-3" />
          )}
          {twitterConnect.message}
        </p>
      )}
      {twitterSync.message && (
        <p
          className={cn(
            "text-xs mt-3 flex items-center gap-1",
            twitterSync.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
          )}
        >
          {twitterSync.status === "error" ? (
            <AlertCircle className="w-3 h-3" />
          ) : (
            <Check className="w-3 h-3" />
          )}
          {twitterSync.message}
        </p>
      )}
      {twitterSync.details && (
        <SyncResultPanel details={twitterSync.details} status={twitterSync.status} />
      )}
    </div>
    {showSyncHistory && <SyncHistoryModal platform="twitter" onClose={() => setShowSyncHistory(false)} />}
    {showSyncSettings && <SyncSettingsModal platform="twitter" onClose={() => setShowSyncSettings(false)} />}
    </>
  );
}
