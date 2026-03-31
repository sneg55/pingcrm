/**
 * Minimal content script for LinkedIn pages.
 * Notifies the service worker on every LinkedIn page load
 * so it can refresh cookies and trigger a throttled sync.
 *
 * Also proxies Voyager API requests from the service worker.
 * Content scripts run same-origin on linkedin.com, so cookies
 * (li_at, JSESSIONID) are attached automatically — no explicit
 * Cookie headers needed and no MV3 service-worker restrictions.
 */
try {
  chrome.runtime.sendMessage({ type: "LINKEDIN_PAGE_VISIT" });
} catch (e) {
  // Extension context may not be ready yet
}

// ── Voyager proxy ────────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "VOYAGER_PROXY") return false;

  const { url, options } = message;

  (async () => {
    try {
      const resp = await fetch(url, {
        ...options,
        credentials: "same-origin", // same-origin on linkedin.com = cookies included
      });

      const status = resp.status;
      if (!resp.ok) {
        const body = await resp.text().catch(() => "");
        sendResponse({ ok: false, status, body: body.substring(0, 1000) });
        return;
      }

      const data = await resp.json();
      sendResponse({ ok: true, status, data });
    } catch (e) {
      sendResponse({ ok: false, status: 0, body: e.message });
    }
  })();

  return true; // keep sendResponse channel open for async
});
