"use client";

import { Suspense, useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Mail, MessageCircle, Twitter, RefreshCw, Check, AlertCircle, CheckCircle2, X, Calendar, Save } from "lucide-react";
import { Upload } from "lucide-react";
import { client } from "@/lib/api-client";
import { CsvImport } from "@/components/csv-import";
import { TagTaxonomyPanel } from "@/components/tag-taxonomy-panel";

type SyncStatus = "idle" | "loading" | "success" | "error";

interface SyncState {
  status: SyncStatus;
  message: string;
  details?: SyncDetails;
}

interface SyncDetails {
  created?: number;
  updated?: number;
  new_interactions?: number;
  errors?: string[];
  elapsed?: number;
  message?: string;
}

interface GoogleAccountInfo {
  id: string;
  email: string;
}

interface ConnectedAccounts {
  google: boolean;
  google_email?: string | null;
  google_accounts: GoogleAccountInfo[];
  telegram: boolean;
  telegram_username?: string | null;
  twitter: boolean;
  twitter_username?: string | null;
}

function ConnectionBadge({ connected }: { connected: boolean }) {
  if (!connected) return null;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
      <Check className="w-3 h-3" />
      Connected
    </span>
  );
}

function SuccessModal({ platform, onClose }: { platform: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl p-6 w-full max-w-sm shadow-xl text-center">
        <div className="mx-auto w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mb-4">
          <CheckCircle2 className="w-6 h-6 text-green-600" />
        </div>
        <h3 className="text-lg font-semibold text-gray-900 mb-1">{platform} Connected</h3>
        <p className="text-sm text-gray-500 mb-5">
          Your {platform} account has been successfully linked. You can now sync your data.
        </p>
        <button
          onClick={onClose}
          className="w-full px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
        >
          Done
        </button>
      </div>
    </div>
  );
}

type SyncPhase = "idle" | "loading" | "success" | "error";

function SyncButtonWrapper({
  phase,
  children,
}: {
  phase: SyncPhase;
  children: React.ReactNode;
}) {
  const [showSuccess, setShowSuccess] = useState(false);
  const [showError, setShowError] = useState(false);
  const prevPhase = useRef<SyncPhase>("idle");

  useEffect(() => {
    if (prevPhase.current === "loading" && phase === "success") {
      setShowSuccess(true);
      const t = setTimeout(() => setShowSuccess(false), 2000);
      return () => clearTimeout(t);
    }
    if (prevPhase.current === "loading" && phase === "error") {
      setShowError(true);
      const t = setTimeout(() => setShowError(false), 1500);
      return () => clearTimeout(t);
    }
    prevPhase.current = phase;
  }, [phase]);

  return (
    <div className="relative flex-1">
      {children}
      {/* Progress shimmer bar — bottom of button */}
      {phase === "loading" && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-b-lg overflow-hidden">
          <div
            className="h-full bg-white/60 rounded-full"
            style={{
              animation: "shimmer 1.5s ease-in-out infinite",
              width: "40%",
            }}
          />
        </div>
      )}
      {/* Success flash overlay */}
      {showSuccess && (
        <div className="absolute inset-0 rounded-lg bg-green-500/20 pointer-events-none animate-[fadeOut_1.5s_ease-out_forwards]" />
      )}
      {/* Error shake */}
      {showError && (
        <div className="absolute inset-0 rounded-lg bg-red-500/15 pointer-events-none animate-[fadeOut_1s_ease-out_forwards]" />
      )}
      <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(350%); }
        }
        @keyframes fadeOut {
          0% { opacity: 1; }
          100% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}

