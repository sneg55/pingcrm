/**
 * TTL cache over the backend's /api/v1/suggestions list.
 *
 * The LinkedIn content script asks for a suggestion on every thread open, so
 * this avoids a round trip per message view. Invalidated explicitly whenever a
 * suggestion is regenerated.
 */

let _suggestionCache = null;
let _suggestionCacheTimestamp = 0;
const SUGGESTION_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

/**
 * @param {string} token   bearer token for the paired instance
 * @param {string} apiUrl  PingCRM instance URL
 * @returns {Promise<object[]>} suggestions, or the stale cache on failure
 */
async function _getSuggestions(token, apiUrl) {
  const now = Date.now();
  if (_suggestionCache && (now - _suggestionCacheTimestamp) < SUGGESTION_CACHE_TTL_MS) {
    return _suggestionCache;
  }
  const resp = await apiFetch(`${apiUrl}/api/v1/suggestions`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) return _suggestionCache || [];
  const json = await resp.json();
  _suggestionCache = json?.data ?? [];
  _suggestionCacheTimestamp = now;
  return _suggestionCache;
}

function _invalidateSuggestionCache() {
  _suggestionCache = null;
  _suggestionCacheTimestamp = 0;
}
