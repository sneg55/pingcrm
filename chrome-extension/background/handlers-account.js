/**
 * Pairing, disconnect, and Twitter cookie handlers.
 *
 * Each takes (message, sendResponse) and always calls sendResponse exactly once.
 */

/** START_PAIRING — generate code, start polling, return code to popup. */
async function handleStartPairing(message, sendResponse) {
  const apiUrl = (message.apiUrl || "").replace(/\/+$/, "");
  if (!apiUrl) {
    sendResponse({ ok: false, error: "Instance URL is required" });
    return;
  }

  // Save the apiUrl so pairing.js polling can read it
  await chrome.storage.local.set({ apiUrl });

  const { code } = startPairing();
  sendResponse({ ok: true, code });
}

/** DISCONNECT — clear storage and notify backend. */
async function handleDisconnect(_message, sendResponse) {
  stopPolling();

  const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);

  // Best-effort DELETE — do not block on response
  if (apiUrl && token) {
    apiFetch(`${apiUrl}/api/v1/extension/pair`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(e => console.debug("[PingCRM SW] Disconnect notify failed:", e.message));
  }

  await chrome.storage.local.clear();
  setBadge("", "");
  sendResponse({ ok: true });
}

/** CONNECT_TWITTER / REFRESH_TWITTER_COOKIES — push x.com cookies to backend. */
async function handleTwitterCookies(_message, sendResponse) {
  try {
    const result = await connectTwitter();
    sendResponse(result);
  } catch (e) {
    console.warn("[SW] Twitter cookie push error:", e.message);
    sendResponse({ ok: false, reason: e.message });
  }
}