function SyncResultPanel({ details, status }: { details: SyncDetails; status: SyncStatus }) {
  if (status === "idle" || status === "loading") return null;

  const hasStats = details.created !== undefined || details.updated !== undefined || details.new_interactions !== undefined;
  const hasErrors = details.errors && details.errors.length > 0;

  return (
    <div className={`mt-3 rounded-lg p-3 text-xs ${status === "error" ? "bg-red-50 border border-red-100" : "bg-green-50 border border-green-100"}`}>
      {hasStats && (
        <div className="flex items-center gap-3 mb-1">
          {details.new_interactions !== undefined && (
            <span className="text-green-700">{details.new_interactions} new interaction{details.new_interactions !== 1 ? "s" : ""}</span>
          )}
          {details.created !== undefined && details.created > 0 && (
            <span className="text-blue-700">+{details.created} new contact{details.created !== 1 ? "s" : ""}</span>
          )}
          {details.updated !== undefined && details.updated > 0 && (
            <span className="text-blue-700">{details.updated} updated</span>
          )}
          {details.elapsed !== undefined && (
            <span className="text-gray-500 ml-auto">{details.elapsed}s</span>
          )}
        </div>
      )}
      {hasErrors && (
        <div className="mt-2 space-y-1">
          <p className="font-medium text-red-600 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" />
            {details.errors!.length} error{details.errors!.length > 1 ? "s" : ""}
          </p>
          <ul className="text-red-500 space-y-0.5 max-h-20 overflow-y-auto">
            {details.errors!.map((err, i) => (
              <li key={i} className="truncate">{err}</li>
            ))}
          </ul>
        </div>
      )}
      {!hasStats && !hasErrors && status === "error" && (
        <p className="text-red-600">{details.message || "Sync failed"}</p>
      )}
    </div>
  );
}

