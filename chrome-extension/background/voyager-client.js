/**
 * LinkedIn Voyager API client for Chrome extension service worker.
 * All calls happen from the user's browser — cookies never leave.
 */

const VOYAGER_BASE = "https://www.linkedin.com/voyager/api";
// Reserved for future schema-version negotiation with LinkedIn's API versioning.
// eslint-disable-next-line no-unused-vars
const VOYAGER_SCHEMA_VERSION = "2026-03-v1";

// Build Voyager request headers.  Cookies are attached automatically via
// credentials:"include" (works in Chrome 116+ with host_permissions).
// We still need the JSESSIONID value for the Csrf-Token header.
function _voyagerHeaders(jsessionid, { graphql = false } = {}) {
  return {
    "Csrf-Token": jsessionid.replace(/"/g, ""),
    "X-Restli-Protocol-Version": "2.0.0",
    "Accept": graphql ? "application/graphql" : "application/vnd.linkedin.normalized+json+2.1",
  };
}

function _encodeUrn(urn) {
  return encodeURIComponent(urn);
}

/**
 * Find an active LinkedIn tab to proxy requests through.
 * Returns the tab ID or null if no LinkedIn tab is open.
 */
async function _findLinkedInTab() {
  const tabs = await chrome.tabs.query({ url: "https://www.linkedin.com/*" });
  // Prefer active/visible tabs, fall back to any LinkedIn tab
  return tabs.find(t => t.active)?.id ?? tabs[0]?.id ?? null;
}

/**
 * Core fetch wrapper for Voyager endpoints.
 *
 * Routes requests through a LinkedIn content script (same-origin) so
 * cookies are included automatically.  MV3 service workers cannot
 * reliably set Cookie headers or use credentials:"include" cross-origin.
 *
 * @param {string} path - API path, e.g. "/messaging/conversations"
 * @param {string} liAt - (unused, kept for call-site compat)
 * @param {string} jsessionid - Value of the JSESSIONID cookie (CSRF token)
 * @param {Object} [params] - Query string parameters
 * @returns {Promise<Object>} Parsed JSON response
 * @throws {Error} "RATE_LIMITED" (with .retryAfter), "AUTH_EXPIRED", or "VOYAGER_ERROR:<status>"
 */
async function voyagerFetch(path, liAt, jsessionid, params = {}, { graphql = false, method = "GET", body = null } = {}) {
  // Build URL manually to avoid double-encoding of pre-encoded values
  // (LinkedIn's variables format uses pre-encoded URNs)
  let urlStr = VOYAGER_BASE + path;
  const paramParts = Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${String(v)}`);
  if (paramParts.length > 0) {
    urlStr += "?" + paramParts.join("&");
  }

  const headers = _voyagerHeaders(jsessionid, { graphql });
  if (body) {
    headers["Content-Type"] = "application/json; charset=UTF-8";
  }

  // Route through LinkedIn tab's content script (same-origin = cookies work)
  const tabId = await _findLinkedInTab();
  if (!tabId) {
    throw new Error("NO_LINKEDIN_TAB");
  }

  const proxyResult = await chrome.tabs.sendMessage(tabId, {
    type: "VOYAGER_PROXY",
    url: urlStr,
    options: {
      method,
      headers,
      body: body ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
    },
  });

  if (!proxyResult) {
    throw new Error("PROXY_NO_RESPONSE");
  }

  const { status } = proxyResult;

  if (status === 429) {
    const error = new Error("RATE_LIMITED");
    error.retryAfter = 900;
    throw error;
  }
  if (status === 401 || status === 403) throw new Error("AUTH_EXPIRED");
  if (!proxyResult.ok) {
    console.error(`[Voyager] ${status} ${method} ${urlStr}`);
    console.error(`[Voyager] Response: ${(proxyResult.body || "").substring(0, 500)}`);
    throw new Error(`VOYAGER_ERROR:${status}`);
  }

  return proxyResult.data;
}

/**
 * Fetch conversation list via the Dash messaging endpoint.
 * LinkedIn migrated from REST /messaging/conversations (now returns 500)
 * to /voyagerMessagingDashMessengerConversations (2025+).
 *
 * @param {string} liAt
 * @param {string} jsessionid
 * @param {number} [count=20] - Number of conversations to fetch
 * @param {number|null} [lastUpdatedBefore] - Unix ms timestamp for pagination
 * @returns {Promise<Object>} Normalized Voyager response
 */
/**
 * Fetch the authenticated user's profile URN (needed for conversation list).
 * @returns {Promise<string>} e.g. "urn:li:fsd_profile:ACoAAB..."
 */
async function voyagerGetSelfUrn(liAt, jsessionid) {
  const data = await voyagerFetch("/me", liAt, jsessionid);
  // The /me response returns fs_miniProfile URN but GraphQL needs fsd_profile.
  // Extract the member ID (ACoAAA...) and construct the correct URN type.
  const miniProfile = data?.included?.find(i => i?.$type?.includes("MiniProfile"))
    ?? data?.data ?? data;
  let urn = miniProfile?.entityUrn
    ?? miniProfile?.["*profile"]
    ?? "";

  // Convert fs_miniProfile → fsd_profile (GraphQL requires fsd_profile)
  if (urn.includes("fs_miniProfile")) {
    urn = urn.replace("fs_miniProfile", "fsd_profile");
  }

  // Fallback: construct from plainId
  if (!urn || !urn.includes("fsd_profile")) {
    const memberId = urn.split(":").pop() || miniProfile?.publicIdentifier || "";
    urn = `urn:li:fsd_profile:${memberId}`;
  }

  return urn;
}

/**
 * Fetch conversation list via GraphQL (March 2026+).
 * Uses messengerConversations queryId with mailboxUrn variable.
 * Source: github.com/eracle/OpenOutreach
 *
 * @param {string} liAt
 * @param {string} jsessionid
 * @param {string} mailboxUrn - The authenticated user's profile URN
 * @param {number|null} [lastUpdatedBefore=null] - Unix ms timestamp cursor for pagination;
 *   when provided, fetches conversations last-updated before this timestamp.
 * @returns {Promise<Object>} GraphQL response with conversations
 */
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

/**
 * Fetch messages for a specific conversation via GraphQL.
 * Uses messengerMessages queryId with conversationUrn variable.
 *
 * @param {string} liAt
 * @param {string} jsessionid
 * @param {string} conversationUrn - Conversation URN
 * @returns {Promise<Object>} GraphQL response with messages
 */
async function voyagerGetConversationMessages(liAt, jsessionid, conversationUrn) {
  const queryId = "messengerMessages.5846eeb71c981f11e0134cb6626cc314";
  const variables = `(conversationUrn:${_encodeUrn(conversationUrn)})`;
  return voyagerFetch("/voyagerMessagingGraphQL/graphql", liAt, jsessionid,
    { queryId, variables },
    { graphql: true },
  );
}

/**
 * Fetch a LinkedIn profile by public identifier (slug).
 *
 * @param {string} liAt
 * @param {string} jsessionid
 * @param {string} publicId - LinkedIn public profile slug, e.g. "john-doe-123"
 * @returns {Promise<Object>} Normalized Voyager response
 */
async function voyagerGetProfile(liAt, jsessionid, publicId) {
  return voyagerFetch("/identity/dash/profiles", liAt, jsessionid, {
    q: "memberIdentity",
    memberIdentity: publicId,
    decorationId: "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-91",
  });
}
