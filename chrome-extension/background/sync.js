/**
 * Voyager sync orchestrator for PingCRM LinkedIn Companion.
 *
 * Reads LinkedIn session cookies, fetches conversations and messages via the
 * Voyager API, and pushes results to the PingCRM backend.
 *
 * Storage keys used (chrome.storage.local):
 *   watermark        - ISO timestamp of the newest message processed (delta cursor)
 *   lastVoyagerSync  - ISO timestamp of when the last sync completed
 *   nextRetryAt      - ISO timestamp; block syncs until this time (rate-limit backoff)
 *   cookiesValid     - boolean; set to false when AUTH_EXPIRED is received
 */

const SYNC_THROTTLE_MS = 15 * 60 * 1000; // 15 minutes between auto-syncs
const RATE_LIMIT_DELAY_MS = 1000;             // 1 second between Voyager calls
const BACKFILL_WINDOW_MS = 30 * 24 * 60 * 60 * 1000; // 30 days for first-sync full fetch
const CONVERSATION_PAGE_MAX = 500;            // hard cap to prevent infinite pagination

// ── Cookie helpers ────────────────────────────────────────────────────────────

/**
 * Read all LinkedIn cookies fresh from the browser.
 * Returns { liAt, jsessionid } or throws if required cookies are missing.
 *
 * @returns {Promise<{liAt: string, jsessionid: string}>}
 * @throws {Error} "MISSING_COOKIES" if li_at or JSESSIONID are not found
 */
async function _readLinkedInCookies() {
  const cookies = await chrome.cookies.getAll({ domain: ".linkedin.com" });
  const map = Object.fromEntries(cookies.map(c => [c.name, c.value]));
  const liAt = map["li_at"];
  const jsessionid = map["JSESSIONID"];
  if (!liAt || !jsessionid) throw new Error("MISSING_COOKIES");
  return { liAt, jsessionid };
}

// ── Delay helper ──────────────────────────────────────────────────────────────

function _delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ── Voyager response parsers ──────────────────────────────────────────────────

/**
 * Extract conversations from a Voyager normalized response.
 * Voyager uses an `included` array with $type discriminators.
 *
 * @param {Object} raw - Raw Voyager JSON response
 * @returns {Array<Object>} Conversation objects
 */
/**
 * Parse conversations from GraphQL messengerConversations response.
 * Response shape: data.messengerConversationsBySyncToken.elements[]
 * or data.messengerConversations.elements[]
 */
function _parseConversations(raw) {
  // GraphQL: data → messengerConversationsBySyncToken → elements
  const bySyncToken = raw?.data?.messengerConversationsBySyncToken?.elements ?? [];
  if (bySyncToken.length > 0) return bySyncToken;

  // GraphQL alt: data → messengerConversations → elements
  const direct = raw?.data?.messengerConversations?.elements ?? [];
  if (direct.length > 0) return direct;

  // Dash REST: top-level elements
  const elements = raw?.elements ?? raw?.data?.elements ?? [];
  if (elements.length > 0) return elements;

  // Legacy: included array
  const included = raw?.included ?? [];
  return included.filter(item => {
    const type = item?.$type ?? "";
    return type.includes("Conversation") || type.includes("MessengerConversation");
  });
}

/**
 * Parse messages from a GraphQL messengerMessages response.
 * GraphQL returns messages in data.messengerMessagesByConversation.elements
 */
function _parseMessages(raw) {
  // GraphQL response format
  const gqlElements = raw?.data?.messengerMessagesByConversation?.elements
    ?? raw?.data?.messengerMessages?.elements
    ?? [];
  if (gqlElements.length > 0) return gqlElements;

  // Fallback: included array with Event type (old format, just in case)
  const included = raw?.included ?? [];
  return included.filter(item => {
    const type = item?.$type ?? "";
    return type.includes("Event") || type.includes("Message");
  });
}