function SyncCard({
  icon: Icon,
  title,
  description,
  connected,
  connectedLabel,
  connectLabel,
  syncLabel,
  onConnect,
  onSync,
  connectState,
  syncState,
}: {
  icon: typeof Mail;
  title: string;
  description: string;
  connected: boolean;
  connectedLabel?: string | null;
  connectLabel: string;
  syncLabel: string;
  onConnect: () => void;
  onSync: () => void;
  connectState: SyncState;
  syncState: SyncState;
}) {
  return (
    <div className={`bg-white rounded-lg border p-5 ${connected ? "border-green-200" : "border-gray-200"}`}>
      <div className="flex items-start gap-3 mb-4">
        <div className={`p-2 rounded-lg ${connected ? "bg-green-50" : "bg-gray-50"}`}>
          <Icon className={`w-5 h-5 ${connected ? "text-green-600" : "text-gray-600"}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
            <ConnectionBadge connected={connected} />
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{description}</p>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onConnect}
          disabled={connectState.status === "loading"}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          {connectState.status === "loading" ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : connectState.status === "success" ? (
            <Check className="w-3.5 h-3.5 text-green-600" />
          ) : null}
          {connected ? "Reconnect" : connectLabel}
        </button>

        <SyncButtonWrapper phase={syncState.status as SyncPhase}>
          <button
            onClick={onSync}
            disabled={syncState.status === "loading" || !connected}
            className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {syncState.status === "loading" ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : syncState.status === "success" ? (
              <Check className="w-3.5 h-3.5 animate-[scaleIn_0.3s_ease-out]" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            {syncState.status === "loading" ? "Syncing..." : syncState.status === "success" ? "Done" : syncLabel}
          </button>
        </SyncButtonWrapper>
      </div>

      {connected && connectedLabel && (
        <p className="mt-2.5 text-xs font-medium text-green-600 flex items-center gap-1">
          <Check className="w-3 h-3" />
          connected {connectedLabel}
        </p>
      )}

      {connectState.message && (
        <p className={`text-xs mt-3 flex items-center gap-1 ${
          connectState.status === "error" ? "text-red-500" : "text-green-600"
        }`}>
          {connectState.status === "error" ? <AlertCircle className="w-3 h-3" /> : <Check className="w-3 h-3" />}
          {connectState.message}
        </p>
      )}

      {syncState.message && !syncState.details && (
        <p className={`text-xs mt-3 flex items-center gap-1 ${
          syncState.status === "error" ? "text-red-500" : "text-green-600"
        }`}>
          {syncState.status === "error" ? <AlertCircle className="w-3 h-3" /> : <Check className="w-3 h-3" />}
          {syncState.message}
        </p>
      )}

      {syncState.details && (
        <SyncResultPanel details={syncState.details} status={syncState.status} />
      )}
    </div>
  );
}

function LinkedInImport() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [result, setResult] = useState<{ created: number; skipped: number; errors: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setStatus("loading");
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const { data, error } = await client.POST("/api/v1/contacts/import/linkedin", {
        body: formData as unknown as { file: string },
        bodySerializer: () => formData,
      });
      if (error) {
        setError((error as { detail?: string })?.detail ?? "Import failed");
        setStatus("error");
      } else {
        setResult(data?.data as { created: number; skipped: number; errors: string[] });
        setStatus("success");
      }
    } catch {
      setError("Import failed");
      setStatus("error");
    }
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">LinkedIn Connections</h3>
      <p className="text-xs text-gray-500 mb-3">
        Upload your Connections.csv from{" "}
        <a href="https://www.linkedin.com/mypreferences/d/download-my-data" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
          LinkedIn Data Export
        </a>
      </p>
      <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); }} />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={status === "loading"}
        className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
      >
        <Upload className="w-3.5 h-3.5" />
        {status === "loading" ? "Importing..." : "Upload Connections.csv"}
      </button>
      {result && (
        <p className="text-xs mt-2 text-green-600">
          Imported {result.created} contacts{result.skipped > 0 ? `, ${result.skipped} duplicates skipped` : ""}
          {result.errors.length > 0 ? `, ${result.errors.length} errors` : ""}
        </p>
      )}
      {error && <p className="text-xs mt-2 text-red-500">{error}</p>}
    </div>
  );
}

function LinkedInMessagesImport() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [result, setResult] = useState<{ new_interactions: number; skipped: number; unmatched: number; unmatched_names: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setStatus("loading");
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const { data, error } = await client.POST("/api/v1/contacts/import/linkedin-messages", {
        body: formData as unknown as { file: string },
        bodySerializer: () => formData,
      });
      if (error) {
        setError((error as { detail?: string })?.detail ?? "Import failed");
        setStatus("error");
      } else {
        setResult(data?.data as { new_interactions: number; skipped: number; unmatched: number; unmatched_names: string[] });
        setStatus("success");
      }
    } catch {
      setError("Import failed");
      setStatus("error");
    }
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">LinkedIn Messages</h3>
      <p className="text-xs text-gray-500 mb-3">
        Upload your messages.csv to import conversation history. Messages are matched to existing contacts by name.
      </p>
      <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); }} />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={status === "loading"}
        className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
      >
        <Upload className="w-3.5 h-3.5" />
        {status === "loading" ? "Importing..." : "Upload messages.csv"}
      </button>
      {result && (
        <div className="text-xs mt-2">
          <p className="text-green-600">
            Imported {result.new_interactions} messages{result.skipped > 0 ? `, ${result.skipped} duplicates skipped` : ""}
          </p>
          {result.unmatched > 0 && (
            <p className="text-yellow-600 mt-1">
              {result.unmatched} contacts not found: {result.unmatched_names.join(", ")}
              {result.unmatched > result.unmatched_names.length ? "..." : ""}
            </p>
          )}
        </div>
      )}
      {error && <p className="text-xs mt-2 text-red-500">{error}</p>}
    </div>
  );
}

interface PrioritySettings {
  high: number;
  medium: number;
  low: number;
}

function PriorityTab() {
  const [settings, setSettings] = useState<PrioritySettings>({ high: 30, medium: 60, low: 180 });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await client.GET("/api/v1/settings/priority" as any, {});
        const ps = (data as any)?.data;
        if (ps) setSettings({ high: ps.high, medium: ps.medium, low: ps.low });
      } catch {
        // use defaults
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setFeedback(null);
    try {
      const { data, error } = await client.PUT("/api/v1/settings/priority" as any, {
        body: settings,
      });
      if (error) {
        setFeedback({ type: "error", message: (error as any)?.detail ?? "Failed to save" });
      } else {
        const ps = (data as any)?.data;
        if (ps) setSettings({ high: ps.high, medium: ps.medium, low: ps.low });
        setFeedback({ type: "success", message: "Priority settings saved" });
      }
    } catch {
      setFeedback({ type: "error", message: "Failed to save" });
    } finally {
      setIsSaving(false);
    }
  };

  const clamp = (v: number) => Math.max(7, Math.min(365, v));

  const levels: { key: keyof PrioritySettings; label: string; color: string; bg: string }[] = [
    { key: "high", label: "\uD83D\uDD25 High", color: "text-red-700", bg: "bg-red-50 border-red-200" },
    { key: "medium", label: "\u26A1 Medium", color: "text-yellow-700", bg: "bg-yellow-50 border-yellow-200" },
    { key: "low", label: "\uD83D\uDCA4 Low", color: "text-gray-600", bg: "bg-gray-50 border-gray-200" },
  ];

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400 mt-8 justify-center">
        <RefreshCw className="w-4 h-4 animate-spin" />
        Loading settings...
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">Follow-up Intervals</h3>
      <p className="text-xs text-gray-500 mb-5">
        Configure how often you&apos;d like to be reminded to follow up with contacts based on their priority level.
      </p>

      <div className="space-y-4">
        {levels.map(({ key, label, color, bg }) => (
          <div key={key} className="flex items-center gap-3">
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${bg} ${color} w-20 justify-center`}>
              {label}
            </span>
            <div className="flex items-center gap-2 flex-1">
              <span className="text-sm text-gray-600">Every</span>
              <input
                type="number"
                min={7}
                max={365}
                value={settings[key]}
                onChange={(e) => setSettings((s) => ({ ...s, [key]: clamp(Number(e.target.value) || 7) }))}
                className="w-20 px-2 py-1.5 rounded-lg border border-gray-300 text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
              <span className="text-sm text-gray-500">days</span>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {isSaving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          Save
        </button>
        {feedback && (
          <p className={`text-xs flex items-center gap-1 ${feedback.type === "error" ? "text-red-500" : "text-green-600"}`}>
            {feedback.type === "error" ? <AlertCircle className="w-3 h-3" /> : <Check className="w-3 h-3" />}
            {feedback.message}
          </p>
        )}
      </div>
    </div>
  );
}

const defaultState: SyncState = { status: "idle", message: "" };

function SettingsPageInner() {
  const [isLoading, setIsLoading] = useState(true);
  const [connected, setConnected] = useState<ConnectedAccounts>({ google: false, telegram: false, twitter: false, google_email: null, google_accounts: [], telegram_username: null, twitter_username: null });
  const [googleConnect, setGoogleConnect] = useState<SyncState>(defaultState);
  const [googleSync, setGoogleSync] = useState<SyncState>(defaultState);
  const [gmailSync, setGmailSync] = useState<SyncState>(defaultState);
  const [calendarSync, setCalendarSync] = useState<SyncState>(defaultState);
  const [telegramConnect, setTelegramConnect] = useState<SyncState>(defaultState);
  const [telegramSync, setTelegramSync] = useState<SyncState>(defaultState);
  const [twitterConnect, setTwitterConnect] = useState<SyncState>(defaultState);
  const [twitterSync, setTwitterSync] = useState<SyncState>(defaultState);

  // Success modal
  const [successPlatform, setSuccessPlatform] = useState<string | null>(null);

  // Phone input for Telegram
  const [telegramPhone, setTelegramPhone] = useState("");
  const [telegramCode, setTelegramCode] = useState("");
  const [telegramPhoneCodeHash, setTelegramPhoneCodeHash] = useState("");
  const [telegramPassword, setTelegramPassword] = useState("");
  const [telegramStep, setTelegramStep] = useState<"phone" | "code" | "password" | "done">("phone");
  const [showTelegramModal, setShowTelegramModal] = useState(false);

  // Tab state from URL
  const searchParams = useSearchParams();
  const router = useRouter();
  const activeTab = searchParams.get("tab") || "sync";

  const setTab = (tab: string) => {
    router.replace(`/settings?tab=${tab}`, { scroll: false });
  };

  // Detect OAuth redirect (e.g. ?connected=twitter)
  useEffect(() => {
    const platform = searchParams.get("connected");
    if (platform) {
      const label = platform.charAt(0).toUpperCase() + platform.slice(1);
      setSuccessPlatform(label);
      window.history.replaceState({}, "", "/settings?tab=sync");
    }
  }, [searchParams]);

  const fetchConnectionStatus = useCallback(async () => {
    try {
      const result = await client.GET("/api/v1/auth/me");
      if (result.error) {
        // Only redirect on 401; ignore other errors (e.g. network, 500)
        const status = (result as { response?: { status?: number } }).response?.status;
        if (status === 401) {
          window.location.href = "/auth/login";
        }
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

  const showSuccess = async (platform: string, username?: string | null) => {
    setSuccessPlatform(platform);
    const key = platform.toLowerCase();
    // Optimistically mark as connected immediately
    setConnected((prev) => ({
      ...prev,
      [key]: true,
      ...(username ? { [`${key}_username`]: username } : {}),
    }));
    // Then confirm from server
    await fetchConnectionStatus();
  };

  // Google
  const handleGoogleConnect = async () => {
    setGoogleConnect({ status: "loading", message: "" });
    try {
      const { data, error } = await client.GET("/api/v1/auth/google/url");
      if (error || !data?.data) {
        setGoogleConnect({ status: "error", message: "Google OAuth not configured. Set GOOGLE_CLIENT_ID in .env" });
        return;
      }
      const url = (data.data as { url?: string })?.url;
      if (url) {
        window.location.href = url;
      } else {
        setGoogleConnect({ status: "error", message: "Google OAuth not configured" });
      }
    } catch {
      setGoogleConnect({ status: "error", message: "Google OAuth not configured. Set GOOGLE_CLIENT_ID in .env" });
    }
  };

  const handleGoogleContactsSync = async () => {
    setGoogleSync({ status: "loading", message: "" });
    const { error } = await client.POST("/api/v1/contacts/sync/google");
    if (error) {
      setGoogleSync({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Sync failed. Connect Google account first.",
      });
    } else {
      setGoogleSync({
        status: "loading",
        message: "Sync dispatched. Waiting for background worker...",
      });
      pollForNotification("Google Contacts", setGoogleSync);
    }
  };

  const handleGoogleCalendarSync = async () => {
    setCalendarSync({ status: "loading", message: "" });
    const { error } = await client.POST("/api/v1/contacts/sync/google-calendar");
    if (error) {
      setCalendarSync({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Calendar sync failed. Connect Google account first.",
      });
    } else {
      setCalendarSync({
        status: "loading",
        message: "Sync dispatched. Waiting for background worker...",
      });
      pollForNotification("Google Calendar", setCalendarSync);
    }
  };

  const handleGmailSync = async () => {
    setGmailSync({ status: "loading", message: "" });
    const { error } = await client.POST("/api/v1/contacts/sync/gmail" as any);
    if (error) {
      setGmailSync({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Gmail sync failed. Connect Google account first.",
      });
    } else {
      setGmailSync({
        status: "loading",
        message: "Sync dispatched. Waiting for background worker...",
      });
      pollForNotification("Gmail", setGmailSync);
    }
  };

  // Telegram
  const closeTelegramModal = () => {
    setShowTelegramModal(false);
    setTelegramStep("phone");
    setTelegramPhone("");
    setTelegramCode("");
    setTelegramPassword("");
    setTelegramPhoneCodeHash("");
    setTelegramConnect({ status: "idle", message: "" });
  };

  const handleTelegramConnect = () => {
    setShowTelegramModal(true);
    setTelegramStep("phone");
    setTelegramConnect({ status: "idle", message: "" });
  };

  const handleTelegramSendCode = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    const { data, error } = await client.POST("/api/v1/auth/telegram/connect", {
      body: { phone: telegramPhone },
    });
    if (error) {
      setTelegramConnect({ status: "error", message: (error as { detail?: string })?.detail ?? "Failed to send code. Check phone number and Telegram API config." });
    } else {
      setTelegramPhoneCodeHash((data?.data as { phone_code_hash?: string })?.phone_code_hash ?? "");
      setTelegramStep("code");
      setTelegramConnect({ status: "idle", message: "Code sent to your Telegram app" });
    }
  };

  const handleTelegramVerify = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    const { data, error } = await client.POST("/api/v1/auth/telegram/verify", {
      body: { phone: telegramPhone, code: telegramCode, phone_code_hash: telegramPhoneCodeHash },
    });
    if (error) {
      setTelegramConnect({ status: "error", message: (error as { detail?: string })?.detail ?? "Invalid code. Try again." });
      return;
    }
    const respData = data?.data as { requires_2fa?: boolean; username?: string } | undefined;
    if (respData?.requires_2fa) {
      setTelegramStep("password");
      setTelegramConnect({ status: "idle", message: "Two-step verification is enabled. Enter your Telegram password." });
      return;
    }
    setTelegramStep("done");
    setTelegramCode("");
    closeTelegramModal();
    setTelegramConnect({ status: "success", message: "" });
    await showSuccess("Telegram", respData?.username);
  };

  const handleTelegram2FA = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    const { data, error } = await client.POST("/api/v1/auth/telegram/verify-2fa", {
      body: { password: telegramPassword },
    });
    if (error) {
      setTelegramPassword("");
      setTelegramConnect({ status: "error", message: (error as { detail?: string })?.detail ?? "Incorrect password. Try again." });
      return;
    }
    setTelegramStep("done");
    setTelegramPassword("");
    closeTelegramModal();
    setTelegramConnect({ status: "success", message: "" });
    await showSuccess("Telegram", (data?.data as { username?: string })?.username);
  };

  const pollForNotification = useCallback((platform: string, setter: (s: SyncState) => void) => {
    let attempts = 0;
    const maxAttempts = 60; // ~2 minutes
    const interval = setInterval(async () => {
      attempts++;
      try {
        const { data } = await client.GET("/api/v1/notifications/unread-count");
        const count = (data as { data?: { count?: number } })?.data?.count ?? 0;
        if (count > 0) {
          clearInterval(interval);
          setter({
            status: "success",
            message: `${platform} sync completed! Check notifications for details.`,
          });
        } else if (attempts >= maxAttempts) {
          clearInterval(interval);
          setter({
            status: "error",
            message: `${platform} sync is taking too long. The background worker may not be running. Try: celery -A worker.celery_app worker --beat --loglevel=info`,
          });
        }
      } catch {
        // ignore polling errors
      }
    }, 2000);
  }, []);

  const handleTelegramSync = async () => {
    setTelegramSync({ status: "loading", message: "" });
    const { error } = await client.POST("/api/v1/contacts/sync/telegram");
    if (error) {
      setTelegramSync({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Telegram sync failed. Please try again.",
      });
    } else {
      setTelegramSync({
        status: "loading",
        message: "Sync dispatched. Waiting for background worker...",
      });
      pollForNotification("Telegram", setTelegramSync);
    }
  };

  // Twitter
  const handleTwitterConnect = async () => {
    setTwitterConnect({ status: "loading", message: "" });
    const { data, error } = await client.GET("/api/v1/auth/twitter/url");
    if (error || !data?.data) {
      setTwitterConnect({ status: "error", message: "Twitter OAuth not configured. Set TWITTER_CLIENT_ID in .env" });
      return;
    }
    const url = (data.data as { url?: string })?.url;
    if (url) {
      window.location.href = url;
    } else {
      setTwitterConnect({ status: "error", message: "Twitter OAuth not configured" });
    }
  };

  const handleTwitterSync = async () => {
    setTwitterSync({ status: "loading", message: "" });
    const { error } = await client.POST("/api/v1/contacts/sync/twitter");
    if (error) {
      setTwitterSync({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Sync failed. Connect Twitter first.",
      });
    } else {
      setTwitterSync({
        status: "loading",
        message: "Sync dispatched. Waiting for background worker...",
      });
      pollForNotification("Twitter", setTwitterSync);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-2xl mx-auto px-4 py-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">Settings</h1>
          <p className="text-sm text-gray-500 mb-8">Manage connected accounts and sync your contacts.</p>
          <div className="flex items-center gap-2 text-sm text-gray-400 mt-12 justify-center">
            <RefreshCw className="w-4 h-4 animate-spin" />
            Loading accounts...
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Settings</h1>
        <p className="text-sm text-gray-500 mb-6">Manage connected accounts and sync your contacts.</p>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-gray-200 mb-6">
          <button
            onClick={() => setTab("sync")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "sync"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Connect + Sync
          </button>
          <button
            onClick={() => setTab("priority")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "priority"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Priority
          </button>
          <button
            onClick={() => setTab("tags")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "tags"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Tags
          </button>
        </div>

        {activeTab === "priority" ? (
          <PriorityTab />
        ) : activeTab === "tags" ? (
          <TagTaxonomyPanel />
        ) : (
        <>
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">Connected Accounts</h2>

        <div className="space-y-4">
          <div className={`bg-white rounded-lg border p-5 ${connected.google ? "border-green-200" : "border-gray-200"}`}>
            <div className="flex items-start gap-3 mb-4">
              <div className={`p-2 rounded-lg ${connected.google ? "bg-green-50" : "bg-gray-50"}`}>
                <Mail className={`w-5 h-5 ${connected.google ? "text-green-600" : "text-gray-600"}`} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-gray-900">Google (Gmail + Contacts + Calendar)</h3>
                  <ConnectionBadge connected={connected.google} />
                </div>
                <p className="text-xs text-gray-500 mt-0.5">Import contacts, sync email interactions, and pull calendar meetings</p>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleGoogleConnect}
                disabled={googleConnect.status === "loading"}
                className="flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                {googleConnect.status === "loading" ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : googleConnect.status === "success" ? (
                  <Check className="w-3.5 h-3.5 text-green-600" />
                ) : null}
                {connected.google ? "Add Google Account" : "Connect Google"}
              </button>

              <SyncButtonWrapper phase={googleSync.status as SyncPhase}>
                <button
                  onClick={handleGoogleContactsSync}
                  disabled={googleSync.status === "loading" || !connected.google}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {googleSync.status === "loading" ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : googleSync.status === "success" ? (
                    <Check className="w-3.5 h-3.5" />
                  ) : (
                    <Mail className="w-3.5 h-3.5" />
                  )}
                  {googleSync.status === "loading" ? "Syncing..." : googleSync.status === "success" ? "Done" : "Sync Contacts"}
                </button>
              </SyncButtonWrapper>

              <SyncButtonWrapper phase={gmailSync.status as SyncPhase}>
                <button
                  onClick={handleGmailSync}
                  disabled={gmailSync.status === "loading" || !connected.google}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {gmailSync.status === "loading" ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : gmailSync.status === "success" ? (
                    <Check className="w-3.5 h-3.5" />
                  ) : (
                    <Mail className="w-3.5 h-3.5" />
                  )}
                  {gmailSync.status === "loading" ? "Syncing..." : gmailSync.status === "success" ? "Done" : "Sync Gmail"}
                </button>
              </SyncButtonWrapper>

              <SyncButtonWrapper phase={calendarSync.status as SyncPhase}>
                <button
                  onClick={handleGoogleCalendarSync}
                  disabled={calendarSync.status === "loading" || !connected.google}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {calendarSync.status === "loading" ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : calendarSync.status === "success" ? (
                    <Check className="w-3.5 h-3.5" />
                  ) : (
                    <Calendar className="w-3.5 h-3.5" />
                  )}
                  {calendarSync.status === "loading" ? "Syncing..." : calendarSync.status === "success" ? "Done" : "Sync Calendar"}
                </button>
              </SyncButtonWrapper>
            </div>

            {connected.google_accounts.length > 0 && (
              <div className="mt-2.5 space-y-1">
                {connected.google_accounts.map((ga) => (
                  <div key={ga.id} className="flex items-center justify-between text-xs">
                    <span className="font-medium text-green-600 flex items-center gap-1">
                      <Check className="w-3 h-3" />
                      {ga.email}
                    </span>
                    <button
                      onClick={async () => {
                        await client.DELETE("/api/v1/auth/google/accounts/{account_id}", {
                          params: { path: { account_id: ga.id } },
                        });
                        await fetchConnectionStatus();
                      }}
                      className="text-gray-400 hover:text-red-500 transition-colors"
                      title="Remove account"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {connected.google && connected.google_accounts.length === 0 && connected.google_email && (
              <p className="mt-2.5 text-xs font-medium text-green-600 flex items-center gap-1">
                <Check className="w-3 h-3" />
                {connected.google_email}
              </p>
            )}

            {googleConnect.message && (
              <p className={`text-xs mt-3 flex items-center gap-1 ${
                googleConnect.status === "error" ? "text-red-500" : "text-green-600"
              }`}>
                {googleConnect.status === "error" ? <AlertCircle className="w-3 h-3" /> : <Check className="w-3 h-3" />}
                {googleConnect.message}
              </p>
            )}

            {googleSync.details && (
              <SyncResultPanel details={googleSync.details} status={googleSync.status} />
            )}
            {gmailSync.message && !gmailSync.details && (
              <p className={`text-xs mt-3 flex items-center gap-1 ${
                gmailSync.status === "error" ? "text-red-500" : "text-green-600"
              }`}>
                {gmailSync.status === "error" ? <AlertCircle className="w-3 h-3" /> : <Check className="w-3 h-3" />}
                {gmailSync.message}
              </p>
            )}
            {gmailSync.details && (
              <SyncResultPanel details={gmailSync.details} status={gmailSync.status} />
            )}
            {calendarSync.details && (
              <SyncResultPanel details={calendarSync.details} status={calendarSync.status} />
            )}
          </div>

          <SyncCard
            icon={MessageCircle}
            title="Telegram"
            description="Sync chat history and match contacts from Telegram"
            connected={connected.telegram}
            connectedLabel={connected.telegram_username ? `@${connected.telegram_username}` : null}
            connectLabel="Connect Telegram"
            syncLabel="Sync Chats"
            onConnect={handleTelegramConnect}
            onSync={handleTelegramSync}
            connectState={telegramConnect}
            syncState={telegramSync}
          />

          <SyncCard
            icon={Twitter}
            title="Twitter / X"
            description="Sync DMs, mentions, and monitor bio changes"
            connected={connected.twitter}
            connectedLabel={connected.twitter_username ? `@${connected.twitter_username}` : null}
            connectLabel="Connect Twitter"
            syncLabel="Sync Activity"
            onConnect={handleTwitterConnect}
            onSync={handleTwitterSync}
            connectState={twitterConnect}
            syncState={twitterSync}
          />
        </div>

        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3 mt-8">Import Contacts</h2>
        <div className="space-y-4">
          <LinkedInImport />
          <LinkedInMessagesImport />
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-1">Generic CSV</h3>
            <p className="text-xs text-gray-500 mb-3">Upload any CSV file. Supported columns: name, email, phone, company, title, tags.</p>
            <CsvImport />
          </div>
        </div>
        </>
        )}
      </div>

      {/* Success modal */}
      {successPlatform && (
        <SuccessModal
          platform={successPlatform}
          onClose={() => setSuccessPlatform(null)}
        />
      )}

      {/* Telegram phone/code/password modal */}
      {showTelegramModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Connect Telegram</h3>
              <button onClick={closeTelegramModal} aria-label="Close" className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            {telegramStep === "phone" && (
              <>
                <label htmlFor="telegram-phone" className="block text-sm font-medium text-gray-700 mb-1">Phone number</label>
                <input
                  id="telegram-phone"
                  type="tel"
                  value={telegramPhone}
                  onChange={(e) => setTelegramPhone(e.target.value)}
                  placeholder="+1234567890"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={closeTelegramModal}
                    className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleTelegramSendCode}
                    disabled={!telegramPhone.trim() || telegramConnect.status === "loading"}
                    className="flex-1 px-3 py-2 text-sm rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50"
                  >
                    {telegramConnect.status === "loading" ? "Sending..." : "Send code"}
                  </button>
                </div>
              </>
            )}

            {telegramStep === "code" && (
              <>
                <label htmlFor="telegram-code" className="block text-sm text-gray-500 mb-3">
                  Enter the code sent to your Telegram app.
                </label>
                <input
                  id="telegram-code"
                  type="text"
                  value={telegramCode}
                  onChange={(e) => setTelegramCode(e.target.value)}
                  placeholder="12345"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={closeTelegramModal}
                    className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleTelegramVerify}
                    disabled={!telegramCode.trim() || telegramConnect.status === "loading"}
                    className="flex-1 px-3 py-2 text-sm rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50"
                  >
                    {telegramConnect.status === "loading" ? "Verifying..." : "Verify"}
                  </button>
                </div>
              </>
            )}

            {telegramStep === "password" && (
              <>
                <label htmlFor="telegram-password" className="block text-sm text-gray-500 mb-3">
                  Your account has two-step verification. Enter your Telegram password.
                </label>
                <input
                  id="telegram-password"
                  type="password"
                  value={telegramPassword}
                  onChange={(e) => setTelegramPassword(e.target.value)}
                  placeholder="Telegram password"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={closeTelegramModal}
                    className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleTelegram2FA}
                    disabled={!telegramPassword.trim() || telegramConnect.status === "loading"}
                    className="flex-1 px-3 py-2 text-sm rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50"
                  >
                    {telegramConnect.status === "loading" ? "Verifying..." : "Submit"}
                  </button>
                </div>
              </>
            )}

            {telegramConnect.message && (
              <p className={`text-xs mt-3 ${telegramConnect.status === "error" ? "text-red-500" : "text-green-600"}`}>
                {telegramConnect.message}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
      <SettingsPageInner />
    </Suspense>
  );
}
