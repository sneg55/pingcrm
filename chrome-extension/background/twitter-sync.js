/**
 * Per-user Twitter/X bird cookie sync.
 * Reads auth_token and ct0 from x.com cookies, pushes them to the PingCRM
 * backend. Listens for cookie rotation and silently re-pushes on change.
 *
 * Loaded via importScripts — all public functions are globals.
 * Auth is read from chrome.storage.local keys: apiUrl, token.
 */

// ── Internal helpers ──────────────────────────────────────────────────────────

const _TWITTER_URL = 'https://x.com';
const _TWITTER_COOKIE_NAMES = ['auth_token', 'ct0'];
let _twitterPushDebounceTimer = null;

async function _readTwitterCookies() {
  const results = await Promise.all(
    _TWITTER_COOKIE_NAMES.map((name) =>
      chrome.cookies.get({ url: _TWITTER_URL, name }),
    ),
  );
  const [authTokenCookie, ct0Cookie] = results;
  if (!authTokenCookie || !ct0Cookie) {
    return null;
  }
  return { auth_token: authTokenCookie.value, ct0: ct0Cookie.value };
}

async function _pushTwitterCookies(cookies) {
  const { apiUrl, token } = await chrome.storage.local.get(['apiUrl', 'token']);
  if (!apiUrl || !token) {
    return { ok: false, reason: 'not_paired' };
  }
  try {
    const resp = await fetch(`${apiUrl}/api/v1/integrations/twitter/cookies`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(cookies),
    });
    if (!resp.ok) {
      console.warn('[pingcrm] twitter cookie push failed, status:', resp.status);
      await chrome.storage.local.set({ twitterCookiesValid: false });
      return { ok: false, reason: `http_${resp.status}` };
    }
    const json = await resp.json();
    const status = json.data?.status;
    await chrome.storage.local.set({
      twitterCookiesValid: status === 'connected',
      twitterStatus: status || 'disconnected',
      lastTwitterSync: new Date().toISOString(),
    });
    return { ok: true, status };
  } catch (err) {
    console.warn('[pingcrm] twitter cookie push failed', err);
    return { ok: false, reason: 'network' };
  }
}

function _scheduleTwitterRefresh() {
  if (_twitterPushDebounceTimer) clearTimeout(_twitterPushDebounceTimer);
  _twitterPushDebounceTimer = setTimeout(async () => {
    _twitterPushDebounceTimer = null;
    const cookies = await _readTwitterCookies();
    if (cookies) await _pushTwitterCookies(cookies);
  }, 2000);
}

// ── Public API (globals for importScripts consumers) ─────────────────────────

/**
 * Read x.com cookies and push them to the PingCRM backend.
 * Returns { ok, status } on success or { ok: false, reason } on failure.
 */
async function connectTwitter() {
  const cookies = await _readTwitterCookies();
  if (!cookies) {
    await chrome.storage.local.set({
      twitterCookiesValid: false,
      twitterStatus: 'disconnected',
    });
    return { ok: false, reason: 'signed_out' };
  }
  return await _pushTwitterCookies(cookies);
}

/**
 * Register a chrome.cookies.onChanged listener that re-pushes cookies to the
 * backend whenever auth_token or ct0 rotates on x.com / twitter.com.
 * Call once at service-worker startup.
 */
function initTwitterCookieWatcher() {
  chrome.cookies.onChanged.addListener((changeInfo) => {
    const { cookie, removed } = changeInfo;
    if (!cookie) return;
    if (!cookie.domain.endsWith('x.com') && !cookie.domain.endsWith('twitter.com')) return;
    if (!_TWITTER_COOKIE_NAMES.includes(cookie.name)) return;
    if (removed) return;
    _scheduleTwitterRefresh();
  });
}
