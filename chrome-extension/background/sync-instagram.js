/**
 * Instagram DM sync orchestrator.
 *
 * Opens a background tab to instagram.com/direct/inbox, scrapes DM threads
 * from the DOM, then pushes to PingCRM backend.
 *
 * Storage keys (chrome.storage.local):
 *   igWatermark        - ISO timestamp of newest conversation activity
 *   lastInstagramSync  - ISO timestamp of last sync completion
 *   metaNextRetryAt    - shared with Facebook sync
 *   metaCookiesValid   - shared with Facebook sync
 */

let _igSyncRunning = false;

/**
 * Run an Instagram DM sync cycle.
 *
 * @param {string} apiUrl - PingCRM backend base URL
 * @param {string} token  - Bearer token for the backend
 * @param {boolean} [force=false] - Skip throttle check
 * @returns {Promise<Object>} { skipped, conversations, messages, error }
 */
async function runInstagramSync(apiUrl, token, force = false) {
  const result = { skipped: false, conversations: 0, messages: 0, error: null };

  if (_igSyncRunning) {
    result.skipped = true;
    return result;
  }
  _igSyncRunning = true;

  try {
    return await _runInstagramSyncInner(apiUrl, token, force, result);
  } finally {
    _igSyncRunning = false;
  }
}

async function _runInstagramSyncInner(apiUrl, token, force, result) {
  // ── Throttle check ──
  if (!force) {
    const stored = await chrome.storage.local.get(["lastInstagramSync", "metaNextRetryAt"]);

    if (stored.metaNextRetryAt && Date.now() < new Date(stored.metaNextRetryAt).getTime()) {
      result.skipped = true;
      return result;
    }

    if (stored.lastInstagramSync) {
      const elapsed = Date.now() - new Date(stored.lastInstagramSync).getTime();
      if (elapsed < META_SYNC_THROTTLE_MS) {
        result.skipped = true;
        return result;
      }
    }
  }

  // ── Read cookies (shared Meta session) ──
  let cUser;
  try {
    ({ cUser } = await _readMetaCookies());
  } catch (e) {
    result.error = e.message;
    await chrome.storage.local.set({ metaCookiesValid: false });
    return result;
  }

  await chrome.storage.local.set({ metaCookiesValid: true });
  console.log("[IGSync] Cookies OK, self user ID:", cUser);

  // ── Open background tab to Instagram DMs ──
  let tabId;
  try {
    const tab = await chrome.tabs.create({
      url: "https://www.instagram.com/direct/inbox/",
      active: false,
    });
    tabId = tab.id;
    console.log("[IGSync] Opened background tab:", tabId);

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

    // Extra wait for Instagram SPA to render DM threads
    await _metaDelay(5000);
  } catch (e) {
    if (tabId) chrome.tabs.remove(tabId).catch(() => {});
    result.error = e.message;
    return result;
  }

  // ── Scrape DM threads from DOM ──
  let threads;
  try {
    const [execResult] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const items = [];

        // Instagram DM threads are links to /direct/t/<thread_id>/
        const links = document.querySelectorAll('a[href*="/direct/t/"]');

        for (const a of links) {
          const href = a.href;
          const threadMatch = href.match(/\/direct\/t\/(\d+)\/?/);
          if (!threadMatch) continue;
          const threadId = threadMatch[1];

          if (items.some(i => i.threadId === threadId)) continue;

          const row = a.closest('[role="listitem"], [role="row"]') || a;

          // Extract username/name
          const spans = row.querySelectorAll('span');
          let name = "";
          let snippet = "";
          let timeText = "";

          for (const s of spans) {
            const text = s.textContent.trim();
            if (!text) continue;

            // First non-empty span is typically the name
            if (!name && text.length < 60 && !text.match(/^\d+[mhd]\s/i) && !text.match(/^(Active|Seen)/i)) {
              name = text;
              continue;
            }

            // Look for time indicators
            if (!timeText && (text.match(/^\d+\s*[mhdw]/i) || text.match(/^(just now|yesterday)/i))) {
              timeText = text;
              continue;
            }

            // Everything else could be a snippet
            if (!snippet && text !== name && text.length > 0) {
              snippet = text;
            }
          }

          if (name) {
            items.push({ threadId, name, snippet, timeText, href });
          }
        }

        return items;
      },
      world: "MAIN",
    });

    threads = execResult?.result ?? [];
    console.log("[IGSync] Scraped", threads.length, "DM threads from DOM");
  } catch (e) {
    chrome.tabs.remove(tabId).catch(() => {});
    result.error = "SCRAPE_FAILED: " + e.message;
    return result;
  }

  // ── Close background tab ──
  chrome.tabs.remove(tabId).catch(() => {});

  result.conversations = threads.length;

  if (threads.length === 0) {
    console.log("[IGSync] No DM threads found, saving sync timestamp");
    await chrome.storage.local.set({ lastInstagramSync: new Date().toISOString() });
    return result;
  }

  // ── Build profiles and messages for backend ──
  const profiles = [];
  const messages = [];
  const seenProfiles = new Set();
  let newestTimestamp = 0;

  for (const thread of threads) {
    if (!thread.name) continue;

    // Build profile
    if (!seenProfiles.has(thread.threadId)) {
      seenProfiles.add(thread.threadId);
      profiles.push({
        platform_id: thread.threadId,
        name: thread.name,
        username: thread.name.startsWith("@") ? thread.name.slice(1) : thread.name,
        avatar_url: null,
      });
    }

    // Build message from last DM snippet. Sidebar has no real message ID,
    // so derive a stable key from sha1(snippet) — re-syncs of the same
    // snippet produce the same key and dedupe on the backend.
    if (thread.snippet) {
      const now = Date.now();
      const snippetHash = await _metaSnippetHash(thread.snippet);

      messages.push({
        message_id: `ig_sidebar_${thread.threadId}_${snippetHash}`,
        conversation_id: thread.threadId,
        platform_id: thread.threadId,
        sender_name: thread.name,
        direction: "inbound",
        content_preview: thread.snippet.substring(0, 500),
        timestamp: new Date().toISOString(),
        reactions: [],
        read_by: [],
      });

      if (now > newestTimestamp) newestTimestamp = now;
    }
  }

  result.messages = messages.length;
  console.log("[IGSync] Built", profiles.length, "profiles,", messages.length, "messages");

  // ── Push to backend ──
  try {
    const pushResp = await fetch(`${apiUrl}/api/v1/meta/push`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        platform: "instagram",
        profiles,
        messages,
      }),
    });

    if (!pushResp.ok) {
      const errBody = await pushResp.text().catch(() => "");
      console.error("[IGSync] Push failed:", pushResp.status, errBody.substring(0, 500));
      if (pushResp.status === 401) {
        result.error = "AUTH_EXPIRED";
        return result;
      }
      result.error = `PUSH_FAILED:${pushResp.status}`;
      return result;
    }

    const pushData = (await pushResp.json())?.data ?? {};
    console.log("[IGSync] Push OK:", pushData);
  } catch (e) {
    result.error = e.message;
    return result;
  }

  // ── Persist watermark ──
  const updates = { lastInstagramSync: new Date().toISOString(), metaNextRetryAt: null };
  if (newestTimestamp > 0) {
    updates.igWatermark = new Date(newestTimestamp).toISOString();
  }
  await chrome.storage.local.set(updates);

  return result;
}
