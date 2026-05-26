"use client";

import { useState } from "react";
import { Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { SyncHistoryModal } from "../sync-history-modal";
import { SyncSettingsModal } from "../sync-settings-modal";
import {
  SyncResultPanel,
  TelegramSyncProgressCard,
} from "../shared";
import type { ConnectedAccounts, SyncState } from "../../_hooks/use-settings-controller";
import type { UseTelegramConnectFlowReturn } from "../../_hooks/use-telegram-connect-flow";
import type { SyncProgress } from "@/hooks/use-telegram-sync";
import { TelegramCardHeader } from "./telegram-card-header";
import { TelegramConnectModal, TelegramConnectStatusMessage } from "./telegram-card-connect-modal";

export type TelegramCardProps = {
  connected: ConnectedAccounts;
  telegramConnect: SyncState;
  telegramSync: SyncState;
  telegramSyncProgress: SyncProgress | undefined;
  showTelegramModal: boolean;
  telegramFlow: UseTelegramConnectFlowReturn;
  handleTelegramSync: () => Promise<void>;
}

export function TelegramCard({
  connected,
  telegramConnect,
  telegramSync,
  telegramSyncProgress,
  showTelegramModal,
  telegramFlow,
  handleTelegramSync,
}: TelegramCardProps) {
  const { handleTelegramConnect } = telegramFlow;
  const [showSyncHistory, setShowSyncHistory] = useState(false);
  const [showSyncSettings, setShowSyncSettings] = useState(false);

  return (
    <>
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 hover:shadow-sm transition-shadow">
        <TelegramCardHeader
          connected={connected}
          telegramSync={telegramSync}
          handleTelegramSync={handleTelegramSync}
          handleTelegramConnect={handleTelegramConnect}
          setShowSyncSettings={setShowSyncSettings}
          setShowSyncHistory={setShowSyncHistory}
        />
        <TelegramConnectStatusMessage
          telegramConnect={telegramConnect}
          showTelegramModal={showTelegramModal}
        />
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

      {showTelegramModal && (
        <TelegramConnectModal
          telegramConnect={telegramConnect}
          telegramFlow={telegramFlow}
        />
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
