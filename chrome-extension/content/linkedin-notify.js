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

// ── Profile capture ──────────────────────────────────────────────────────────
// On a member profile page (/in/<slug>), ask the service worker to fetch and
// enrich that contact via Voyager. LinkedIn is an SPA — navigating between
// profiles doesn't reload this content script — so poll the URL and fire once
// per distinct slug. The SW additionally throttles per slug.
const _capturedSlugs = new Set();

function _currentProfileSlug() {
  const m = window.location.pathname.match(/^\/in\/([^/?#]+)/);
  if (!m) return null;
  const slug = decodeURIComponent(m[1]);
  // Anonymized member URNs (ACo…) aren't accepted by the profile endpoint.
  if (/^aco/i.test(slug)) return null;
  return slug;
}

function _maybeCaptureProfile() {
  const slug = _currentProfileSlug();
  if (!slug || _capturedSlugs.has(slug)) return;
  _capturedSlugs.add(slug);
  try {
    chrome.runtime.sendMessage({ type: "PROFILE_VISIT", slug });
  } catch (e) {
    // Extension context not ready — allow a later retry for this slug.
    _capturedSlugs.delete(slug);
  }
}

_maybeCaptureProfile();
setInterval(_maybeCaptureProfile, 3000);

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
