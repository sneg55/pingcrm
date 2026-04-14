/**
 * Voyager sync orchestrator for PingCRM LinkedIn Companion.
 *
 * Reads LinkedIn session cookies, fetches conversations and messages via the
 * Voyager API, and pushes results to the PingCRM backend.
 *
 * Depends on sync-utils.js (constants, parsers, helpers) loaded first via
 * importScripts.
 *
 * Storage keys used (chrome.storage.local):
 *   watermark        - ISO timestamp of the newest message processed (delta cursor)
 *   lastVoyagerSync  - ISO timestamp of when the last sync completed
 *   nextRetryAt      - ISO timestamp; block syncs until this time (rate-limit backoff)
 *   cookiesValid     - boolean; set to false when AUTH_EXPIRED is received
 */

// ── Main sync function ──────────────────────────────────────────────────────

/**
 * Run a Voyager sync cycle.
 *
 * @param {string} apiUrl - PingCRM backend base URL
 * @param {string} token  - Bearer token for the backend
 * @param {boolean} [force=false] - Skip throttle check and run immediately
 * @returns {Promise<{
 *   skipped: boolean,
 *   conversations: number,
 *   messages: number,
 *   backfilled: number,
 *   error: string|null
 * }>}
 */
let _syncRunning = false;

async function runSync(apiUrl, token, force = false) {
  const result = { skipped: false, conversations: 0, messages: 0, backfilled: 0, error: null };

  // ── Sync lock — prevent concurrent syncs ──
  if (_syncRunning) {
    console.log("[Sync] Already running, skipping");
    result.skipped = true;
    return result;
  }
  _syncRunning = true;

  try {
    return await _runSyncInner(apiUrl, token, force, result);
  } finally {
    _syncRunning = false;
  }
}

