"use client";

import { useState } from "react";
import { RefreshCw, Check, History } from "lucide-react";
import { cn } from "@/lib/utils";
import { ConnectionBadge, KebabMenu, SyncButtonWrapper } from "../shared";
import { SyncHistoryModal } from "../sync-history-modal";
import type { ConnectedAccounts } from "../../_hooks/use-settings-controller";
import type { SyncPhase } from "../shared";

function MetaIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#1877F2" />
      <path
        d="M13 10.5h2.5l.5-2.5H13V6.5c0-.7.3-1 1-1h2V3h-2.5C11.5 3 10 4.5 10 6.5V8H8v2.5h2V21h3V10.5z"
        fill="#fff"
      />
    </svg>
  );
}

export type MetaCardProps = {
  connected: ConnectedAccounts;
  fetchConnectionStatus: () => Promise<void>;
}

export function MetaCard({ connected }: MetaCardProps) {
  const isConnected = connected.meta_connected;
  const [syncStatus, setSyncStatus] = useState<SyncPhase>("idle");
  const [showFacebookHistory, setShowFacebookHistory] = useState(false);
  const [showInstagramHistory, setShowInstagramHistory] = useState(false);

  function handleSync() {
    setSyncStatus("loading");
    window.postMessage({ type: "PINGCRM_META_SYNC", platform: "both" }, "*");
    setTimeout(() => {
      setSyncStatus("success");
      setTimeout(() => setSyncStatus("idle"), 2000);
    }, 3000);
  }

  return (
    <>
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 hover:shadow-sm transition-shadow">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            <div
              className={cn(
                "w-11 h-11 rounded-lg flex items-center justify-center shrink-0",
                isConnected ? "bg-blue-50 dark:bg-blue-950" : "bg-stone-100 dark:bg-stone-800"
              )}
            >
              <MetaIcon />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Meta</h3>
                <ConnectionBadge connected={isConnected} />
              </div>
              <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
                Sync Facebook Messenger &amp; Instagram DMs via browser extension
              </p>
              {isConnected && connected.meta_connected_name && (
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                  Connected · <strong>{connected.meta_connected_name}</strong> · Messenger + Instagram DMs enabled
                </p>
              )}
              {!isConnected && (
                <p className="text-xs text-stone-400 dark:text-stone-500 mt-1">
                  Install extension, visit facebook.com to connect automatically
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isConnected ? (
              <>
                <SyncButtonWrapper phase={syncStatus}>
                  <button
                    onClick={handleSync}
                    disabled={syncStatus === "loading"}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors disabled:opacity-50"
                  >
                    {syncStatus === "loading" ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : syncStatus === "success" ? (
                      <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5" />
                    )}
                    {syncStatus === "loading"
                      ? "Syncing..."
                      : syncStatus === "success"
                      ? "Done"
                      : "Sync now"}
                  </button>
                </SyncButtonWrapper>
                <KebabMenu
                  items={[
                    { icon: History, label: "Messenger sync history", onClick: () => setShowFacebookHistory(true) },
                    { icon: History, label: "Instagram sync history", onClick: () => setShowInstagramHistory(true) },
                  ]}
                />
              </>
            ) : null}
          </div>
        </div>
      </div>

      {showFacebookHistory && (
        <SyncHistoryModal platform="facebook" onClose={() => setShowFacebookHistory(false)} />
      )}
      {showInstagramHistory && (
        <SyncHistoryModal platform="instagram" onClose={() => setShowInstagramHistory(false)} />
      )}
    </>
  );
}
