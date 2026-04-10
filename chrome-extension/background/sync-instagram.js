/**
 * Instagram DM sync orchestrator.
 *
 * Fetches DM threads and messages via Meta's internal GraphQL API
 * (shared with Facebook), then pushes to PingCRM backend.
 *
 * Storage keys (chrome.storage.local):
 *   igWatermark        - ISO timestamp of newest message (delta cursor)
 *   lastInstagramSync  - ISO timestamp of last sync completion
 *   metaNextRetryAt    - shared with Facebook sync
 *   metaCookiesValid   - shared with Facebook sync
 */

// Instagram DM GraphQL doc_ids
const IG_THREADS_DOC_ID = "6707582879298508";   // IGDInboxQuery
const IG_MESSAGES_DOC_ID = "7123744197665318";   // thread detail query

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

  // ── Determine sync mode ──
  const { igWatermark } = await chrome.storage.local.get(["igWatermark"]);
  const isFirstSync = !igWatermark;
  const cutoffMs = isFirstSync
    ? Date.now() - META_BACKFILL_WINDOW_MS
    : new Date(igWatermark).getTime();

  // ── Fetch threads ──
  let threads;
  try {
    // Instagram DMs use the same GraphQL endpoint but via instagram.com tab
    const raw = await metaGraphQL(IG_THREADS_DOC_ID, {
      limit: META_CONVERSATION_MAX,
      before: null,
    }, "instagram");
    threads = _parseInstagramThreads(raw);
    await _metaDelay(META_RATE_LIMIT_DELAY_MS);
  } catch (e) {
    return await _handleMetaSyncError(e, result);
  }

  result.conversations = threads.length;
  console.log("[IGSync] Fetched", threads.length, "threads");

  // ── Process threads → messages ──
  const allMessages = [];
  let newestTimestamp = igWatermark ? new Date(igWatermark).getTime() : 0;

  for (const thread of threads) {
    const threadId = thread?.thread_id ?? thread?.id ?? null;
    if (!threadId) continue;

    const lastActivityMs = thread?.last_activity_at
      ? parseInt(thread.last_activity_at)
      : 0;

    if (!isFirstSync && lastActivityMs <= cutoffMs) continue;

    // Identify conversation partner
    const users = thread?.users ?? thread?.participants ?? [];
    const partner = users.find(u => (u?.pk ?? u?.id) !== cUser);
    const partnerId = partner?.pk ?? partner?.id ?? null;
    const partnerName = partner?.full_name ?? partner?.username ?? "Unknown";
    const partnerUsername = partner?.username ?? null;

    // Fetch messages for this thread
    let messages;
    try {
      const msgRaw = await metaGraphQL(IG_MESSAGES_DOC_ID, {
        thread_id: threadId,
        message_limit: META_MESSAGES_PER_CONV_MAX,
      }, "instagram");
      messages = _parseInstagramMessages(msgRaw);
      await _metaDelay(META_RATE_LIMIT_DELAY_MS);
    } catch (e) {
      if (e.message === "RATE_LIMITED" || e.message === "AUTH_EXPIRED") {
        return await _handleMetaSyncError(e, result);
      }
      console.warn("[IGSync] Failed to fetch messages for thread", threadId, e.message);
      continue;
    }

    for (const msg of messages) {
      const createdAtMs = msg?.timestamp ? parseInt(msg.timestamp) / 1000 : 0;

      if (!isFirstSync && createdAtMs <= cutoffMs) continue;

      const payload = _igMessageToPayload(msg, threadId, partnerId, partnerName, cUser);
      allMessages.push(payload);

      if (createdAtMs > newestTimestamp) newestTimestamp = createdAtMs;
    }
  }

  result.messages = allMessages.length;
  console.log("[IGSync] Extracted", allMessages.length, "messages");

  // ── Push to backend ──
  try {
    // Build profiles from thread partners for contact creation
    const profilesSeen = new Set();
    const profiles = [];
    for (const thread of threads) {
      const users = thread?.users ?? thread?.participants ?? [];
      const partner = users.find(u => (u?.pk ?? u?.id) !== cUser);
      if (!partner) continue;
      const pid = partner?.pk ?? partner?.id;
      if (!pid || profilesSeen.has(pid)) continue;
      profilesSeen.add(pid);
      profiles.push({
        platform_id: pid,
        name: partner?.full_name ?? partner?.username ?? "",
        username: partner?.username ?? null,
        avatar_url: partner?.profile_pic_url ?? null,
      });
    }

    const pushResp = await fetch(`${apiUrl}/api/v1/meta/push`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        platform: "instagram",
        profiles,
        messages: allMessages,
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
