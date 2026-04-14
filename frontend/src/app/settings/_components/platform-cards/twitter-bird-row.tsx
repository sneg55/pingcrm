"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw, Link2, Unplug, X, AlertTriangle } from "lucide-react";
import { client } from "@/lib/api-client";
import { sendToExtension } from "@/lib/extension-bridge";
import { TwitterIcon } from "../shared";

type BirdStatus = "disconnected" | "connected" | "expired";

interface BirdStatusData {
  status: BirdStatus;
  checked_at: string | null;
}

export function TwitterBirdRow() {
  const [state, setState] = useState<BirdStatusData>({ status: "disconnected", checked_at: null });
  const [busy, setBusy] = useState(false);
  const [showInstallModal, setShowInstallModal] = useState(false);

  const refresh = useCallback(async () => {
    const result = await (client as any).GET("/api/v1/integrations/twitter/cookies", {});
    if (result.data?.data) {
      setState(result.data.data as BirdStatusData);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while expired — the extension auto-pushes on cookie rotation, so the
  // status will flip to connected on its own once the user signs in to x.com.
  useEffect(() => {
    if (state.status !== "expired") return;
    const id = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(id);
  }, [state.status, refresh]);

  async function onConnect() {
    setBusy(true);
    try {
      const resp = await sendToExtension<{ ok: boolean; reason?: string; status?: BirdStatus }>(
        { type: "pingcrm:connect-twitter" },
      );
      if (resp === null) {
        setShowInstallModal(true);
        return;
      }
      if (!resp.ok && resp.reason === "signed_out") {
        window.open("https://x.com/login", "_blank");
        return;
      }
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function onRefresh() {
    setBusy(true);
    try {
      const resp = await sendToExtension<{ ok: boolean; reason?: string }>(
        { type: "pingcrm:refresh-twitter-cookies" },
      );
      if (resp === null) {
        setShowInstallModal(true);
        return;
      }
      if (!resp.ok && resp.reason === "signed_out") {
        window.open("https://x.com/login", "_blank");
        return;
      }
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function onDisconnect() {
    setBusy(true);
    try {
      await (client as any).DELETE("/api/v1/integrations/twitter/cookies", {});
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 hover:shadow-sm transition-shadow">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 rounded-lg bg-stone-100 dark:bg-stone-800 flex items-center justify-center shrink-0">
              <TwitterIcon />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">
                  X (Twitter) — mentions &amp; bios
                </h3>
                {state.status === "connected" && (
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Connected
                  </span>
                )}
                {state.status === "expired" && (
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
                    <AlertTriangle className="w-3 h-3" />
                    Expired
                  </span>
                )}
              </div>
              <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
                Fetch mentions and bio changes via browser extension cookies.
              </p>
              {state.status === "connected" && state.checked_at && (
                <p className="text-xs text-teal-600 dark:text-teal-400 mt-1">
                  Last verified {new Date(state.checked_at).toLocaleString()}
                </p>
              )}
              {state.status === "expired" && (
                <p className="text-xs text-amber-700 dark:text-amber-400 mt-1">
                  X cookies expired — click Refresh to reconnect.
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {state.status === "disconnected" && (
              <button
                onClick={() => void onConnect()}
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
              >
                {busy ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Link2 className="w-3.5 h-3.5" />
                )}
                Connect X
              </button>
            )}
            {state.status === "connected" && (
              <button
                onClick={() => void onDisconnect()}
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors disabled:opacity-50"
              >
                {busy ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Unplug className="w-3.5 h-3.5" />
                )}
                Disconnect
              </button>
            )}
            {state.status === "expired" && (
              <button
                onClick={() => void onRefresh()}
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
              >
                {busy ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5" />
                )}
                Refresh
              </button>
            )}
          </div>
        </div>
      </div>

      {showInstallModal && (
        <InstallExtensionModal onClose={() => setShowInstallModal(false)} />
      )}
    </>
  );
}

function InstallExtensionModal({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white dark:bg-stone-900 rounded-xl p-6 w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
            Install the PingCRM extension
          </h3>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <p className="text-sm text-stone-600 dark:text-stone-400 mb-4">
          Connecting X requires the PingCRM browser extension. Install it, then click Connect X again.
        </p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
          >
            Close
          </button>
          <a
            href="/settings?tab=integrations"
            className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm"
          >
            View extension setup
          </a>
        </div>
      </div>
    </div>
  );
}