async function _runSyncInner(apiUrl, token, force, result) {
  // ── Throttle check ──
  if (!force) {
    const stored = await chrome.storage.local.get(["lastVoyagerSync", "nextRetryAt"]);

    if (stored.nextRetryAt && Date.now() < new Date(stored.nextRetryAt).getTime()) {
      const waitMin = Math.round((new Date(stored.nextRetryAt).getTime() - Date.now()) / 60000);
      console.log("[Sync] Skipped: rate-limit backoff active, retry in", waitMin, "min");
      result.skipped = true;
      return result;
    }

    if (stored.lastVoyagerSync) {
      const elapsed = Date.now() - new Date(stored.lastVoyagerSync).getTime();
      if (elapsed < SYNC_THROTTLE_MS) {
        const remainMin = Math.round((SYNC_THROTTLE_MS - elapsed) / 60000);
        console.log("[Sync] Skipped: throttle, last sync", Math.round(elapsed / 60000), "min ago, next in", remainMin, "min");
        result.skipped = true;
        return result;
      }
    }
  }

  // ── Read cookies ──
  let liAt, jsessionid;
  try {
    ({ liAt, jsessionid } = await _readLinkedInCookies());
  } catch (e) {
    result.error = e.message;
    await chrome.storage.local.set({ cookiesValid: false });
    return result;
  }

  await chrome.storage.local.set({ cookiesValid: true });
  console.log("[Sync] Cookies OK, reading watermark...");

  // ── Determine sync mode (first sync vs delta) ──
  const { watermark } = await chrome.storage.local.get(["watermark"]);
  const isFirstSync = !watermark;
  console.log("[Sync] Mode:", isFirstSync ? "FIRST SYNC" : "delta", "watermark:", watermark);
  const cutoffMs = isFirstSync
    ? Date.now() - BACKFILL_WINDOW_MS
    : new Date(watermark).getTime();

  // ── Get self URN (needed for conversation list) ──
  let selfUrn;
  try {
    console.log("[Sync] Fetching self URN...");
    selfUrn = await voyagerGetSelfUrn(liAt, jsessionid);
    console.log("[Sync] Self URN:", selfUrn);
    await _delay(RATE_LIMIT_DELAY_MS);
  } catch (e) {
    console.error("[Sync] Self URN failed:", e.message);
    return await _handleSyncError(e, result);
  }

  // ── Fetch conversations (paginated) ──
  const conversations = await _fetchAllConversations(liAt, jsessionid, selfUrn, isFirstSync, cutoffMs, result);
  if (result.error) return result;

  result.conversations = conversations.length;
  console.log("[Sync] Fetched", conversations.length, "conversations total");

  // ── Process each conversation into messages ──
  const { allMessages, newestTimestamp } = await _processConversations(
    conversations, liAt, jsessionid, selfUrn, isFirstSync, cutoffMs, watermark, result
  );
  if (result.error) return result;

  result.messages = allMessages.length;

  // ── Push to backend (always push, even with 0 messages, to get backfill_needed) ──
  try {
    const pushResp = await fetch(`${apiUrl}/api/v1/linkedin/push`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify({ profiles: [], messages: allMessages }),
    });

    if (!pushResp.ok) {
      const errBody = await pushResp.text().catch(() => "");
      console.error("[Sync] Push failed:", pushResp.status, errBody.substring(0, 500));
      if (pushResp.status === 401) {
        result.error = "AUTH_EXPIRED";
        return result;
      }
      result.error = `PUSH_FAILED:${pushResp.status}`;
      return result;
    }
    console.log("[Sync] Push succeeded:", result.messages, "messages");

    const pushJson = await pushResp.json();
    const pushData = pushJson?.data ?? {};
    console.log("[Sync] Push response keys:", Object.keys(pushJson || {}), "data keys:", Object.keys(pushData || {}));

    // Handle backfill request: store for a separate pass to avoid MV3 SW termination
    const backfillIds = pushData?.backfill_needed ?? [];
    console.log("[Sync] Backfill needed:", backfillIds.length, backfillIds.length > 0 ? JSON.stringify(backfillIds[0]) : "none");
    if (backfillIds.length > 0) {
      await chrome.storage.local.set({ _pendingBackfill: backfillIds });
    }
  } catch (e) {
    result.error = e.message;
    return result;
  }

  // ── Persist watermark and sync timestamp ──
  const updates = { lastVoyagerSync: new Date().toISOString(), nextRetryAt: null };
  if (newestTimestamp > 0) {
    updates.watermark = new Date(newestTimestamp).toISOString();
  }
  await chrome.storage.local.set(updates);

  return result;
}

// ── Conversation pagination ─────────────────────────────────────────────────

async function _fetchAllConversations(liAt, jsessionid, selfUrn, isFirstSync, cutoffMs, result) {
  const conversations = [];
  let pageCursor = null;
  let morePages = true;

  while (morePages && conversations.length < CONVERSATION_PAGE_MAX) {
    let pageRaw;
    try {
      pageRaw = await voyagerGetConversations(liAt, jsessionid, selfUrn, pageCursor);
      await _delay(RATE_LIMIT_DELAY_MS);
    } catch (e) {
      await _handleSyncError(e, result);
      return conversations;
    }

    const page = _parseConversations(pageRaw);

    if (page.length === 0) {
      morePages = false;
      break;
    }

    const oldestOnPage = page[page.length - 1]?.lastActivityAt ?? 0;

    for (const conv of page) {
      conversations.push(conv);
      if (conversations.length >= CONVERSATION_PAGE_MAX) break;
    }

    if (!isFirstSync && oldestOnPage <= cutoffMs) {
      morePages = false;
    } else {
      pageCursor = page[page.length - 1]?.lastActivityAt ?? null;
      if (pageCursor === null) morePages = false;
    }
  }

  return conversations;
}

// ── Message extraction per conversation ─────────────────────────────────────

