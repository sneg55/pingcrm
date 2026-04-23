"use client";

import { useState } from "react";
import { RefreshCw, Check, AlertCircle, X, Link2, Settings, RotateCcw, History, Unplug } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import { SyncHistoryModal } from "../sync-history-modal";
import { SyncSettingsModal } from "../sync-settings-modal";
import {
  ConnectionBadge,
  SyncButtonWrapper,
  SyncResultPanel,
  TelegramSyncProgressCard,
  KebabMenu,
  TelegramIcon,
} from "../shared";
import type { ConnectedAccounts, SyncState } from "../../_hooks/use-settings-controller";
import type { UseTelegramConnectFlowReturn } from "../../_hooks/use-telegram-connect-flow";
import type { SyncProgress } from "@/hooks/use-telegram-sync";

export type TelegramCardProps = {
  connected: ConnectedAccounts;
  telegramConnect: SyncState;
  telegramSync: SyncState;
  telegramSyncProgress: SyncProgress | undefined;
  showTelegramModal: boolean;
  telegramFlow: UseTelegramConnectFlowReturn;
  handleTelegramSync: () => Promise<void>;
}

// eslint-disable-next-line sonarjs/cognitive-complexity -- card composes pairing/connect/sync/progress/error states; refactor tracked separately
export function TelegramCard({
  connected,
  telegramConnect,
  telegramSync,
  telegramSyncProgress,
  showTelegramModal,
  telegramFlow,
  handleTelegramSync,
}: TelegramCardProps) {
  const {
    telegramStep,
    telegramPhone,
    setTelegramPhone,
    telegramCode,
    setTelegramCode,
    telegramPassword,
    setTelegramPassword,
    handleTelegramConnect,
    closeTelegramModal,
    handleTelegramSendCode,
    handleTelegramVerify,
    handleTelegram2FA,
  } = telegramFlow;
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
        {telegramConnect.message && !showTelegramModal && (
          <p
            className={cn(
              "text-xs mt-3 flex items-center gap-1",
              telegramConnect.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
            )}
          >
            {telegramConnect.status === "error" ? (
              <AlertCircle className="w-3 h-3" />
            ) : (
              <Check className="w-3 h-3" />
            )}
            {telegramConnect.message}
          </p>
        )}
        {telegramSync.message && (
          <p
            className={cn(
              "text-xs mt-3 flex items-center gap-1",
              telegramSync.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
            )}
          >
            {telegramSync.status === "error" ? (
              <AlertCircle className="w-3 h-3" />
            ) : (
              <Check className="w-3 h-3" />
            )}
            {telegramSync.message}
          </p>
        )}
        {telegramSync.details && (
          <SyncResultPanel details={telegramSync.details} status={telegramSync.status} />
        )}
        {telegramSyncProgress?.active && (
          <TelegramSyncProgressCard progress={telegramSyncProgress} />
        )}
      </div>

      {/* Telegram phone/code/password modal */}
      {showTelegramModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white dark:bg-stone-900 rounded-xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">Connect Telegram</h3>
              <button
                onClick={closeTelegramModal}
                aria-label="Close"
                className="text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {telegramStep === "phone" && (
              <>
                <label
                  htmlFor="telegram-phone"
                  className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-1"
                >
                  Phone number
                </label>
                <input
                  id="telegram-phone"
                  type="tel"
                  value={telegramPhone}
                  onChange={(e) => setTelegramPhone(e.target.value)}
                  placeholder="+1234567890"
                  className="w-full px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-teal-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={closeTelegramModal}
                    className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => void handleTelegramSendCode()}
                    disabled={!telegramPhone.trim() || telegramConnect.status === "loading"}
                    className="flex-1 px-3 py-2 text-sm rounded-lg bg-teal-600 text-white font-medium hover:bg-teal-700 disabled:opacity-50"
                  >
                    {telegramConnect.status === "loading" ? "Sending..." : "Send code"}
                  </button>
                </div>
              </>
            )}

            {telegramStep === "code" && (
              <>
                <label
                  htmlFor="telegram-code"
                  className="block text-sm text-stone-500 dark:text-stone-400 mb-3"
                >
                  Enter the code sent to your Telegram app.
                </label>
                <input
                  id="telegram-code"
                  type="text"
                  value={telegramCode}
                  onChange={(e) => setTelegramCode(e.target.value)}
                  placeholder="12345"
                  className="w-full px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-teal-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={closeTelegramModal}
                    className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => void handleTelegramVerify()}
                    disabled={!telegramCode.trim() || telegramConnect.status === "loading"}
                    className="flex-1 px-3 py-2 text-sm rounded-lg bg-teal-600 text-white font-medium hover:bg-teal-700 disabled:opacity-50"
                  >
                    {telegramConnect.status === "loading" ? "Verifying..." : "Verify"}
                  </button>
                </div>
              </>
            )}

            {telegramStep === "password" && (
              <>
                <label
                  htmlFor="telegram-password"
                  className="block text-sm text-stone-500 dark:text-stone-400 mb-3"
                >
                  Your account has two-step verification. Enter your Telegram password.
                </label>
                <input
                  id="telegram-password"
                  type="password"
                  value={telegramPassword}
                  onChange={(e) => setTelegramPassword(e.target.value)}
                  placeholder="Telegram password"
                  className="w-full px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-teal-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={closeTelegramModal}
                    className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => void handleTelegram2FA()}
                    disabled={
                      !telegramPassword.trim() || telegramConnect.status === "loading"
                    }
                    className="flex-1 px-3 py-2 text-sm rounded-lg bg-teal-600 text-white font-medium hover:bg-teal-700 disabled:opacity-50"
                  >
                    {telegramConnect.status === "loading" ? "Verifying..." : "Submit"}
                  </button>
                </div>
              </>
            )}

            {telegramConnect.message && (
              <p
                className={cn(
                  "text-xs mt-3",
                  telegramConnect.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
                )}
              >
                {telegramConnect.message}
              </p>
            )}
          </div>
        </div>
      )}

      {showSyncHistory && (
        <SyncHistoryModal platform="telegram" onClose={() => setShowSyncHistory(false)} />
      )}
      {showSyncSettings && (
        <SyncSettingsModal platform="telegram" onClose={() => setShowSyncSettings(false)} />
      )}
    </>
  );
}
