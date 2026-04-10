/**
 * Meta GraphQL API client for Chrome extension service worker.
 *
 * Executes GraphQL requests inside Facebook/Instagram tabs via
 * chrome.scripting.executeScript — required for MV3 cookie access.
 * Extracts fb_dtsg CSRF token from page context.
 */

const META_GRAPHQL_URL = "https://www.facebook.com/api/graphql/";

/**
 * Find a Facebook or Instagram tab to execute requests in.
 * @param {"facebook"|"instagram"} platform
 * @returns {Promise<number>} Tab ID
 * @throws {Error} "NO_META_TAB" if none found
 */
async function _requireMetaTab(platform) {
  const patterns = platform === "instagram"
    ? ["https://www.instagram.com/*", "https://instagram.com/*"]
    : ["https://www.facebook.com/*", "https://facebook.com/*", "https://web.facebook.com/*"];
  let tabs = [];
  for (const pattern of patterns) {
    tabs = await chrome.tabs.query({ url: pattern });
    if (tabs.length > 0) break;
  }
  const tabId = tabs.find(t => t.active)?.id ?? tabs[0]?.id;
  if (!tabId) throw new Error("NO_META_TAB");
  return tabId;
}

/**
 * Execute a Meta GraphQL query inside a Facebook/Instagram tab.
 *
 * @param {string} docId - GraphQL doc_id (query hash)
 * @param {Object} variables - Query variables
 * @param {"facebook"|"instagram"} platform - Which tab to use
 * @returns {Promise<Object>} Parsed JSON response
 */
async function metaGraphQL(docId, variables, platform = "facebook") {
  const tabId = await _requireMetaTab(platform);

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (graphqlUrl, docId, variablesJson) => {
      try {
        // Extract fb_dtsg from page — it's in a hidden input or __comet_req config
        let fbDtsg = "";

        // Method 1: hidden input (most reliable)
        const dtsgInput = document.querySelector('input[name="fb_dtsg"]');
        if (dtsgInput) {
          fbDtsg = dtsgInput.value;
        }

        // Method 2: __comet_req script data
        if (!fbDtsg) {
          const scripts = document.querySelectorAll("script");
          for (const s of scripts) {
            const text = s.textContent || "";
            const match = text.match(/"DTSGInitialData"[^}]*"token":"([^"]+)"/);
            if (match) {
              fbDtsg = match[1];
              break;
            }
          }
        }

        if (!fbDtsg) {
          return { ok: false, status: 0, body: "NO_FB_DTSG" };
        }

        const formData = new URLSearchParams();
        formData.append("fb_dtsg", fbDtsg);
        formData.append("doc_id", docId);
        formData.append("variables", variablesJson);

        const resp = await fetch(graphqlUrl, {
          method: "POST",
          body: formData,
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
        });

        if (!resp.ok) {
          const text = await resp.text().catch(() => "");
          return { ok: false, status: resp.status, body: text.substring(0, 2000) };
        }

        const data = await resp.json();
        return { ok: true, status: resp.status, data };
      } catch (e) {
        return { ok: false, status: 0, body: e.message };
      }
    },
    args: [META_GRAPHQL_URL, docId, JSON.stringify(variables)],
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
    throw new Error("AUTH_EXPIRED");
  }
  if (!result.ok) {
    console.error(`[MetaClient] ${result.status}: ${result.body}`);
    throw new Error(`META_ERROR:${result.status}`);
  }

  return result.data;
}
