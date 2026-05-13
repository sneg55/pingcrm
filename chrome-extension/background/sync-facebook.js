/**
 * Facebook Messenger sync orchestrator.
 *
 * Opens a background tab to facebook.com/messages, scrapes conversations
 * from the DOM (required because Messenger uses E2EE — data is only
 * readable after client-side decryption), then pushes to backend.
 *
 * Storage keys (chrome.storage.local):
 *   fbWatermark        - ISO timestamp of newest conversation activity
 *   lastFacebookSync   - ISO timestamp of last sync completion
 *   metaNextRetryAt    - ISO timestamp; block syncs until (rate-limit backoff)
 *   metaCookiesValid   - boolean
 */

let _fbSyncRunning = false;

/**
 * Run a Facebook Messenger sync cycle.
 *
 * @param {string} apiUrl - PingCRM backend base URL
 * @param {string} token  - Bearer token for the backend
 * @param {boolean} [force=false] - Skip throttle check
 * @returns {Promise<Object>} { skipped, conversations, messages, error }
 */
async function runFacebookSync(apiUrl, token, force = false) {
  const result = { skipped: false, conversations: 0, messages: 0, error: null };

  if (_fbSyncRunning) {
    result.skipped = true;
    return result;
  }
  _fbSyncRunning = true;

  try {
    return await _runFacebookSyncInner(apiUrl, token, force, result);
  } finally {
    _fbSyncRunning = false;
  }
}

