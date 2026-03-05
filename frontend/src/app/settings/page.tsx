"use client";

import { useState } from "react";
import { Mail, MessageCircle, Twitter, RefreshCw, Check, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

type SyncStatus = "idle" | "loading" | "success" | "error";

interface SyncState {
  status: SyncStatus;
  message: string;
}

function SyncCard({
  icon: Icon,
  title,
  description,
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
  connectLabel: string;
  syncLabel: string;
  onConnect: () => void;
  onSync: () => void;
  connectState: SyncState;
  syncState: SyncState;
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <div className="flex items-start gap-3 mb-4">
        <div className="p-2 rounded-lg bg-gray-50">
          <Icon className="w-5 h-5 text-gray-600" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
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
          {connectLabel}
        </button>

        <button
          onClick={onSync}
          disabled={syncState.status === "loading"}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {syncState.status === "loading" ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5" />
          )}
          {syncLabel}
        </button>
      </div>

      {(connectState.message || syncState.message) && (
        <div className="mt-3 space-y-1">
          {connectState.message && (
            <p className={`text-xs flex items-center gap-1 ${
              connectState.status === "error" ? "text-red-500" : "text-green-600"
            }`}>
              {connectState.status === "error" ? <AlertCircle className="w-3 h-3" /> : <Check className="w-3 h-3" />}
              {connectState.message}
            </p>
          )}
          {syncState.message && (
            <p className={`text-xs flex items-center gap-1 ${
              syncState.status === "error" ? "text-red-500" : "text-green-600"
            }`}>
              {syncState.status === "error" ? <AlertCircle className="w-3 h-3" /> : <Check className="w-3 h-3" />}
              {syncState.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

const defaultState: SyncState = { status: "idle", message: "" };

export default function SettingsPage() {
  const [googleConnect, setGoogleConnect] = useState<SyncState>(defaultState);
  const [googleSync, setGoogleSync] = useState<SyncState>(defaultState);
  const [telegramConnect, setTelegramConnect] = useState<SyncState>(defaultState);
  const [telegramSync, setTelegramSync] = useState<SyncState>(defaultState);
  const [twitterConnect, setTwitterConnect] = useState<SyncState>(defaultState);
  const [twitterSync, setTwitterSync] = useState<SyncState>(defaultState);

  // Phone input for Telegram
  const [telegramPhone, setTelegramPhone] = useState("");
  const [telegramCode, setTelegramCode] = useState("");
  const [telegramPhoneCodeHash, setTelegramPhoneCodeHash] = useState("");
  const [telegramStep, setTelegramStep] = useState<"phone" | "code" | "done">("phone");
  const [showTelegramModal, setShowTelegramModal] = useState(false);

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
      const { data } = await api.post("/contacts/sync/google");
      const r = data?.data;
      setGoogleSync({ status: "success", message: `Created ${r?.created ?? 0}, updated ${r?.updated ?? 0} contacts` });
    } catch {
      setGoogleSync({ status: "error", message: "Sync failed. Connect Google account first." });
    }
  };

  // Telegram
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
    } catch {
      setTelegramConnect({ status: "error", message: "Failed to send code. Check phone number and Telegram API config." });
    }
  };

  const handleTelegramVerify = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    try {
      await api.post("/auth/telegram/verify", { phone: telegramPhone, code: telegramCode, phone_code_hash: telegramPhoneCodeHash });
      setTelegramStep("done");
      setShowTelegramModal(false);
      setTelegramConnect({ status: "success", message: "Telegram connected!" });
    } catch {
      setTelegramConnect({ status: "error", message: "Invalid code. Try again." });
    }
  };

  const handleTelegramSync = async () => {
    setTelegramSync({ status: "loading", message: "" });
    try {
      const { data } = await api.post("/contacts/sync/telegram");
      const r = data?.data;
      setTelegramSync({ status: "success", message: `Synced ${r?.new_interactions ?? 0} interactions` });
    } catch {
      setTelegramSync({ status: "error", message: "Sync failed. Connect Telegram first." });
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
      setTwitterSync({ status: "success", message: "Twitter activity synced" });
    } catch {
      setTwitterSync({ status: "error", message: "Sync failed. Connect Twitter first." });
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Settings</h1>
        <p className="text-sm text-gray-500 mb-8">Manage connected accounts and sync your contacts.</p>

        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">Connected Accounts</h2>

        <div className="space-y-4">
          <SyncCard
            icon={Mail}
            title="Google (Gmail + Contacts)"
            description="Import contacts from Google and sync email interactions"
            connectLabel="Connect Google"
            syncLabel="Sync Contacts"
            onConnect={handleGoogleConnect}
            onSync={handleGoogleContactsSync}
            connectState={googleConnect}
            syncState={googleSync}
          />

          <SyncCard
            icon={MessageCircle}
            title="Telegram"
            description="Sync chat history and match contacts from Telegram"
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
            connectLabel="Connect Twitter"
            syncLabel="Sync Activity"
            onConnect={handleTwitterConnect}
            onSync={handleTwitterSync}
            connectState={twitterConnect}
            syncState={twitterSync}
          />
        </div>
      </div>

      {/* Telegram phone/code modal */}
      {showTelegramModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl p-6 w-full max-w-sm shadow-xl">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Connect Telegram</h3>

            {telegramStep === "phone" && (
              <>
                <label className="block text-sm font-medium text-gray-700 mb-1">Phone number</label>
                <input
                  type="tel"
                  value={telegramPhone}
                  onChange={(e) => setTelegramPhone(e.target.value)}
                  placeholder="+1234567890"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowTelegramModal(false)}
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
                <p className="text-sm text-gray-500 mb-3">
                  Enter the code sent to your Telegram app.
                </p>
                <input
                  type="text"
                  value={telegramCode}
                  onChange={(e) => setTelegramCode(e.target.value)}
                  placeholder="12345"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowTelegramModal(false)}
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
