/**
 * LinkedIn Voyager API client for Chrome extension service worker.
 *
 * Voyager requests are executed inside a LinkedIn tab via
 * chrome.scripting.executeScript — the only reliable way to include
 * cookies in MV3.  Service-worker fetch() silently strips the Cookie
 * header (even with host_permissions), causing "CSRF check failed."
 */

const VOYAGER_BASE = "https://www.linkedin.com/voyager/api";
// eslint-disable-next-line no-unused-vars
const VOYAGER_SCHEMA_VERSION = "2026-03-v1";

function _encodeUrn(urn) {
  return encodeURIComponent(urn);
}

/**
 * Find a LinkedIn tab to execute requests in.
 * @returns {Promise<number>} Tab ID
 * @throws {Error} "NO_LINKEDIN_TAB" if none found
 */
async function _requireLinkedInTab() {
  const tabs = await chrome.tabs.query({ url: "https://www.linkedin.com/*" });
  const tabId = tabs.find(t => t.active)?.id ?? tabs[0]?.id;
  if (!tabId) throw new Error("NO_LINKEDIN_TAB");
  return tabId;
}

/**
 * Core fetch wrapper for Voyager endpoints.
 *
 * Executes the fetch inside a LinkedIn tab so cookies are attached
 * automatically by the browser (same-origin context).
 *
 * @param {string} path - API path, e.g. "/messaging/conversations"
 * @param {string} _liAt - Unused (cookies come from the page context)
 * @param {string} jsessionid - JSESSIONID value for the Csrf-Token header
 * @param {Object} [params] - Query string parameters
 * @returns {Promise<Object>} Parsed JSON response
 */
