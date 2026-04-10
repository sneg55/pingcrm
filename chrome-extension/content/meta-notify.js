/**
 * Content script for Facebook and Instagram pages.
 * Notifies the service worker on page load to refresh cookies
 * and trigger a throttled Meta sync.
 *
 * Also proxies Meta GraphQL requests from the service worker.
 * Content scripts run same-origin, so cookies (c_user, xs) are
 * attached automatically — no MV3 service-worker restrictions.
 */
try {
  const platform = location.hostname.includes("instagram") ? "instagram" : "facebook";
  chrome.runtime.sendMessage({ type: "META_PAGE_VISIT", platform });
} catch (e) {
  // Extension context may not be ready yet
}

// ── Meta GraphQL proxy ──────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "META_GRAPHQL_PROXY") return false;

  const { url, options } = message;

  (async () => {
    try {
      const resp = await fetch(url, {
        ...options,
        credentials: "same-origin",
      });

      const status = resp.status;
      if (!resp.ok) {
        const body = await resp.text().catch(() => "");
        sendResponse({ ok: false, status, body: body.substring(0, 2000) });
        return;
      }

      const data = await resp.json();
      sendResponse({ ok: true, status, data });
    } catch (e) {
      sendResponse({ ok: false, status: 0, body: e.message });
    }
  })();

  return true;
});
