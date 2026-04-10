/**
 * Facebook Messenger sync orchestrator.
 *
 * Fetches conversations and messages via Meta's internal GraphQL API,
 * then pushes results to the PingCRM backend.
 *
 * Storage keys (chrome.storage.local):
 *   fbWatermark        - ISO timestamp of newest message (delta cursor)
 *   lastFacebookSync   - ISO timestamp of last sync completion
 *   metaNextRetryAt    - ISO timestamp; block syncs until (rate-limit backoff)
 *   metaCookiesValid   - boolean
 */

// GraphQL doc_id hashes — these are Meta's internal query identifiers.
// They may change when Meta deploys updates; update as needed.
const FB_CONVERSATIONS_DOC_ID = "8845758248780392";  // LSPlatformGraphQLLightspeedRequestQuery
const FB_MESSAGES_DOC_ID = "9106571592726805";        // thread messages query

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

  // ── Determine sync mode ──
  const { fbWatermark } = await chrome.storage.local.get(["fbWatermark"]);
  const isFirstSync = !fbWatermark;
  const cutoffMs = isFirstSync
    ? Date.now() - META_BACKFILL_WINDOW_MS
    : new Date(fbWatermark).getTime();

  // ── Fetch conversations ──
  let conversations;
  try {
    const raw = await metaGraphQL(FB_CONVERSATIONS_DOC_ID, {
      limit: META_CONVERSATION_MAX,
      before: null,
    }, "facebook");
    conversations = _parseMetaConversations(raw);
    await _metaDelay(META_RATE_LIMIT_DELAY_MS);
  } catch (e) {
    return await _handleMetaSyncError(e, result);
  }

  result.conversations = conversations.length;
  console.log("[FBSync] Fetched", conversations.length, "conversations");

  // ── Process conversations → messages ──
  const allMessages = [];
  let newestTimestamp = fbWatermark ? new Date(fbWatermark).getTime() : 0;

  for (const thread of conversations) {
    const threadId = thread?.thread_key?.thread_fbid ?? thread?.id ?? null;
    if (!threadId) continue;

    const lastActivityMs = thread?.updated_time_precise
      ? parseInt(thread.updated_time_precise)
      : (thread?.updated_time ?? 0) * 1000;

    if (!isFirstSync && lastActivityMs <= cutoffMs) continue;

    // Identify conversation partner
    const participants = thread?.all_participants?.nodes ?? thread?.participants?.nodes ?? [];
    const partner = participants.find(p => (p?.id ?? p?.messaging_actor?.id) !== cUser);
    const partnerId = partner?.id ?? partner?.messaging_actor?.id ?? null;
    const partnerName = partner?.name ?? partner?.messaging_actor?.name ?? "Unknown";

    // Fetch messages for this thread
    let messages;
    try {
      const msgRaw = await metaGraphQL(FB_MESSAGES_DOC_ID, {
        thread_id: threadId,
        message_limit: META_MESSAGES_PER_CONV_MAX,
      }, "facebook");
      messages = _parseMetaMessages(msgRaw);
      await _metaDelay(META_RATE_LIMIT_DELAY_MS);
    } catch (e) {
      if (e.message === "RATE_LIMITED" || e.message === "AUTH_EXPIRED") {
        return await _handleMetaSyncError(e, result);
      }
      console.warn("[FBSync] Failed to fetch messages for thread", threadId, e.message);
      continue;
    }

    for (const msg of messages) {
      const createdAtMs = msg?.timestamp_precise
        ? parseInt(msg.timestamp_precise)
        : (msg?.timestamp ?? 0) * 1000;

      if (!isFirstSync && createdAtMs <= cutoffMs) continue;

      const payload = _metaMessageToPayload(msg, threadId, partnerId, partnerName, cUser);
      allMessages.push(payload);

      if (createdAtMs > newestTimestamp) newestTimestamp = createdAtMs;
    }
  }

  result.messages = allMessages.length;
  console.log("[FBSync] Extracted", allMessages.length, "messages");

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
        profiles: [],
        messages: allMessages,
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
