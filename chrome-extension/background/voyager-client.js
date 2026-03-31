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

  // Execute fetch inside the LinkedIn tab (same-origin → cookies included)
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    // This function runs in the LinkedIn page context
    func: async (url, method, csrfToken, accept, serializedBody) => {
      try {
        const headers = {
          "Csrf-Token": csrfToken,
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
    args: [urlStr, method, csrfToken, accept, serializedBody],
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
