"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { client } from "@/lib/api-client";
import { useTelegramSyncProgress } from "@/hooks/use-telegram-sync";

/* ═══════════════════════════════════════════════════════════ */
/*  Types                                                       */
/* ═══════════════════════════════════════════════════════════ */

export type SyncStatus = "idle" | "loading" | "success" | "error";

export interface SyncState {
  status: SyncStatus;
  message: string;
  details?: SyncDetails;
}

export interface SyncDetails {
  created?: number;
  updated?: number;
  new_interactions?: number;
  errors?: string[];
  elapsed?: number;
  message?: string;
}

export interface GoogleAccountInfo {
  id: string;
  email: string;
}

export interface ConnectedAccounts {
  google: boolean;
  google_email?: string | null;
  google_accounts: GoogleAccountInfo[];
  telegram: boolean;
  telegram_username?: string | null;
  twitter: boolean;
  twitter_username?: string | null;
  linkedin_extension_paired_at?: string | null;
  whatsapp: boolean;
  whatsapp_phone?: string | null;
}

const TABS = [
  { id: "integrations" },
  { id: "import" },
  { id: "followup" },
  { id: "tags" },
  { id: "account" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

const defaultSyncState: SyncState = { status: "idle", message: "" };

export interface UseSettingsControllerReturn {
  // Tab state
  activeTab: TabId;
  setTab: (tab: TabId) => void;

  // Connection state
  isLoading: boolean;
  connected: ConnectedAccounts;

  // Sync states
  googleConnect: SyncState;
  setGoogleConnect: (s: SyncState) => void;
  googleSync: SyncState;
  setGoogleSync: (s: SyncState) => void;
  telegramConnect: SyncState;
  setTelegramConnect: (s: SyncState) => void;
  telegramSync: SyncState;
  setTelegramSync: (s: SyncState) => void;
  telegramSyncProgress: ReturnType<typeof useTelegramSyncProgress>["data"];
  twitterConnect: SyncState;
  setTwitterConnect: (s: SyncState) => void;
  twitterSync: SyncState;
  setTwitterSync: (s: SyncState) => void;
  whatsappConnect: SyncState;
  setWhatsappConnect: (s: SyncState) => void;
  whatsappSync: SyncState;
  setWhatsappSync: (s: SyncState) => void;
  handleWhatsAppSync: () => Promise<void>;

  // Success modal
  successPlatform: string | null;
  setSuccessPlatform: (p: string | null) => void;

  // Telegram modal
  showTelegramModal: boolean;
  setShowTelegramModal: (v: boolean) => void;

  // Sync schedule (UI-only)
  bgSync: boolean;
  setBgSync: (v: boolean) => void;
  syncFreq: string;
  setSyncFreq: (v: string) => void;

  // Actions
  fetchConnectionStatus: () => Promise<void>;
  showSuccessModal: (platform: string, username?: string | null) => Promise<void>;
  pollForNotification: (platform: string, setter: (s: SyncState) => void) => void;
  handleGoogleConnect: () => Promise<void>;
  handleGoogleSyncAll: () => Promise<void>;
  handleTelegramSync: () => Promise<void>;
  handleTwitterConnect: () => Promise<void>;
  handleTwitterSync: () => Promise<void>;
}

export function useSettingsController(): UseSettingsControllerReturn {
  const searchParams = useSearchParams();
  const router = useRouter();

  const tabParam = (searchParams.get("tab") || "integrations") as TabId;
  const activeTab = TABS.some((t) => t.id === tabParam) ? tabParam : "integrations";

  const setTab = (tab: TabId) => {
    router.replace(`/settings?tab=${tab}`, { scroll: false });
  };

  // Connection state
  const [isLoading, setIsLoading] = useState(true);
  const [connected, setConnected] = useState<ConnectedAccounts>({
    google: false,
    telegram: false,
    twitter: false,
    google_email: null,
    google_accounts: [],
    telegram_username: null,
    twitter_username: null,
    linkedin_extension_paired_at: null,
    whatsapp: false,
    whatsapp_phone: null,
  });

  // Sync states
  const [googleConnect, setGoogleConnect] = useState<SyncState>(defaultSyncState);
  const [googleSync, setGoogleSync] = useState<SyncState>(defaultSyncState);
  const [telegramConnect, setTelegramConnect] = useState<SyncState>(defaultSyncState);
  const [telegramSync, setTelegramSync] = useState<SyncState>(defaultSyncState);
  const { data: telegramSyncProgress } = useTelegramSyncProgress();
  const [twitterConnect, setTwitterConnect] = useState<SyncState>(defaultSyncState);
  const [twitterSync, setTwitterSync] = useState<SyncState>(defaultSyncState);
  const [whatsappConnect, setWhatsappConnect] = useState<SyncState>(defaultSyncState);
  const [whatsappSync, setWhatsappSync] = useState<SyncState>(defaultSyncState);

  // Success modal
  const [successPlatform, setSuccessPlatform] = useState<string | null>(null);

  // Telegram modal
  const [showTelegramModal, setShowTelegramModal] = useState(false);

  // Sync schedule (UI-only)
  const [bgSync, setBgSync] = useState(true);
  const [syncFreq, setSyncFreq] = useState("6h");

  // Detect OAuth redirect
  useEffect(() => {
    const platform = searchParams.get("connected");
    if (platform) {
      const label = platform.charAt(0).toUpperCase() + platform.slice(1);
      setSuccessPlatform(label);
      window.history.replaceState({}, "", "/settings?tab=integrations");
    }
  }, [searchParams]);

  const fetchConnectionStatus = useCallback(async () => {
    try {
      const result = await client.GET("/api/v1/auth/me", {});
      if (result.error) {
        const status = (result as { response?: { status?: number } }).response?.status;
        if (status === 401) window.location.href = "/auth/login";
        return;
      }
      const { data } = result;
      const user = data?.data as Record<string, unknown> | undefined;
      if (user) {
        const accounts: GoogleAccountInfo[] = (user.google_accounts as GoogleAccountInfo[]) || [];
        setConnected({
          google: !!user.google_connected || accounts.length > 0,
          google_email: (user.google_email as string) || null,
          google_accounts: accounts,
          telegram: !!user.telegram_connected,
          telegram_username: (user.telegram_username as string) || null,
          twitter: !!user.twitter_connected,
          twitter_username: (user.twitter_username as string) || null,
          linkedin_extension_paired_at:
            (user.linkedin_extension_paired_at as string) || null,
          whatsapp: !!user.whatsapp_connected,
          whatsapp_phone: (user.whatsapp_phone as string) || null,
        });
      }
    } catch {
      // network error
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnectionStatus();
  }, [fetchConnectionStatus]);

  const showSuccessModal = async (platform: string, username?: string | null) => {
    setSuccessPlatform(platform);
    const key = platform.toLowerCase();
    setConnected((prev) => ({
      ...prev,
      [key]: true,
      ...(username ? { [`${key}_username`]: username } : {}),
    }));
    await fetchConnectionStatus();
  };

  // Polling
  const pollForNotification = useCallback(
    (platform: string, setter: (s: SyncState) => void) => {
      let attempts = 0;
      const maxAttempts = 60;
      let baselineCount: number | null = null;
      const interval = setInterval(async () => {
        attempts++;
        try {
          const { data } = await client.GET("/api/v1/notifications/unread-count", {});
          const count = (data as { data?: { count?: number } })?.data?.count ?? 0;
          if (baselineCount === null) {
            baselineCount = count;
          } else if (count > baselineCount) {
            clearInterval(interval);
            setter({
              status: "success",
              message: `${platform} sync completed! Check notifications for details.`,
            });
          } else if (attempts >= maxAttempts) {
            clearInterval(interval);
            setter({
              status: "error",
              message: `${platform} sync is taking too long. The background worker may not be running.`,
            });
          }
        } catch {
          /* ignore */
        }
      }, 2000);
    },
    []
  );

  /* ── Google handlers ── */
  const handleGoogleConnect = async () => {
    setGoogleConnect({ status: "loading", message: "" });
    try {
      const { data, error } = await client.GET("/api/v1/auth/google/url", {});
      if (error || !data?.data) {
        setGoogleConnect({
          status: "error",
          message: "Google OAuth not configured. Set GOOGLE_CLIENT_ID in .env",
        });
        return;
      }
      const url = (data.data as { url?: string })?.url;
      if (url) window.location.href = url;
      else setGoogleConnect({ status: "error", message: "Google OAuth not configured" });
    } catch {
      setGoogleConnect({
        status: "error",
        message: "Google OAuth not configured. Set GOOGLE_CLIENT_ID in .env",
      });
    }
  };

  const handleGoogleSyncAll = async () => {
    setGoogleSync({ status: "loading", message: "" });
    try {
      const results = await Promise.allSettled([
        client.POST("/api/v1/contacts/sync/google"),
        client.POST("/api/v1/contacts/sync/gmail" as any, {}),
        client.POST("/api/v1/contacts/sync/google-calendar"),
      ]);
      const anyError = results.some(
        (r) => r.status === "rejected" || (r.status === "fulfilled" && r.value.error)
      );
      if (anyError) {
        setGoogleSync({
          status: "error",
          message: "Some sync operations failed. Check your Google connection.",
        });
      } else {
        setGoogleSync({
          status: "loading",
          message: "Sync dispatched. Waiting for background worker...",
        });
        pollForNotification("Google", setGoogleSync);
      }
    } catch {
      setGoogleSync({ status: "error", message: "Google sync failed. Please try again." });
    }
  };

  /* ── Telegram handlers ── */
  const handleTelegramSync = async () => {
    setTelegramSync({ status: "loading", message: "" });
    const { error } = await client.POST("/api/v1/contacts/sync/telegram", {});
    if (error) {
      setTelegramSync({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Telegram sync failed.",
      });
    } else {
      setTelegramSync({
        status: "loading",
        message: "Sync dispatched. Waiting for background worker...",
      });
      pollForNotification("Telegram", setTelegramSync);
    }
  };

  /* ── Twitter handlers ── */
  const handleTwitterConnect = async () => {
    setTwitterConnect({ status: "loading", message: "" });
    const { data, error } = await client.GET("/api/v1/auth/twitter/url", {});
    if (error || !data?.data) {
      setTwitterConnect({
        status: "error",
        message: "Twitter OAuth not configured. Set TWITTER_CLIENT_ID in .env",
      });
      return;
    }
    const url = (data.data as { url?: string })?.url;
    if (url) window.location.href = url;
    else setTwitterConnect({ status: "error", message: "Twitter OAuth not configured" });
  };

  const handleTwitterSync = async () => {
    setTwitterSync({ status: "loading", message: "" });
    const { error } = await client.POST("/api/v1/contacts/sync/twitter", {});
    if (error) {
      setTwitterSync({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Sync failed.",
      });
    } else {
      setTwitterSync({
        status: "loading",
        message: "Sync dispatched. Waiting for background worker...",
      });
      pollForNotification("Twitter", setTwitterSync);
    }
  };

  /* ── WhatsApp handlers ── */
  const handleWhatsAppSync = useCallback(async () => {
    setWhatsappSync({ status: "loading", message: "Syncing WhatsApp..." });
    const { error } = await client.POST("/api/v1/contacts/sync/whatsapp", {});
    if (error) {
      setWhatsappSync({ status: "error", message: "Sync failed" });
    } else {
      pollForNotification("whatsapp", setWhatsappSync);
    }
  }, [pollForNotification]);

  return {
    activeTab,
    setTab,
    isLoading,
    connected,
    googleConnect,
    setGoogleConnect,
    googleSync,
    setGoogleSync,
    telegramConnect,
    setTelegramConnect,
    telegramSync,
    setTelegramSync,
    telegramSyncProgress,
    twitterConnect,
    setTwitterConnect,
    twitterSync,
    setTwitterSync,
    whatsappConnect,
    setWhatsappConnect,
    whatsappSync,
    setWhatsappSync,
    handleWhatsAppSync,
    successPlatform,
    setSuccessPlatform,
    showTelegramModal,
    setShowTelegramModal,
    bgSync,
    setBgSync,
    syncFreq,
    setSyncFreq,
    fetchConnectionStatus,
    showSuccessModal,
    pollForNotification,
    handleGoogleConnect,
    handleGoogleSyncAll,
    handleTelegramSync,
    handleTwitterConnect,
    handleTwitterSync,
  };
}
