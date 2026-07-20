/**
 * Timeout-bounded fetch for every call to the user's PingCRM instance.
 *
 * Why this exists: a fetch with no timeout can hang indefinitely. Chrome allows
 * only ~6 concurrent connections per host, so a handful of hung background
 * requests starve every other request to that origin — including the PingCRM
 * tab's own API calls, which is user-visible as a dashboard that renders zeros
 * because its requests never leave the browser.
 *
 * pairing.js hit this first and fixed its own poll inline. Every other call to
 * ${apiUrl} had the same defect, so the guard lives here rather than being
 * re-applied by hand at each new call site.
 *
 * Loaded via importScripts() before any module that calls it, so `apiFetch` is
 * a global by the time the sync/push paths run.
 */

// Long enough for a slow push of a sync batch, short enough that a wedged
// connection is released well before it can starve the tab.
const API_FETCH_TIMEOUT_MS = 30 * 1000;

/**
 * fetch() against the PingCRM API with an abort timeout applied.
 *
 * Rejects like fetch() does. A timeout surfaces as a TimeoutError DOMException,
 * so callers that already handle network rejection need no change.
 *
 * @param {string} url                  absolute URL to the PingCRM instance
 * @param {RequestInit} [options]       standard fetch options
 * @param {number} [timeoutMs]          override the default timeout
 * @returns {Promise<Response>}
 */
function apiFetch(url, options = {}, timeoutMs = API_FETCH_TIMEOUT_MS) {
  // Respect an explicit caller signal rather than silently replacing it.
  const signal = options.signal ?? AbortSignal.timeout(timeoutMs);
  return fetch(url, { ...options, signal });
}
