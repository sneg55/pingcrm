"use client";

import { GoogleCard } from "./platform-cards/google-card";
import { TelegramCard } from "./platform-cards/telegram-card";
import { TwitterCard } from "./platform-cards/twitter-card";
import { LinkedInCard } from "./platform-cards/linkedin-card";
import { WhatsAppCard } from "./platform-cards/whatsapp-card";
import type {
  ConnectedAccounts,
  SyncState,
} from "../_hooks/use-settings-controller";
import type { UseTelegramConnectFlowReturn } from "../_hooks/use-telegram-connect-flow";
import type { UseWhatsAppConnectFlowReturn } from "../_hooks/use-whatsapp-connect-flow";
import type { SyncProgress } from "@/hooks/use-telegram-sync";

export interface IntegrationsTabProps {
  connected: ConnectedAccounts;
  googleConnect: SyncState;
  googleSync: SyncState;
  telegramConnect: SyncState;
  telegramSync: SyncState;
  telegramSyncProgress: SyncProgress | undefined;
  twitterConnect: SyncState;
  twitterSync: SyncState;
  showTelegramModal: boolean;
  telegramFlow: UseTelegramConnectFlowReturn;
  whatsappConnect: SyncState;
  whatsappSync: SyncState;
  whatsappFlow: UseWhatsAppConnectFlowReturn;
  handleWhatsAppSync: () => Promise<void>;
  fetchConnectionStatus: () => Promise<void>;
  handleGoogleConnect: () => Promise<void>;
  handleGoogleSyncAll: () => Promise<void>;
  handleTelegramSync: () => Promise<void>;
  handleTwitterConnect: () => Promise<void>;
  handleTwitterSync: () => Promise<void>;
}

export function IntegrationsTab({
  connected,
  googleConnect,
  googleSync,
  telegramConnect,
  telegramSync,
  telegramSyncProgress,
  twitterConnect,
  twitterSync,
  showTelegramModal,
  telegramFlow,
  whatsappConnect,
  whatsappSync,
  whatsappFlow,
  handleWhatsAppSync,
  fetchConnectionStatus,
  handleGoogleConnect,
  handleGoogleSyncAll,
  handleTelegramSync,
  handleTwitterConnect,
  handleTwitterSync,
}: IntegrationsTabProps) {
  return (
    <div className="space-y-4">
      <GoogleCard
        connected={connected}
        googleConnect={googleConnect}
        googleSync={googleSync}
        fetchConnectionStatus={fetchConnectionStatus}
        handleGoogleConnect={handleGoogleConnect}
        handleGoogleSyncAll={handleGoogleSyncAll}
      />

      <TelegramCard
        connected={connected}
        telegramConnect={telegramConnect}
        telegramSync={telegramSync}
        telegramSyncProgress={telegramSyncProgress}
        showTelegramModal={showTelegramModal}
        telegramFlow={telegramFlow}
        handleTelegramSync={handleTelegramSync}
      />

      <TwitterCard
        connected={connected}
        twitterConnect={twitterConnect}
        twitterSync={twitterSync}
        handleTwitterConnect={handleTwitterConnect}
        handleTwitterSync={handleTwitterSync}
      />

      <LinkedInCard
        connected={connected}
        fetchConnectionStatus={fetchConnectionStatus}
      />

      <WhatsAppCard
        connected={connected}
        whatsappConnect={whatsappConnect}
        whatsappSync={whatsappSync}
        whatsappFlow={whatsappFlow}
        handleWhatsAppSync={handleWhatsAppSync}
        fetchConnectionStatus={fetchConnectionStatus}
      />
    </div>
  );
}
