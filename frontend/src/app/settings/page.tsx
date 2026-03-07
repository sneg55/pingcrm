"use client";

import { Suspense, useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { Mail, MessageCircle, Twitter, RefreshCw, Check, AlertCircle, CheckCircle2, X, Clock, Calendar } from "lucide-react";
import { Upload } from "lucide-react";
import { api } from "@/lib/api";
import { CsvImport } from "@/components/csv-import";

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

function ElapsedTimer({ running }: { running: boolean }) {
  const [seconds, setSeconds] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  useEffect(() => {
    if (running) {
      setSeconds(0);
      intervalRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [running]);

  if (!running) return null;

  return (
    <span className="inline-flex items-center gap-1 text-xs text-gray-400">
      <Clock className="w-3 h-3" />
      {seconds}s
    </span>
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

        <button
          onClick={onSync}
          disabled={syncState.status === "loading" || !connected}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {syncState.status === "loading" ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : syncState.status === "success" ? (
            <Check className="w-3.5 h-3.5" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5" />
          )}
          {syncLabel}
          <ElapsedTimer running={syncState.status === "loading"} />
        </button>
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
      const { data } = await api.post("/contacts/import/linkedin", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data.data);
      setStatus("success");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Import failed");
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
      const { data } = await api.post("/contacts/import/linkedin-messages", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data.data);
      setStatus("success");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Import failed");
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

const defaultState: SyncState = { status: "idle", message: "" };

function SettingsPageInner() {
  const [isLoading, setIsLoading] = useState(true);
  const [connected, setConnected] = useState<ConnectedAccounts>({ google: false, telegram: false, twitter: false, google_email: null, google_accounts: [], telegram_username: null, twitter_username: null });
  const [googleConnect, setGoogleConnect] = useState<SyncState>(defaultState);
  const [googleSync, setGoogleSync] = useState<SyncState>(defaultState);
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

  // Detect OAuth redirect (e.g. ?connected=twitter)
  const searchParams = useSearchParams();
  useEffect(() => {
    const platform = searchParams.get("connected");
    if (platform) {
      const label = platform.charAt(0).toUpperCase() + platform.slice(1);
      setSuccessPlatform(label);
      window.history.replaceState({}, "", "/settings");
    }
  }, [searchParams]);

  const fetchConnectionStatus = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      const user = data?.data;
      if (user) {
        const accounts: GoogleAccountInfo[] = user.google_accounts || [];
        setConnected({
          google: !!user.google_connected || accounts.length > 0,
          google_email: user.google_email || null,
          google_accounts: accounts,
          telegram: !!user.telegram_connected,
          telegram_username: user.telegram_username || null,
          twitter: !!user.twitter_connected,
          twitter_username: user.twitter_username || null,
        });
      }
    } catch (err: unknown) {
      const s = (err as { response?: { status?: number } })?.response?.status;
      if (s === 401) {
        window.location.href = "/auth/login";
        return;
      }
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
      const { data } = await api.get("/auth/google/url");
      if (data?.data?.url) {
        window.location.href = data.data.url;
      } else {
        setGoogleConnect({ status: "error", message: "Google OAuth not configured" });
      }
    } catch {
      setGoogleConnect({ status: "error", message: "Google OAuth not configured. Set GOOGLE_CLIENT_ID in .env" });
    }
  };

  const handleGoogleContactsSync = async () => {
    setGoogleSync({ status: "loading", message: "" });
    try {
      await api.post("/contacts/sync/google");
      setGoogleSync({
        status: "success",
        message: "Sync started. You'll be notified when it completes.",
      });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setGoogleSync({
        status: "error",
        message: detail || "Sync failed. Connect Google account first.",
      });
    }
  };

  const handleGoogleCalendarSync = async () => {
    setCalendarSync({ status: "loading", message: "" });
    try {
      await api.post("/contacts/sync/google-calendar");
      setCalendarSync({
        status: "success",
        message: "Sync started. You'll be notified when it completes.",
      });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setCalendarSync({
        status: "error",
        message: detail || "Calendar sync failed. Connect Google account first.",
      });
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
    try {
      const { data } = await api.post("/auth/telegram/connect", { phone: telegramPhone });
      setTelegramPhoneCodeHash(data?.data?.phone_code_hash ?? "");
      setTelegramStep("code");
      setTelegramConnect({ status: "idle", message: "Code sent to your Telegram app" });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTelegramConnect({ status: "error", message: detail || "Failed to send code. Check phone number and Telegram API config." });
    }
  };

  const handleTelegramVerify = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    try {
      const { data } = await api.post("/auth/telegram/verify", { phone: telegramPhone, code: telegramCode, phone_code_hash: telegramPhoneCodeHash });
      if (data?.data?.requires_2fa) {
        setTelegramStep("password");
        setTelegramConnect({ status: "idle", message: "Two-step verification is enabled. Enter your Telegram password." });
        return;
      }
      setTelegramStep("done");
      setTelegramCode("");
      closeTelegramModal();
      setTelegramConnect({ status: "success", message: "" });
      await showSuccess("Telegram", data?.data?.username);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTelegramConnect({ status: "error", message: detail || "Invalid code. Try again." });
    }
  };

  const handleTelegram2FA = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    try {
      const { data } = await api.post("/auth/telegram/verify-2fa", { password: telegramPassword });
      setTelegramStep("done");
      setTelegramPassword("");
      closeTelegramModal();
      setTelegramConnect({ status: "success", message: "" });
      await showSuccess("Telegram", data?.data?.username);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTelegramPassword("");
      setTelegramConnect({ status: "error", message: detail || "Incorrect password. Try again." });
    }
  };

  const handleTelegramSync = async () => {
    setTelegramSync({ status: "loading", message: "" });
    try {
      await api.post("/contacts/sync/telegram");
      setTelegramSync({
        status: "success",
        message: "Sync started. You'll be notified when it completes.",
      });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTelegramSync({
        status: "error",
        message: detail || "Telegram sync failed. Please try again.",
      });
    }
  };

  // Twitter
  const handleTwitterConnect = async () => {
    setTwitterConnect({ status: "loading", message: "" });
    try {
      const { data } = await api.get("/auth/twitter/url");
      if (data?.data?.url) {
        window.location.href = data.data.url;
      } else {
        setTwitterConnect({ status: "error", message: "Twitter OAuth not configured" });
      }
    } catch {
      setTwitterConnect({ status: "error", message: "Twitter OAuth not configured. Set TWITTER_CLIENT_ID in .env" });
    }
  };

  const handleTwitterSync = async () => {
    setTwitterSync({ status: "loading", message: "" });
    try {
      await api.post("/contacts/sync/twitter");
      setTwitterSync({
        status: "success",
        message: "Sync started. You'll be notified when it completes.",
      });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTwitterSync({
        status: "error",
        message: detail || "Sync failed. Connect Twitter first.",
      });
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
        <p className="text-sm text-gray-500 mb-8">Manage connected accounts and sync your contacts.</p>

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

              <button
                onClick={handleGoogleContactsSync}
                disabled={googleSync.status === "loading" || !connected.google}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {googleSync.status === "loading" ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Mail className="w-3.5 h-3.5" />
                )}
                Sync Contacts
                <ElapsedTimer running={googleSync.status === "loading"} />
              </button>

              <button
                onClick={handleGoogleCalendarSync}
                disabled={calendarSync.status === "loading" || !connected.google}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {calendarSync.status === "loading" ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Calendar className="w-3.5 h-3.5" />
                )}
                Sync Calendar
                <ElapsedTimer running={calendarSync.status === "loading"} />
              </button>
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
                        try {
                          await api.delete(`/auth/google/accounts/${ga.id}`);
                          await fetchConnectionStatus();
                        } catch { /* ignore */ }
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