/**
 * Extract participant info from a conversation object.
 * GraphQL format (2026): conversationParticipants[] with
 *   participantType.member.profileUrl containing the slug
 *   hostIdentityUrn containing the profile URN
 */
function _parseParticipants(conversation) {
  const dashParticipants = conversation?.conversationParticipants ?? [];
  if (dashParticipants.length > 0) {
    return dashParticipants
      .map(p => {
        // GraphQL 2026 format: participantType.member has profileUrl
        const member = p?.participantType?.member ?? {};
        const profileUrl = member?.profileUrl ?? "";
        // Extract publicIdentifier (slug) from URL: https://www.linkedin.com/in/john-doe
        const slug = profileUrl.match(/\/in\/([^/?]+)/)?.[1] ?? null;

        // Also try nested memberProfile or miniProfile
        const profile = member?.memberProfile ?? p?.memberProfile ?? p?.miniProfile ?? {};
        const publicId = slug ?? profile?.publicIdentifier ?? null;

        // Name: try member.distance.memberRelationship fields, or profile fields
        // Names can be plain strings or {text: "..."} attributed text objects
        const rawFirst = profile?.firstName ?? member?.firstName ?? null;
        const rawLast = profile?.lastName ?? member?.lastName ?? null;
        const firstName = typeof rawFirst === "object" ? rawFirst?.text ?? null : rawFirst;
        const lastName = typeof rawLast === "object" ? rawLast?.text ?? null : rawLast;

        return {
          publicIdentifier: publicId,
          firstName,
          lastName,
          // Also store the URN for identity resolution
          profileUrn: p?.hostIdentityUrn ?? profile?.entityUrn ?? null,
        };
      })
      .filter(p => p.publicIdentifier || p.profileUrn);
  }

  // Legacy format: participants with miniProfile
  const participants = conversation?.participants ?? [];
  return participants
    .map(p => {
      const mini = p?.miniProfile
        ?? p?.["com.linkedin.voyager.messaging.MessagingMember"]?.miniProfile
        ?? {};
      return {
        publicIdentifier: mini?.publicIdentifier ?? null,
        firstName: mini?.firstName ?? null,
        lastName: mini?.lastName ?? null,
        profileUrn: mini?.entityUrn ?? null,
      };
    })
    .filter(p => p.publicIdentifier || p.profileUrn);
}

/**
 * Convert a message (from GraphQL or Dash) into the shape expected by /linkedin/push.
 */
function _eventToMessage(msg, conversationUrn, partnerPublicId, partnerName) {
  // GraphQL format: body.text or body.attributedBody.text
  const text = msg?.body?.text
    ?? msg?.body?.attributedBody?.text
    ?? msg?.eventContent?.body
    ?? msg?.eventContent?.["com.linkedin.voyager.messaging.event.MessageEvent"]?.attributedBody?.text
    ?? "";
  const createdAt = msg?.deliveredAt ?? msg?.createdAt ?? null;
  // GraphQL: sender is in msg.sender.memberProfile or msg.from
  const sender = msg?.sender?.memberProfile
    ?? msg?.from?.["com.linkedin.voyager.messaging.MessagingMember"]?.miniProfile
    ?? {};
  const senderPublicId = sender?.publicIdentifier ?? null;

  return {
    conversation_id: conversationUrn,
    profile_id: partnerPublicId,
    profile_name: partnerName ?? partnerPublicId ?? "",
    direction: senderPublicId === partnerPublicId ? "inbound" : "outbound",
    content_preview: String(text).substring(0, 500),
    timestamp: createdAt ? new Date(createdAt).toISOString() : new Date().toISOString(),
    source: "voyager",
    raw_reference_id: `linkedin:voyager:${msg?.entityUrn ?? msg?.backendUrn ?? ""}`,
  };
}

