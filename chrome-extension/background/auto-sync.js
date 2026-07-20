/**
 * Throttled background syncs triggered by page visits.
 *
 * These fire on ordinary browsing (opening LinkedIn, Facebook, or Instagram),
 * so every entry point is rate limited. Without the throttles a user scrolling
 * their feed would kick off a sync per navigation.
 */

// ── Throttle state for post-profile-capture Voyager sync ─────────────────────

let _lastProfileSyncAt = 0;
const PROFILE_SYNC_THROTTLE_MS = 5 * 60 * 1000; // 5 minutes

// Per-slug throttle for profile-visit capture (avoid re-fetching the same
// person every time the user reopens their profile).
const _profileVisitAt = {};
const PROFILE_VISIT_THROTTLE_MS = 10 * 60 * 1000; // 10 minutes per profile

// ── Throttle state for Meta auto-sync ────────────────────────────────────────
let _lastMetaSyncAt = 0;
const META_AUTO_SYNC_THROTTLE_MS = 5 * 60 * 1000; // 5 minutes

/**
 * @param {"facebook"|"instagram"} platform
 */
async function _maybeRunMetaSync(platform) {
  if (Date.now() - _lastMetaSyncAt < META_AUTO_SYNC_THROTTLE_MS) return;
  _lastMetaSyncAt = Date.now();

  const { apiUrl, token, metaSyncFacebook, metaSyncInstagram } = await chrome.storage.local.get([
    "apiUrl", "token", "metaSyncFacebook", "metaSyncInstagram",
  ]);
  if (!apiUrl || !token) return;

  if (platform === "facebook" && metaSyncFacebook !== false) {
    const result = await runFacebookSync(apiUrl, token, false);
    if (result.error) {
      console.warn("[SW] Auto Meta sync error (facebook):", result.error);
    }
  }

  if (platform === "instagram" && metaSyncInstagram !== false) {
    const result = await runInstagramSync(apiUrl, token, false);
    if (result.error) {
      console.warn("[SW] Auto Meta sync error (instagram):", result.error);
    }
  }
}

async function _maybeRunVoyagerSync() {
  if (Date.now() - _lastProfileSyncAt < PROFILE_SYNC_THROTTLE_MS) return;
  _lastProfileSyncAt = Date.now();

  const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);
  if (!apiUrl || !token) return;

  const result = await runSync(apiUrl, token, false);
  if (result.skipped) return;

  if (result.error) {
    console.warn("[PingCRM SW] Post-capture Voyager sync error:", result.error);
    return;
  }

  await Storage.recordSync({
    profilesSynced: result.backfilled,
    messagesSynced: result.messages,
  });

  setBadge("OK", "#4CAF50");
  setTimeout(() => setBadge("", ""), 3000);
}