async function voyagerFetch(path, _liAt, jsessionid, params = {}, { graphql = false, method = "GET", body = null } = {}) {
  let urlStr = VOYAGER_BASE + path;
  const paramParts = Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${String(v)}`);
  if (paramParts.length > 0) {
    urlStr += "?" + paramParts.join("&");
  }

  const csrfToken = jsessionid.replace(/"/g, "");
  const accept = graphql
    ? "application/graphql"
    : "application/vnd.linkedin.normalized+json+2.1";
  const serializedBody = body
    ? (typeof body === "string" ? body : JSON.stringify(body))
    : null;

  const tabId = await _requireLinkedInTab();

  // Execute fetch inside the LinkedIn tab (same-origin → cookies included).
  // Read the CSRF token from document.cookie inside the page context so it
  // matches exactly what the browser sends — chrome.cookies.getAll() may
  // return a different JSESSIONID (multiple cookies, different paths).
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (url, method, accept, serializedBody) => {
      try {
        // Extract JSESSIONID from the page's own cookies
        const cookieStr = document.cookie;
        const jsMatch = cookieStr.match(/JSESSIONID="?([^";]+)"?/);
        const csrf = jsMatch ? jsMatch[1] : "";
        if (!csrf) return { ok: false, status: 0, body: "NO_JSESSIONID_IN_PAGE_COOKIES" };

        const headers = {
          "Csrf-Token": csrf,
          "X-Restli-Protocol-Version": "2.0.0",
          "Accept": accept,
        };
        const opts = { method, headers, credentials: "same-origin" };
        if (serializedBody) {
          opts.body = serializedBody;
          headers["Content-Type"] = "application/json; charset=UTF-8";
        }
        const resp = await fetch(url, opts);
        if (!resp.ok) {
          const text = await resp.text().catch(() => "");
          return { ok: false, status: resp.status, body: text.substring(0, 1000) };
        }
        return { ok: true, status: resp.status, data: await resp.json() };
      } catch (e) {
        return { ok: false, status: 0, body: e.message };
      }
    },
    args: [urlStr, method, accept, serializedBody],
    world: "MAIN",
  });

  const result = results?.[0]?.result;
  if (!result) throw new Error("SCRIPT_EXEC_FAILED");

  if (result.status === 429) {
    const error = new Error("RATE_LIMITED");
    error.retryAfter = 900;
    throw error;
  }
  if (result.status === 401 || result.status === 403) {
    console.error(`[Voyager] AUTH ${result.status} ${method} ${path}: ${result.body}`);
    throw new Error("AUTH_EXPIRED");
  }
  if (!result.ok) {
    console.error(`[Voyager] ${result.status} ${method} ${path}: ${result.body}`);
    throw new Error(`VOYAGER_ERROR:${result.status}`);
  }

  return result.data;
}

// ── Public API (unchanged signatures for call-site compat) ───────────────────

async function voyagerGetSelfUrn(liAt, jsessionid) {
  const data = await voyagerFetch("/me", liAt, jsessionid);
  const miniProfile = data?.included?.find(i => i?.$type?.includes("MiniProfile"))
    ?? data?.data ?? data;
  let urn = miniProfile?.entityUrn
    ?? miniProfile?.["*profile"]
    ?? "";

  if (urn.includes("fs_miniProfile")) {
    urn = urn.replace("fs_miniProfile", "fsd_profile");
  }
  if (!urn || !urn.includes("fsd_profile")) {
    const memberId = urn.split(":").pop() || miniProfile?.publicIdentifier || "";
    urn = `urn:li:fsd_profile:${memberId}`;
  }
  return urn;
}

async function voyagerGetConversations(liAt, jsessionid, mailboxUrn, lastUpdatedBefore = null) {
  const queryId = "messengerConversations.0d5e6781bbee71c3e51c8843c6519f48";
  const variablesParts = [`mailboxUrn:${_encodeUrn(mailboxUrn)}`];
  if (lastUpdatedBefore != null) {
    variablesParts.push(`lastUpdatedBefore:${lastUpdatedBefore}`);
  }
  const variables = `(${variablesParts.join(",")})`;
  return voyagerFetch("/voyagerMessagingGraphQL/graphql", liAt, jsessionid,
    { queryId, variables },
    { graphql: true },
  );
}

async function voyagerGetConversationMessages(liAt, jsessionid, conversationUrn) {
  const queryId = "messengerMessages.5846eeb71c981f11e0134cb6626cc314";
  const variables = `(conversationUrn:${_encodeUrn(conversationUrn)})`;
  return voyagerFetch("/voyagerMessagingGraphQL/graphql", liAt, jsessionid,
    { queryId, variables },
    { graphql: true },
  );
}

async function voyagerGetProfile(liAt, jsessionid, publicId) {
  return voyagerFetch("/identity/dash/profiles", liAt, jsessionid, {
    q: "memberIdentity",
    memberIdentity: publicId,
    decorationId: "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-91",
  });
}

// Server-side fetches against media.licdn.com return 403 — the CDN requires
// a real browser context. Run the fetch inside a LinkedIn tab so the browser
// supplies cookies/referer, then ship the bytes back as a base64 data URI.
const AVATAR_MAX_BYTES = 5_000_000; // matches backend cap in _save_avatar

async function fetchLinkedInImageAsBase64(url) {
  if (!url) return null;
  const tabId = await _requireLinkedInTab();
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (imgUrl, maxBytes) => {
      // Try 1: credentialed fetch (works when CDN returns ACAO; preferred
      // because we get the original JPEG bytes without re-encoding).
      try {
        const resp = await fetch(imgUrl, { credentials: "include" });
        if (resp.ok) {
          const blob = await resp.blob();
          if (blob.size > maxBytes) return { ok: false, body: "TOO_LARGE" };
          const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.onerror = () => reject(new Error("FileReader error"));
            reader.readAsDataURL(blob);
          });
          return { ok: true, dataUrl, via: "fetch" };
        }
      } catch (_e) {
        // CORS or network — fall through to canvas
      }

      // Try 2: load via <img crossOrigin="anonymous"> and read pixels via
      // canvas. media.licdn.com does send ACAO for image requests, so the
      // canvas stays untainted and toDataURL succeeds.
      try {
        const img = new Image();
        img.crossOrigin = "anonymous";
        const loaded = new Promise((resolve, reject) => {
          img.onload = () => resolve();
          img.onerror = () => reject(new Error("img load failed"));
          setTimeout(() => reject(new Error("img load timeout")), 8000);
        });
        img.src = imgUrl;
        await loaded;
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth || 400;
        canvas.height = img.naturalHeight || 400;
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
        if (!dataUrl || dataUrl.length < 100) return { ok: false, body: "EMPTY_CANVAS" };
        if (dataUrl.length > maxBytes * 1.4) return { ok: false, body: "TOO_LARGE" };
        return { ok: true, dataUrl, via: "canvas" };
      } catch (e) {
        return { ok: false, body: e.message };
      }
    },
    args: [url, AVATAR_MAX_BYTES],
    world: "MAIN",
  });
  const result = results?.[0]?.result;
  if (!result?.ok || !result.dataUrl) return null;
  return result.dataUrl;
}