// ── Main sync function ────────────────────────────────────────────────────────

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
  // We page through conversations using the lastActivityAt of the last conversation
  // on the previous page as a cursor. Pagination stops when:
  //   (a) the API returns an empty page,
  //   (b) all returned conversations are older than the watermark (delta sync guard),
  //   (c) we have accumulated CONVERSATION_PAGE_MAX conversations.
  const conversations = [];
  let pageCursor = null; // Unix ms — lastActivityAt of last conv on previous page
  let morePages = true;

  while (morePages && conversations.length < CONVERSATION_PAGE_MAX) {
    let pageRaw;
    try {
      pageRaw = await voyagerGetConversations(liAt, jsessionid, selfUrn, pageCursor);
      await _delay(RATE_LIMIT_DELAY_MS);
    } catch (e) {
      return await _handleSyncError(e, result);
    }

    const page = _parseConversations(pageRaw);

    if (page.length === 0) {
      // No more conversations returned — end of inbox
      morePages = false;
      break;
    }

    // Check whether the entire page is older than the watermark.
    // lastActivityAt is in Unix ms; conversations are returned newest-first.
    // The oldest conversation on this page is the last one.
    const oldestOnPage = page[page.length - 1]?.lastActivityAt ?? 0;

    for (const conv of page) {
      conversations.push(conv);
      if (conversations.length >= CONVERSATION_PAGE_MAX) break;
    }

    if (!isFirstSync && oldestOnPage <= cutoffMs) {
      // All remaining pages are older than the watermark — nothing new there
      morePages = false;
    } else {
      // Advance the cursor: use lastActivityAt of the last conversation fetched
      pageCursor = page[page.length - 1]?.lastActivityAt ?? null;
      if (pageCursor === null) morePages = false;
    }
  }

  result.conversations = conversations.length;
  console.log("[Sync] Fetched", conversations.length, "conversations total");

  const allMessages = [];
  let newestTimestamp = watermark ? new Date(watermark).getTime() : 0;

  // ── Process each conversation ──
  for (const conv of conversations) {
    // Use backendUrn (urn:li:messagingThread:...) for messages endpoint,
    // entityUrn for conversation identification
    const convUrn = conv?.entityUrn ?? conv?.backendUrn ?? conv?.["*id"] ?? null;
    // The messages GraphQL endpoint needs the backendUrn (thread format), not the composite entityUrn
    const threadUrn = conv?.backendUrn ?? convUrn;
    if (!convUrn) continue;

    const lastActivityAt = conv?.lastActivityAt ?? 0;

    // Delta sync: skip conversations with no new activity
    if (!isFirstSync && lastActivityAt <= cutoffMs) continue;

    const participants = _parseParticipants(conv);
    // Filter out self from participants
    const selfUrnSuffix = selfUrn.split(":").pop();
    const otherParticipants = participants.filter(p => {
      const pUrnSuffix = (p.profileUrn || "").split(":").pop();
      return pUrnSuffix !== selfUrnSuffix;
    });
    const partner = otherParticipants[0] ?? participants[0] ?? null;
    // Use slug from publicIdentifier, or extract from profileUrn member ID
    // The backend matches on linkedin_profile_id (slug) so we need the slug, not the URN
    let partnerPublicId = partner?.publicIdentifier ?? null;
    // If publicIdentifier looks like a URN member ID (starts with ACo), it's not a slug
    if (partnerPublicId && partnerPublicId.startsWith("ACo")) {
      // Store URN member ID separately, try to get slug from conversationUrl
      const convUrl = conv?.conversationUrl?.url ?? conv?.conversationUrl ?? "";
      const slugFromUrl = typeof convUrl === "string" ? convUrl.match(/\/in\/([^/?]+)/)?.[1] : null;
      partnerPublicId = slugFromUrl ?? partnerPublicId;
    }
    // Name: from participant data, or conversation title (which is usually the other person's name)
    const convTitle = conv?.title?.text ?? (typeof conv?.title === "string" ? conv.title : null);
    const partnerName = [partner?.firstName, partner?.lastName].filter(Boolean).join(" ")
      || convTitle
      || partnerPublicId
      || "Unknown";

    // For first sync: fetch full events only for recent conversations (within 30 days)
    // For older first-sync conversations: use the lastMessage from the conversation object
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
      // Check if messages are already embedded in the conversation response
      const embeddedMessages = conv?.messages?.elements ?? (Array.isArray(conv?.messages) ? conv.messages : []);
      let eventsRaw;

      // Use embedded messages first (always available, no extra API call).
      // The messengerMessages API returns 400 for the current GraphQL schema,
      // so we skip it and use what the conversation response already includes.
      if (allMessages.length === 0 && embeddedMessages.length > 0) {
        console.log("[Sync] Embedded msg type:", typeof embeddedMessages[0], embeddedMessages[0]?._type);
        console.log("[Sync] Embedded msg keys:", Object.keys(embeddedMessages[0] || {}));
      }
      if (embeddedMessages.length > 0) {
        eventsRaw = { data: { messengerMessages: { elements: embeddedMessages } } };
      } else {
        // Fetch messages via GraphQL using the thread URN (not composite entityUrn)
        try {
          eventsRaw = await voyagerGetConversationMessages(liAt, jsessionid, threadUrn);
          await _delay(RATE_LIMIT_DELAY_MS);
        } catch (e) {
          if (e.message === "RATE_LIMITED") {
            return await _handleSyncError(e, result);
          }
          if (e.message === "AUTH_EXPIRED") {
            return await _handleSyncError(e, result);
          }
          // Non-fatal error for this conversation — skip and continue
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

        const msg = _eventToMessage(event, convUrn, partnerPublicId, partnerName);
        allMessages.push(msg);

        if (createdAt > newestTimestamp) newestTimestamp = createdAt;
      }
    } else {
      // First sync, older conversation: use only the last message preview
      const lastMsg = conv?.lastMessage ?? conv?.lastEvent ?? null;
      if (lastMsg) {
        const previewMsg = _eventToMessage(lastMsg, convUrn, partnerPublicId, partnerName);
        allMessages.push(previewMsg);
      }
    }
  }

  result.messages = allMessages.length;

  // ── Push to backend (always push, even with 0 messages, to get backfill_needed) ──
  {
    try {
      // Push to backend
      const pushResp = await fetch(`${apiUrl}/api/v1/linkedin/push`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({ profiles: [], messages: allMessages }),
      });
      // Check response

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

      // Handle backfill request: fetch profiles for contacts missing data
      const backfillIds = pushData?.backfill_needed ?? [];
      console.log("[Sync] Backfill needed:", backfillIds.length, backfillIds.length > 0 ? JSON.stringify(backfillIds[0]) : "none");
      // Store backfill items for a separate pass — running them inline causes
      // MV3 service worker termination during long-running Voyager calls
      if (backfillIds.length > 0) {
        await chrome.storage.local.set({ _pendingBackfill: backfillIds });
      }
    } catch (e) {
      result.error = e.message;
      return result;
    }
  }

  // ── Persist watermark and sync timestamp ──
  const updates = { lastVoyagerSync: new Date().toISOString(), nextRetryAt: null };
  if (newestTimestamp > 0) {
    updates.watermark = new Date(newestTimestamp).toISOString();
  }
  await chrome.storage.local.set(updates);

  return result;
}