async function _runFacebookSyncInner(apiUrl, token, force, result) {
  // ── Throttle check ──
  if (!force) {
    const stored = await chrome.storage.local.get(["lastFacebookSync", "metaNextRetryAt"]);

    if (stored.metaNextRetryAt && Date.now() < new Date(stored.metaNextRetryAt).getTime()) {
      result.skipped = true;
      return result;
    }

    if (stored.lastFacebookSync) {
      const elapsed = Date.now() - new Date(stored.lastFacebookSync).getTime();
      if (elapsed < META_SYNC_THROTTLE_MS) {
        result.skipped = true;
        return result;
      }
    }
  }

  // ── Read cookies ──
  let cUser;
  try {
    ({ cUser } = await _readMetaCookies());
  } catch (e) {
    result.error = e.message;
    await chrome.storage.local.set({ metaCookiesValid: false });
    return result;
  }

  await chrome.storage.local.set({ metaCookiesValid: true });
  console.log("[FBSync] Cookies OK, self user ID:", cUser);

  // ── Open background tab to Messenger ──
  let tabId;
  try {
    const tab = await chrome.tabs.create({
      url: "https://www.facebook.com/messages/t",
      active: false,
    });
    tabId = tab.id;
    console.log("[FBSync] Opened background tab:", tabId);

    // Wait for page to fully load
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        chrome.tabs.onUpdated.removeListener(listener);
        reject(new Error("PAGE_LOAD_TIMEOUT"));
      }, 30000);

      function listener(id, info) {
        if (id === tabId && info.status === "complete") {
          clearTimeout(timeout);
          chrome.tabs.onUpdated.removeListener(listener);
          resolve();
        }
      }
      chrome.tabs.onUpdated.addListener(listener);
    });

    // Extra wait for Messenger SPA to render conversations
    await _metaDelay(5000);
  } catch (e) {
    if (tabId) chrome.tabs.remove(tabId).catch(() => {});
    result.error = e.message;
    return result;
  }

  // ── Scrape conversations from DOM ──
  let conversations;
  try {
    const [execResult] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const items = [];
        const links = document.querySelectorAll('a[href*="/messages/t/"], a[href*="/messages/e2ee/t/"]');

        for (const a of links) {
          const href = a.href;
          const threadMatch = href.match(/\/t\/(\d+)\/?/);
          if (!threadMatch) continue;
          const threadId = threadMatch[1];

          // Skip duplicate thread IDs
          if (items.some(i => i.threadId === threadId)) continue;

          // Get the row container for this conversation
          const row = a.closest('[role="row"], [role="listitem"]') || a;

          // Extract name: first span[dir="auto"] within the row is typically the contact name
          const spans = row.querySelectorAll('span[dir="auto"]');
          let name = "";
          for (const s of spans) {
            const text = s.textContent.trim();
            // Skip timestamps, snippets (usually shorter or contain specific patterns)
            if (text && text.length > 0 && text.length < 60 && !text.match(/^\d+[mhd]\s*ago$/i)) {
              name = text;
              break;
            }
          }

          // Extract last message snippet: usually the second or third span
          let snippet = "";
          for (const s of spans) {
            const text = s.textContent.trim();
            if (text && text !== name && text.length > 0) {
              snippet = text;
              break;
            }
          }

          // Extract relative time: look for time-related text
          let timeText = "";
          const allText = row.textContent || "";
          const timeMatch = allText.match(/(\d+\s*(?:min|hour|day|week|month|year|[mhd])\w*\s*ago|just now|yesterday|\d{1,2}:\d{2}\s*[AP]M)/i);
          if (timeMatch) timeText = timeMatch[0];

          // Check if E2EE
          const isE2EE = href.includes("/e2ee/");

          items.push({ threadId, name, snippet, timeText, isE2EE, href });
        }

        return items;
      },
      world: "MAIN",
    });

    conversations = execResult?.result ?? [];
    console.log("[FBSync] Scraped", conversations.length, "conversations from DOM");
  } catch (e) {
    chrome.tabs.remove(tabId).catch(() => {});
    result.error = "SCRAPE_FAILED: " + e.message;
    return result;
  }

  // ── Close background tab ──
  chrome.tabs.remove(tabId).catch(() => {});

  result.conversations = conversations.length;

  if (conversations.length === 0) {
    console.log("[FBSync] No conversations found, saving sync timestamp");
    await chrome.storage.local.set({ lastFacebookSync: new Date().toISOString() });
    return result;
  }

  // ── Build profiles and messages for backend ──
  const profiles = [];
  const messages = [];
  const seenProfiles = new Set();
  let newestTimestamp = 0;

  for (const conv of conversations) {
    if (!conv.name || conv.name === "Unknown") continue;

    // Build profile
    if (!seenProfiles.has(conv.threadId)) {
      seenProfiles.add(conv.threadId);
      profiles.push({
        platform_id: conv.threadId,
        name: conv.name,
        username: null,
        avatar_url: null,
      });
    }

    // Build message from last conversation snippet.
    // The sidebar only exposes the last-message preview, not a real message ID.
    // Derive message_id from sha1(snippet) so re-syncs of the same snippet
    // produce the same key and dedupe on the backend.
    if (conv.snippet) {
      const now = Date.now();
      const snippetHash = await _metaSnippetHash(conv.snippet);

      messages.push({
        message_id: `fb_sidebar_${conv.threadId}_${snippetHash}`,
        conversation_id: conv.threadId,
        platform_id: conv.threadId,
        sender_name: conv.name,
        direction: "inbound", // sidebar shows their last message typically
        content_preview: conv.snippet.substring(0, 500),
        timestamp: new Date().toISOString(),
        reactions: [],
        read_by: [],
      });

      if (now > newestTimestamp) newestTimestamp = now;
    }
  }

  result.messages = messages.length;
  console.log("[FBSync] Built", profiles.length, "profiles,", messages.length, "messages");

  // ── Push to backend ──
  try {
    const pushResp = await fetch(`${apiUrl}/api/v1/meta/push`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        platform: "facebook",
        profiles,
        messages,
      }),
    });

    if (!pushResp.ok) {
      const errBody = await pushResp.text().catch(() => "");
      console.error("[FBSync] Push failed:", pushResp.status, errBody.substring(0, 500));
      if (pushResp.status === 401) {
        result.error = "AUTH_EXPIRED";
        return result;
      }
      result.error = `PUSH_FAILED:${pushResp.status}`;
      return result;
    }

    const pushData = (await pushResp.json())?.data ?? {};
    console.log("[FBSync] Push OK:", pushData);
  } catch (e) {
    result.error = e.message;
    return result;
  }

  // ── Persist watermark ──
  const updates = { lastFacebookSync: new Date().toISOString(), metaNextRetryAt: null };
  if (newestTimestamp > 0) {
    updates.fbWatermark = new Date(newestTimestamp).toISOString();
  }
  await chrome.storage.local.set(updates);

  return result;
}
