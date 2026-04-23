"use client";

import { useState, useEffect } from "react";
import { AlertTriangle, Check, Copy, Download, Key, Trash2 } from "lucide-react";
import { client } from "@/lib/api-client";
import { extractErrorMessage } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

// eslint-disable-next-line sonarjs/cognitive-complexity -- account tab bundles profile + password + export + delete flows; refactor tracked separately
export function AccountTab() {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMsg, setProfileMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [savingPw, setSavingPw] = useState(false);
  const [pwMsg, setPwMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // MCP API key
  const [mcpHasKey, setMcpHasKey] = useState(false);
  const [mcpKey, setMcpKey] = useState<string | null>(null);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [mcpCopied, setMcpCopied] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const result = await client.GET("/api/v1/auth/me", {});
        const user = result.data?.data;
        if (user) {
          setDisplayName(user.full_name || "");
          setEmail(user.email || "");
        }
      } catch (err) {
        console.error("load profile failed", err);
      }
      try {
        const { data } = await client.GET("/api/v1/settings/mcp-key", {});
        setMcpHasKey(!!data?.data?.has_key);
      } catch (err) {
        console.error("load mcp-key status failed", err);
      }
    })();
  }, []);

  const handleSaveProfile = async () => {
    setSavingProfile(true);
    setProfileMsg(null);
    try {
      const { error } = await client.PUT("/api/v1/auth/me", {
        body: { full_name: displayName },
      });
      if (error) {
        setProfileMsg({ type: "error", text: extractErrorMessage(error) ?? "Failed to save" });
      } else {
        setProfileMsg({ type: "success", text: "Profile updated" });
        setTimeout(() => setProfileMsg(null), 3000);
      }
    } catch {
      setProfileMsg({ type: "error", text: "Failed to save profile" });
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChangePassword = async () => {
    setPwMsg(null);
    if (newPw !== confirmPw) {
      setPwMsg({ type: "error", text: "New passwords don't match" });
      return;
    }
    if (newPw.length < 8) {
      setPwMsg({ type: "error", text: "Password must be at least 8 characters" });
      return;
    }
    setSavingPw(true);
    try {
      const { error } = await client.POST("/api/v1/auth/change-password", {
        body: { current_password: currentPw, new_password: newPw },
      });
      if (error) {
        setPwMsg({ type: "error", text: extractErrorMessage(error) ?? "Failed to change password" });
      } else {
        setPwMsg({ type: "success", text: "Password updated" });
        setCurrentPw("");
        setNewPw("");
        setConfirmPw("");
        setTimeout(() => setPwMsg(null), 3000);
      }
    } catch {
      setPwMsg({ type: "error", text: "Failed to change password" });
    } finally {
      setSavingPw(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleting(true);
    try {
      await client.DELETE("/api/v1/auth/me", {});
      localStorage.removeItem("access_token");
      window.location.href = "/auth/login";
    } catch {
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const initials = displayName
    ? displayName.split(" ").map((w: string) => w[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  return (
    <div className="space-y-6">
      {/* Profile */}
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 mb-1">Profile</h3>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-5">Your personal information.</p>

        <div className="flex items-start gap-5 mb-6">
          <div className="shrink-0">
            <div className="w-16 h-16 rounded-full bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-300 flex items-center justify-center text-xl font-bold">
              {initials}
            </div>
          </div>
          <div className="flex-1 space-y-3">
            <div>
              <label className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-1 block">Display name</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full text-sm border border-stone-200 dark:border-stone-700 rounded-lg px-3 py-2.5 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-1 block">Email</label>
              <input
                type="email"
                value={email}
                disabled
                className="w-full text-sm border border-stone-200 dark:border-stone-700 rounded-lg px-3 py-2.5 bg-stone-50 dark:bg-stone-800 text-stone-500 dark:text-stone-400 cursor-not-allowed"
              />
            </div>
          </div>
        </div>

        {profileMsg && (
          <p className={cn("text-xs mb-3", profileMsg.type === "success" ? "text-emerald-600 dark:text-emerald-400" : "text-red-500")}>
            {profileMsg.text}
          </p>
        )}

        <div className="flex justify-end pt-4 border-t border-stone-100 dark:border-stone-800">
          <button
            onClick={() => void handleSaveProfile()}
            disabled={savingProfile}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
          >
            {savingProfile ? "Saving..." : "Save profile"}
          </button>
        </div>
      </div>

      {/* Change Password */}
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 mb-1">Change Password</h3>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-5">Update your account password.</p>

        <div className="space-y-3 max-w-sm">
          <div>
            <label className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-1 block">Current password</label>
            <input type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} placeholder="Enter current password" className="w-full text-sm border border-stone-200 dark:border-stone-700 rounded-lg px-3 py-2.5 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-teal-400 placeholder:text-stone-300 dark:placeholder:text-stone-600" />
          </div>
          <div>
            <label className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-1 block">New password</label>
            <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="Enter new password" className="w-full text-sm border border-stone-200 dark:border-stone-700 rounded-lg px-3 py-2.5 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-teal-400 placeholder:text-stone-300 dark:placeholder:text-stone-600" />
          </div>
          <div>
            <label className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-1 block">Confirm new password</label>
            <input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} placeholder="Confirm new password" className="w-full text-sm border border-stone-200 dark:border-stone-700 rounded-lg px-3 py-2.5 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-teal-400 placeholder:text-stone-300 dark:placeholder:text-stone-600" />
          </div>
        </div>

        {pwMsg && (
          <p className={cn("text-xs mt-3", pwMsg.type === "success" ? "text-emerald-600 dark:text-emerald-400" : "text-red-500")}>
            {pwMsg.text}
          </p>
        )}

        <div className="flex justify-end pt-4 mt-4 border-t border-stone-100 dark:border-stone-800">
          <button
            onClick={() => void handleChangePassword()}
            disabled={savingPw || !currentPw || !newPw || !confirmPw}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
          >
            {savingPw ? "Updating..." : "Update password"}
          </button>
        </div>
      </div>

      {/* MCP Access */}
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
        <div className="flex items-center gap-2 mb-1">
          <Key className="w-4 h-4 text-teal-600 dark:text-teal-400" />
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">MCP Access</h3>
        </div>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-4">
          Connect AI clients (Claude Desktop, Cursor, VS Code) to your CRM via the Model Context Protocol.
        </p>

        {mcpKey ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 px-3 py-2 rounded-lg font-mono truncate">
                {mcpKey}
              </code>
              <button
                onClick={() => {
                  void navigator.clipboard.writeText(mcpKey);
                  setMcpCopied(true);
                  setTimeout(() => setMcpCopied(false), 2000);
                }}
                className="shrink-0 inline-flex items-center gap-1 px-3 py-2 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
              >
                {mcpCopied ? <><Check className="w-3.5 h-3.5 text-emerald-500" /> Copied</> : <><Copy className="w-3.5 h-3.5" /> Copy</>}
              </button>
            </div>
            <p className="text-xs text-amber-600 dark:text-amber-400">
              This key is shown only once. Copy it now and store it securely.
            </p>
          </div>
        ) : (
          <div className="flex items-center justify-between p-4 border border-stone-200 dark:border-stone-700 rounded-lg">
            <div>
              <p className="text-sm font-medium text-stone-700 dark:text-stone-300">
                {mcpHasKey ? "API key active" : "No API key"}
              </p>
              <p className="text-xs text-stone-400 dark:text-stone-500">
                {mcpHasKey ? "Revoke to generate a new one" : "Generate a key to connect AI clients"}
              </p>
            </div>
            <div className="flex gap-2">
              {mcpHasKey && (
                <button
                  onClick={() => { void (async () => {
                    setMcpLoading(true);
                    try {
                      await client.DELETE("/api/v1/settings/mcp-key", {});
                      setMcpHasKey(false);
                      setMcpKey(null);
                    } catch (err) {
                      console.error("revoke mcp-key failed", err);
                    } finally { setMcpLoading(false); }
                  })(); }}
                  disabled={mcpLoading}
                  className="inline-flex items-center gap-1 px-3 py-2 text-xs font-medium rounded-lg border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors disabled:opacity-50"
                >
                  Revoke
                </button>
              )}
              <button
                onClick={() => { void (async () => {
                  setMcpLoading(true);
                  try {
                    const { data } = await client.POST("/api/v1/settings/mcp-key", {});
                    const key = data?.data?.key;
                    if (key) {
                      setMcpKey(key);
                      setMcpHasKey(true);
                    }
                  } catch (err) {
                    console.error("generate mcp-key failed", err);
                  } finally { setMcpLoading(false); }
                })(); }}
                disabled={mcpLoading}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
              >
                <Key className="w-3.5 h-3.5" />
                {mcpLoading ? "..." : mcpHasKey ? "Regenerate" : "Generate key"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Danger Zone */}
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-red-200 dark:border-red-800 p-5">
        <div className="flex items-center gap-2 mb-1">
          <AlertTriangle className="w-4 h-4 text-red-500" />
          <h3 className="text-sm font-semibold text-red-700 dark:text-red-400">Danger Zone</h3>
        </div>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-5">Irreversible actions. Proceed with caution.</p>

        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 border border-stone-200 dark:border-stone-700 rounded-lg">
            <div>
              <p className="text-sm font-medium text-stone-700 dark:text-stone-300">Export all data</p>
              <p className="text-xs text-stone-400 dark:text-stone-500">Download all your contacts, interactions, and notes</p>
            </div>
            <button
              // eslint-disable-next-line no-alert -- placeholder before bespoke UI; coming-soon notice
              onClick={() => alert("Data export is coming soon.")}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> Export
            </button>
          </div>
          <div className="flex items-center justify-between p-4 border border-red-200 dark:border-red-800 rounded-lg bg-red-50/50 dark:bg-red-950/50">
            <div>
              <p className="text-sm font-medium text-red-700 dark:text-red-400">Delete account</p>
              <p className="text-xs text-red-500/80 dark:text-red-400/80">Permanently delete your account and all data. This cannot be undone.</p>
            </div>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" /> Delete account
            </button>
          </div>
        </div>
      </div>

      {/* Delete confirmation */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" role="dialog" aria-modal="true">
          <div className="bg-white dark:bg-stone-900 rounded-xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-50 dark:bg-red-950 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-stone-900 dark:text-stone-100">Delete your account?</h3>
                <p className="text-sm text-stone-500 dark:text-stone-400">This cannot be undone.</p>
              </div>
            </div>
            <p className="text-sm text-stone-600 dark:text-stone-300 mb-5">
              All your contacts, interactions, suggestions, and connected accounts will be permanently deleted.
            </p>
            <div className="flex gap-2">
              <button onClick={() => setShowDeleteConfirm(false)} className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800">Cancel</button>
              <button onClick={() => void handleDeleteAccount()} disabled={deleting} className="flex-1 px-3 py-2 text-sm rounded-lg bg-red-600 text-white font-medium hover:bg-red-700 disabled:opacity-50">
                {deleting ? "Deleting..." : "Delete everything"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
