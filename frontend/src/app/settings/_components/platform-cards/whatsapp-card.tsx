"use client";

import { RefreshCw, Unplug } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import {
  ConnectionBadge,
  SyncButtonWrapper,
  KebabMenu,
  WhatsAppIcon,
} from "../shared";
import type { ConnectedAccounts, SyncState } from "../../_hooks/use-settings-controller";
import type { UseWhatsAppConnectFlowReturn } from "../../_hooks/use-whatsapp-connect-flow";

export interface WhatsAppCardProps {
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

  const handleDisconnect = async () => {
    await client.DELETE("/api/v1/auth/whatsapp/disconnect" as any, {});
    await fetchConnectionStatus();
  };

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-800 p-5">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center",
            isConnected ? "bg-green-50 dark:bg-green-900/30" : "bg-stone-100 dark:bg-stone-800"
          )}>
            <WhatsAppIcon />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-stone-900 dark:text-stone-100">WhatsApp</h3>
              <ConnectionBadge connected={isConnected} />
            </div>
            <p className="text-sm text-stone-500 dark:text-stone-400 mt-0.5">
              {isConnected
                ? `Connected${connected.whatsapp_phone ? ` · ${connected.whatsapp_phone}` : ""}`
                : "Sync your WhatsApp messages"}
            </p>
          </div>
        </div>
        {isConnected && (
          <KebabMenu items={[{
            label: "Disconnect WhatsApp",
            icon: Unplug,
            onClick: handleDisconnect,
            danger: true,
          }]} />
        )}
      </div>

      {step === "qr_pending" && qrData && (
        <div className="mt-4 flex flex-col items-center gap-3">
          <QRCodeSVG value={qrData} size={200} />
          <p className="text-sm text-stone-500 dark:text-stone-400">
            Open WhatsApp on your phone → Settings → Linked Devices → Link a Device
          </p>
          <button onClick={cancel} className="text-sm text-stone-400 hover:text-stone-600 dark:hover:text-stone-300">
            Cancel
          </button>
        </div>
      )}

      {step === "qr_pending" && !qrData && (
        <div className="mt-4 flex flex-col items-center gap-2">
          <div className="w-[200px] h-[200px] bg-stone-100 dark:bg-stone-800 rounded-lg animate-pulse" />
          <p className="text-sm text-stone-400">Generating QR code...</p>
        </div>
      )}

      {error && <p className="mt-3 text-sm text-red-500">{error}</p>}

      <div className="mt-4 flex gap-2">
        {!isConnected && step === "idle" && (
          <SyncButtonWrapper phase={whatsappConnect.status}>
            <button onClick={startConnect} className="px-4 py-2 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700">
              Connect WhatsApp
            </button>
          </SyncButtonWrapper>
        )}
        {isConnected && (
          <SyncButtonWrapper phase={whatsappSync.status}>
            <button onClick={handleWhatsAppSync} className="px-4 py-2 text-sm font-medium rounded-lg border border-stone-200 dark:border-stone-700 hover:bg-stone-50 dark:hover:bg-stone-800 flex items-center gap-2">
              <RefreshCw className="w-4 h-4" />
              Sync Messages
            </button>
          </SyncButtonWrapper>
        )}
      </div>
    </div>
  );
}
