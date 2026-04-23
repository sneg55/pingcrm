"use client";

import { useState } from "react";
import { RefreshCw, Check, AlertCircle, X, Link2, Settings, Key, History, Unplug } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import { SyncHistoryModal } from "../sync-history-modal";
import { SyncSettingsModal } from "../sync-settings-modal";
import {
  ConnectionBadge,
  SyncButtonWrapper,
  SyncResultPanel,
  KebabMenu,
  GmailIcon,
} from "../shared";
import type { ConnectedAccounts, SyncState } from "../../_hooks/use-settings-controller";

export type GoogleCardProps = {
  connected: ConnectedAccounts;
  googleConnect: SyncState;
  googleSync: SyncState;
  fetchConnectionStatus: () => Promise<void>;
  handleGoogleConnect: () => Promise<void>;
  handleGoogleSyncAll: () => Promise<void>;
}

// eslint-disable-next-line sonarjs/cognitive-complexity -- card composes connect/sync/error/progress state branches; refactor tracked separately
export function GoogleCard({
  connected,
  googleConnect,
  googleSync,
  fetchConnectionStatus,
  handleGoogleConnect,
  handleGoogleSyncAll,
}: GoogleCardProps) {
  const [showSyncHistory, setShowSyncHistory] = useState(false);
  const [showSyncSettings, setShowSyncSettings] = useState(false);

  return (
    <>
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div
            className={cn(
              "w-11 h-11 rounded-lg flex items-center justify-center shrink-0",
              connected.google ? "bg-red-50 dark:bg-red-950" : "bg-stone-100 dark:bg-stone-800"
            )}
          >
            <GmailIcon />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Gmail</h3>
              <ConnectionBadge connected={connected.google} />
            </div>
            <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
              Sync email threads, contacts, and calendar from Google.
            </p>
            {connected.google && (
              <>
                {connected.google_accounts.length > 0 ? (
                  <div className="mt-1 space-y-0.5">
                    {connected.google_accounts.map((ga) => (
                      <div key={ga.id} className="flex items-center gap-2 text-xs">
                        <span className="text-teal-600 dark:text-teal-400 font-medium flex items-center gap-1">
                          <Check className="w-3 h-3" />
                          {ga.email}
                        </span>
                        <button
                          onClick={() => { void (async () => {
                            await client.DELETE(
                              "/api/v1/auth/google/accounts/{account_id}",
                              { params: { path: { account_id: ga.id } } }
                            );
                            await fetchConnectionStatus();
                          })(); }}
                          className="text-stone-400 dark:text-stone-500 hover:text-red-500 transition-colors"
                          title="Remove account"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : connected.google_email ? (
                  <p className="text-xs text-teal-600 dark:text-teal-400 mt-1">
                    Connected as <strong>{connected.google_email}</strong>
                  </p>
                ) : null}
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {connected.google ? (
            <>
              <SyncButtonWrapper phase={googleSync.status}>
                <button
                  onClick={() => void handleGoogleSyncAll()}
                  disabled={googleSync.status === "loading"}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors disabled:opacity-50"
                >
                  {googleSync.status === "loading" ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : googleSync.status === "success" ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <RefreshCw className="w-3.5 h-3.5" />
                  )}
                  {googleSync.status === "loading"
                    ? "Syncing..."
                    : googleSync.status === "success"
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
                    onClick: () => void handleGoogleConnect(),
                  },
                  { icon: History, label: "Sync history", onClick: () => setShowSyncHistory(true) },
                  { icon: Unplug, label: "---" },
                  { icon: Unplug, label: "Disconnect Gmail", danger: true, onClick: () => { void (async () => {
                    const ga = connected.google_accounts?.[0];
                    // eslint-disable-next-line no-alert -- native confirm before destructive disconnect
                    if (ga && confirm("Disconnect Gmail? Your synced emails will be kept.")) {
                      await client.DELETE("/api/v1/auth/google/accounts/{account_id}", {
                        params: { path: { account_id: ga.id } },
                      });
                      void fetchConnectionStatus();
                    }
                  })(); }},
                ]}
              />
            </>
          ) : (
            <button
              onClick={() => void handleGoogleConnect()}
              disabled={googleConnect.status === "loading"}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
            >
              {googleConnect.status === "loading" ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Link2 className="w-3.5 h-3.5" />
              )}
              Connect
            </button>
          )}
        </div>
      </div>
      {googleConnect.message && (
        <p
          className={cn(
            "text-xs mt-3 flex items-center gap-1",
            googleConnect.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
          )}
        >
          {googleConnect.status === "error" ? (
            <AlertCircle className="w-3 h-3" />
          ) : (
            <Check className="w-3 h-3" />
          )}
          {googleConnect.message}
        </p>
      )}
      {googleSync.message && !googleSync.details && (
        <p
          className={cn(
            "text-xs mt-3 flex items-center gap-1",
            googleSync.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
          )}
        >
          {googleSync.status === "error" ? (
            <AlertCircle className="w-3 h-3" />
          ) : (
            <Check className="w-3 h-3" />
          )}
          {googleSync.message}
        </p>
      )}
      {googleSync.details && (
        <SyncResultPanel details={googleSync.details} status={googleSync.status} />
      )}
    </div>
    {showSyncHistory && <SyncHistoryModal platform="gmail" onClose={() => setShowSyncHistory(false)} />}
    {showSyncSettings && <SyncSettingsModal platform="gmail" onClose={() => setShowSyncSettings(false)} />}
    </>
  );
}
