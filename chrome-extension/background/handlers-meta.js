/**
 * Facebook / Instagram message handlers.
 *
 * Each takes (message, sendResponse) and always calls sendResponse exactly once.
 */

/** META_PAGE_VISIT — user visited Facebook or Instagram. */
async function handleMetaPageVisit(message, sendResponse) {
  try {
    const cookies = await chrome.cookies.getAll({ domain: ".facebook.com" });
    const cUser = cookies.find(c => c.name === "c_user")?.value;
    const xs = cookies.find(c => c.name === "xs")?.value;
    const valid = !!(cUser && xs);
    await chrome.storage.local.set({ metaCookiesValid: valid });
    console.log("[SW] Meta cookie refresh:", valid ? "valid" : "missing");

    if (valid) {
      _maybeRunMetaSync(message.platform).catch(e =>
        console.warn("[SW] Auto Meta sync failed:", e.message)
      );
    }
  } catch (e) {
    console.warn("[SW] Meta cookie refresh failed:", e.message);
  }
  sendResponse({ ok: true });
}

/** META_SYNC_NOW — force Meta sync (from popup or frontend). */
async function handleMetaSyncNow(message, sendResponse) {
  try {
    const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);
    if (!apiUrl || !token) {
      sendResponse({ ok: false, error: "Not paired" });
      return;
    }

    setBadge("...", "#64748b");
    const platform = message.platform || "both";

    let fbResult = { skipped: true, conversations: 0, messages: 0 };
    let igResult = { skipped: true, conversations: 0, messages: 0 };

    if (platform === "facebook" || platform === "both") {
      fbResult = await runFacebookSync(apiUrl, token, true);
      if (fbResult.error) {
        setBadge("X", "#FF9800");
        sendResponse({ ok: false, error: fbResult.error, platform: "facebook" });
        return;
      }
    }

    if (platform === "instagram" || platform === "both") {
      igResult = await runInstagramSync(apiUrl, token, true);
      if (igResult.error) {
        setBadge("X", "#FF9800");
        sendResponse({ ok: false, error: igResult.error, platform: "instagram" });
        return;
      }
    }

    setBadge("OK", "#4CAF50");
    setTimeout(() => setBadge("", ""), 3000);

    sendResponse({
      ok: true,
      facebook: {
        conversations: fbResult.conversations,
        messages: fbResult.messages,
      },
      instagram: {
        conversations: igResult.conversations,
        messages: igResult.messages,
      },
    });
  } catch (e) {
    console.error("[SW] META_SYNC_NOW crashed:", e.message, e.stack);
    setBadge("X", "#FF9800");
    sendResponse({ ok: false, error: e.message });
  }
}
