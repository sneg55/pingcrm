/**
 * Service worker for PingCRM LinkedIn Companion v2.
 * Message router — delegates to imported modules.
 *
 * importScripts loads modules synchronously at service worker startup.
 * Each module exposes its public functions as globals (no ES module syntax).
 *
 * Handlers live in handlers-*.js. This file owns only the dispatch table, so
 * adding a message type means adding a handler and one row below.
 */

importScripts(
  "../lib/storage.js",
  "api-fetch.js",
  "voyager-client.js",
  "sync-utils.js",
  "sync.js",
  "pairing.js",
  "meta-client.js",
  "meta-sync-utils.js",
  "sync-facebook.js",
  "sync-instagram.js",
  "twitter-sync.js",
  "badge.js",
  "suggestion-cache.js",
  "auto-sync.js",
  "backfill.js",
  "handlers-linkedin.js",
  "handlers-suggestions.js",
  "handlers-meta.js",
  "handlers-account.js"
);

// Start Twitter cookie watcher immediately after all modules are loaded.
initTwitterCookieWatcher();

// ── Message router ────────────────────────────────────────────────────────────

/**
 * message.type -> async (message, sendResponse) => void
 *
 * Every handler resolves by calling sendResponse exactly once, so the listener
 * can uniformly return true and keep the message port open.
 */
const MESSAGE_HANDLERS = {
  LINKEDIN_PAGE_VISIT: handleLinkedInPageVisit,
  PROFILE_VISIT: handleProfileVisit,
  SYNC_NOW: handleSyncNow,
  START_PAIRING: handleStartPairing,
  DISCONNECT: handleDisconnect,
  GET_SUGGESTION: handleGetSuggestion,
  REGENERATE_SUGGESTION: handleRegenerateSuggestion,
  META_PAGE_VISIT: handleMetaPageVisit,
  META_SYNC_NOW: handleMetaSyncNow,
  "pingcrm:connect-twitter": handleTwitterCookies,
  "pingcrm:refresh-twitter-cookies": handleTwitterCookies,
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handler = MESSAGE_HANDLERS[message?.type];
  if (!handler) return false;

  // A handler that throws before responding would otherwise leave the sender
  // hanging until the port closes with no reply.
  handler(message, sendResponse).catch((e) => {
    console.error("[SW] Handler crashed:", message.type, e.message, e.stack);
    sendResponse({ ok: false, error: e.message });
  });
  return true;
});

// ── Startup ───────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  const manifest = chrome.runtime.getManifest();
  console.log(`[PingCRM] LinkedIn Companion v${manifest.version} installed`);
});
