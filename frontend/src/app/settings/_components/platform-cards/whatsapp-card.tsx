"use client";

import { useState } from "react";
import { RefreshCw, Check, Link2, Unplug, History } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import {
  ConnectionBadge,
  SyncButtonWrapper,
  KebabMenu,
  WhatsAppIcon,
} from "../shared";
import { SyncHistoryModal } from "../sync-history-modal";
import type { ConnectedAccounts, SyncState } from "../../_hooks/use-settings-controller";
import type { UseWhatsAppConnectFlowReturn } from "../../_hooks/use-whatsapp-connect-flow";

export type WhatsAppCardProps = {
  connected: ConnectedAccounts;
  whatsappConnect: SyncState;
  whatsappSync: SyncState;
  whatsappFlow: UseWhatsAppConnectFlowReturn;
  handleWhatsAppSync: () => Promise<void>;
  fetchConnectionStatus: () => Promise<void>;
}

export function WhatsAppCard({
  connected,
  whatsappConnect,
  whatsappSync,
  whatsappFlow,
  handleWhatsAppSync,
  fetchConnectionStatus,
}: WhatsAppCardProps) {
  const isConnected = connected.whatsapp;
  const { step, qrData, error, startConnect, cancel } = whatsappFlow;
  const [showSyncHistory, setShowSyncHistory] = useState(false);

  const handleDisconnect = async () => {
    // eslint-disable-next-line no-alert -- native confirm before destructive disconnect
    if (confirm("Disconnect WhatsApp? Your synced messages will be kept but no new data will sync.")) {
      await client.DELETE("/api/v1/auth/whatsapp/disconnect", {});
      await fetchConnectionStatus();
    }
  };

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div
            className={cn(
              "w-11 h-11 rounded-lg flex items-center justify-center shrink-0",
              isConnected ? "bg-green-50 dark:bg-green-950" : "bg-stone-100 dark:bg-stone-800"
            )}
          >
            <WhatsAppIcon />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">WhatsApp</h3>
              <ConnectionBadge connected={isConnected} />
            </div>
            <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
              Sync your WhatsApp messages
            </p>
            {isConnected && connected.whatsapp_phone && (
              <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                Connected · <strong>{connected.whatsapp_phone}</strong>
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isConnected ? (
            <>
              <SyncButtonWrapper phase={whatsappSync.status}>
                <button
                  onClick={() => void handleWhatsAppSync()}
                  disabled={whatsappSync.status === "loading"}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors disabled:opacity-50"
                >
                  {whatsappSync.status === "loading" ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : whatsappSync.status === "success" ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <RefreshCw className="w-3.5 h-3.5" />
                  )}
                  {whatsappSync.status === "loading"
                    ? "Syncing..."
                    : whatsappSync.status === "success"
                    ? "Done"
                    : "Sync now"}
                </button>
              </SyncButtonWrapper>
              <KebabMenu
                items={[
                  { icon: History, label: "Sync history", onClick: () => setShowSyncHistory(true) },
                  { icon: Unplug, label: "Disconnect WhatsApp", danger: true, onClick: () => { void handleDisconnect(); } },
                ]}
              />
            </>
          ) : (
            <button
              onClick={() => { void startConnect(); }}
              disabled={step === "qr_pending"}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
            >
              <Link2 className="w-3.5 h-3.5" />
              Connect
            </button>
          )}
        </div>
      </div>

      {step === "qr_pending" && qrData && (
        <div className="mt-4 flex flex-col items-center gap-3">
          <QRCodeSVG value={qrData} size={200} />
          <p className="text-xs text-stone-500 dark:text-stone-400">
            Open WhatsApp on your phone → Settings → Linked Devices → Link a Device
          </p>
          <button onClick={cancel} className="text-xs text-stone-400 hover:text-stone-600 dark:hover:text-stone-300">
            Cancel
          </button>
        </div>
      )}

      {step === "qr_pending" && !qrData && (
        <div className="mt-4 flex flex-col items-center gap-2">
          <div className="w-[200px] h-[200px] bg-stone-100 dark:bg-stone-800 rounded-lg animate-pulse" />
          <p className="text-xs text-stone-400">Generating QR code...</p>
        </div>
      )}

      {(error || whatsappConnect.status === "error") && (
        <p className="text-xs mt-3 text-red-500">
          {error || whatsappConnect.message}
        </p>
      )}

      {showSyncHistory && (
        <SyncHistoryModal platform="whatsapp" onClose={() => setShowSyncHistory(false)} />
      )}
    </div>
  );
}
