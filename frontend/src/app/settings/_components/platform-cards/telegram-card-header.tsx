"use client";

import { RefreshCw, Check, Settings, RotateCcw, History, Unplug, Link2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import {
  ConnectionBadge,
  SyncButtonWrapper,
  KebabMenu,
  TelegramIcon,
} from "../shared";
import type { ConnectedAccounts, SyncState } from "../../_hooks/use-settings-controller";

type TelegramCardHeaderProps = {
  connected: ConnectedAccounts;
  telegramSync: SyncState;
  handleTelegramSync: () => Promise<void>;
  handleTelegramConnect: () => void;
  setShowSyncSettings: (v: boolean) => void;
  setShowSyncHistory: (v: boolean) => void;
};

function TelegramSyncButton({
  telegramSync,
  handleTelegramSync,
}: {
  telegramSync: SyncState;
  handleTelegramSync: () => Promise<void>;
}) {
  return (
    <SyncButtonWrapper phase={telegramSync.status}>
      <button
        onClick={() => void handleTelegramSync()}
        disabled={telegramSync.status === "loading"}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors disabled:opacity-50"
      >
        {telegramSync.status === "loading" ? (
          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
        ) : telegramSync.status === "success" ? (
          <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
        ) : (
          <RefreshCw className="w-3.5 h-3.5" />
        )}
        {telegramSync.status === "loading"
          ? "Syncing..."
          : telegramSync.status === "success"
          ? "Done"
          : "Sync now"}
      </button>
    </SyncButtonWrapper>
  );
}

export function TelegramCardHeader({
  connected,
  telegramSync,
  handleTelegramSync,
  handleTelegramConnect,
  setShowSyncSettings,
  setShowSyncHistory,
}: TelegramCardHeaderProps) {
  return (
    <div className="flex items-start justify-between">
      <div className="flex items-start gap-4">
        <div
          className={cn(
            "w-11 h-11 rounded-lg flex items-center justify-center shrink-0",
            connected.telegram ? "bg-sky-50 dark:bg-sky-950" : "bg-stone-100 dark:bg-stone-800"
          )}
        >
          <TelegramIcon />
        </div>
        <div>
          <div className="flex items-center gap-2.5">
            <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Telegram</h3>
            <ConnectionBadge connected={connected.telegram} />
          </div>
          <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
            Chat history and contact sync via MTProto session.
          </p>
          {connected.telegram && connected.telegram_username && (
            <p className="text-xs text-teal-600 dark:text-teal-400 mt-1">
              Connected as <strong>@{connected.telegram_username}</strong>
            </p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {connected.telegram ? (
          <>
            <TelegramSyncButton
              telegramSync={telegramSync}
              handleTelegramSync={handleTelegramSync}
            />
            <KebabMenu
              items={[
                { icon: Settings, label: "Sync settings", onClick: () => setShowSyncSettings(true) },
                { icon: RotateCcw, label: "Reset session", onClick: () => { void (async () => {
                  // eslint-disable-next-line no-alert -- native confirm before destructive session reset
                  if (confirm("Reset your Telegram session? You'll need to re-enter your phone number and code.")) {
                    await client.POST("/api/v1/auth/telegram/reset-session", {});
                    window.location.reload();
                  }
                })(); }},
                { icon: History, label: "Sync history", onClick: () => setShowSyncHistory(true) },
                { icon: Unplug, label: "---" },
                { icon: Unplug, label: "Disconnect Telegram", danger: true, onClick: () => { void (async () => {
                  // eslint-disable-next-line no-alert -- native confirm before destructive disconnect
                  if (confirm("Disconnect Telegram? Your synced messages will be kept but no new data will sync.")) {
                    await client.DELETE("/api/v1/auth/telegram/disconnect", {});
                    window.location.reload();
                  }
                })(); }},
              ]}
            />
          </>
        ) : (
          <button
            onClick={handleTelegramConnect}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm"
          >
            <Link2 className="w-3.5 h-3.5" />
            Connect
          </button>
        )}
      </div>
    </div>
  );
}