// ── Backfill helper ───────────────────────────────────────────────────────────

/**
 * Fetch profiles for contacts that are missing profile data and push them to the backend.
 * Called when the backend signals that certain contacts are missing profile data.
 *
 * @param {Array<{contact_id: string, linkedin_profile_id: string}>} backfillItems
 * @param {string} liAt
 * @param {string} jsessionid
 * @param {string} apiUrl
 * @param {string} token
 * @returns {Promise<number>} Number of profiles successfully fetched and pushed
 */
async function _backfillProfiles(backfillItems, liAt, jsessionid, apiUrl, token) {
  console.log("[Backfill] Starting for", backfillItems.length, "items");
  let backfilled = 0;
  const profiles = [];

  for (const item of backfillItems) {
    const publicId = item.linkedin_profile_id;
    if (!publicId) continue;
    console.log("[Backfill] Fetching profile for:", publicId);
    try {
      const raw = await Promise.race([
        voyagerGetProfile(liAt, jsessionid, publicId),
        new Promise((_, reject) => setTimeout(() => reject(new Error("TIMEOUT")), 10000)),
      ]);
      console.log("[Backfill] Got response for:", publicId);
      await _delay(RATE_LIMIT_DELAY_MS);

      // Log response structure to understand format
      const types = (raw?.included ?? []).map(i => i?.$type).filter(Boolean);
      console.log("[Backfill] Response included types:", types.length ? types.slice(0, 5) : "none, keys: " + Object.keys(raw || {}));

      // Extract the first profile from the normalized response
      const profileObj = (raw?.included ?? []).find(
        item => item?.$type === "com.linkedin.voyager.dash.identity.profile.Profile"
          || item?.$type === "com.linkedin.voyager.identity.shared.MiniProfile"
          || item?.$type?.includes("Profile")
      );

      if (profileObj) {
        console.log("[Backfill] Profile found:", profileObj?.$type, "avatar artifacts:", (profileObj?.profilePicture?.displayImageReference?.vectorImage?.artifacts ?? []).length);
        // Extract avatar URL from profilePicture.displayImageReference.vectorImage artifacts.
        // Dash format: profilePicture → displayImageReference → vectorImage → artifacts[]
        // Pick the largest artifact for best quality.
        let avatarUrl = null;
        const artifacts = profileObj?.profilePicture?.displayImageReference?.vectorImage?.artifacts ?? [];
        if (artifacts.length > 0) {
          // Artifacts are sorted smallest→largest; pick the last (largest)
          const largest = artifacts[artifacts.length - 1];
          const rootUrl = profileObj?.profilePicture?.displayImageReference?.vectorImage?.rootUrl ?? "";
          if (rootUrl && largest?.fileIdentifyingUrlPathSegment) {
            avatarUrl = rootUrl + largest.fileIdentifyingUrlPathSegment;
          }
        }

        // Location: prefer geoLocationName (human-readable), fall back to geo.defaultLocalizedName
        const location = profileObj?.geoLocationName
          ?? profileObj?.geo?.defaultLocalizedName
          ?? profileObj?.location?.basicLocation?.countryCode
          ?? null;

        profiles.push({
          profile_id: publicId,
          profile_url: `https://www.linkedin.com/in/${publicId}`,
          full_name: [profileObj?.firstName, profileObj?.lastName].filter(Boolean).join(" ") || null,
          headline: profileObj?.headline ?? null,
          company: profileObj?.position?.companyName ?? null,
          location,
          avatar_url: avatarUrl,
        });
        backfilled++;
      }
    } catch (e) {
      if (e.message === "RATE_LIMITED" || e.message === "AUTH_EXPIRED") break;
      console.warn("[PingCRM Voyager] Backfill failed for", publicId, e.message);
    }
  }

  if (profiles.length > 0) {
    try {
      await fetch(`${apiUrl}/api/v1/linkedin/push`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({ profiles, messages: [] }),
      });
    } catch (e) {
      console.warn("[PingCRM Voyager] Backfill push failed:", e.message);
    }
  }

  return backfilled;
}

// ── Error handler ─────────────────────────────────────────────────────────────

/**
 * Handle a Voyager-level error and update storage state accordingly.
 *
 * @param {Error} e
 * @param {Object} result - Mutable result object to annotate
 * @returns {Object} The annotated result
 */
async function _handleSyncError(e, result) {
  result.error = e.message;

  if (e.message === "RATE_LIMITED") {
    const waitMs = (e.retryAfter ?? 900) * 1000;
    const nextRetryAt = new Date(Date.now() + waitMs).toISOString();
    await chrome.storage.local.set({ nextRetryAt });
  } else if (e.message === "AUTH_EXPIRED") {
    await chrome.storage.local.set({ cookiesValid: false });
  }

  return result;
}