async function _processConversations(conversations, liAt, jsessionid, selfUrn, isFirstSync, cutoffMs, watermark, result) {
  const allMessages = [];
  let newestTimestamp = watermark ? new Date(watermark).getTime() : 0;
  const selfUrnSuffix = selfUrn.split(":").pop();

  for (const conv of conversations) {
    const convUrn = conv?.entityUrn ?? conv?.backendUrn ?? conv?.["*id"] ?? null;
    const threadUrn = conv?.backendUrn ?? convUrn;
    if (!convUrn) continue;

    const lastActivityAt = conv?.lastActivityAt ?? 0;

    // Delta sync: skip conversations with no new activity
    if (!isFirstSync && lastActivityAt <= cutoffMs) continue;

    const participants = _parseParticipants(conv);
    const otherParticipants = participants.filter(p => {
      const pUrnSuffix = (p.profileUrn || "").split(":").pop();
      return pUrnSuffix !== selfUrnSuffix;
    });
    const partner = otherParticipants[0] ?? participants[0] ?? null;

    let partnerPublicId = partner?.publicIdentifier ?? null;
    if (partnerPublicId && partnerPublicId.startsWith("ACo")) {
      const convUrl = conv?.conversationUrl?.url ?? conv?.conversationUrl ?? "";
      const slugFromUrl = typeof convUrl === "string" ? convUrl.match(/\/in\/([^/?]+)/)?.[1] : null;
      partnerPublicId = slugFromUrl ?? partnerPublicId;
    }

    const convTitle = conv?.title?.text ?? (typeof conv?.title === "string" ? conv.title : null);
    const partnerName = [partner?.firstName, partner?.lastName].filter(Boolean).join(" ")
      || convTitle
      || partnerPublicId
      || "Unknown";

    const isRecent = lastActivityAt >= cutoffMs;

    // Debug: log first conv's timestamps to verify format
    if (allMessages.length === 0) {
      console.log("[Sync] Timestamp debug:", {
        lastActivityAt,
        cutoffMs,
        asDate: new Date(lastActivityAt).toISOString(),
        cutoffDate: new Date(cutoffMs).toISOString(),
        isRecent,
      });
    }

    if (!isFirstSync || isRecent) {
      const embeddedMessages = conv?.messages?.elements ?? (Array.isArray(conv?.messages) ? conv.messages : []);
      let eventsRaw;

      if (allMessages.length === 0 && embeddedMessages.length > 0) {
        console.log("[Sync] Embedded msg type:", typeof embeddedMessages[0], embeddedMessages[0]?._type);
        console.log("[Sync] Embedded msg keys:", Object.keys(embeddedMessages[0] || {}));
      }
      if (embeddedMessages.length > 0) {
        eventsRaw = { data: { messengerMessages: { elements: embeddedMessages } } };
      } else {
        try {
          eventsRaw = await voyagerGetConversationMessages(liAt, jsessionid, threadUrn);
          await _delay(RATE_LIMIT_DELAY_MS);
        } catch (e) {
          if (e.message === "RATE_LIMITED" || e.message === "AUTH_EXPIRED") {
            await _handleSyncError(e, result);
            return { allMessages, newestTimestamp };
          }
          console.warn("[PingCRM Voyager] Failed to fetch events for", convUrn, e.message);
          continue;
        }
      }

      const events = _parseMessages(eventsRaw);
      if (allMessages.length === 0) {
        console.log("[Sync] Parsed events:", events.length, "from eventsRaw keys:", Object.keys(eventsRaw || {}));
      }
      for (const event of events) {
        const createdAt = event?.createdAt ?? event?.deliveredAt ?? 0;
        if (!isFirstSync && createdAt <= cutoffMs) continue;

        const msg = _eventToMessage(event, convUrn, partnerPublicId, partnerName, selfUrnSuffix);
        allMessages.push(msg);

        if (createdAt > newestTimestamp) newestTimestamp = createdAt;
      }
    } else {
      // First sync, older conversation: use only the last message preview
      const lastMsg = conv?.lastMessage ?? conv?.lastEvent ?? null;
      if (lastMsg) {
        const previewMsg = _eventToMessage(lastMsg, convUrn, partnerPublicId, partnerName, selfUrnSuffix);
        allMessages.push(previewMsg);
      }
    }
  }

  return { allMessages, newestTimestamp };
}
