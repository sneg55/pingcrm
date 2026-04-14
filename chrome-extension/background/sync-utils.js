/**
 * Shared utilities for Voyager sync: constants, cookie helpers, response
 * parsers, and error handling.
 *
 * Loaded via importScripts before sync.js — all exports are globals.
 */

// ── Constants ────────────────────────────────────────────────────────────────

const SYNC_THROTTLE_MS = 15 * 60 * 1000; // 15 minutes between auto-syncs
const RATE_LIMIT_DELAY_MS = 1000;             // 1 second between Voyager calls
const BACKFILL_WINDOW_MS = 30 * 24 * 60 * 60 * 1000; // 30 days for first-sync full fetch
const CONVERSATION_PAGE_MAX = 500;            // hard cap to prevent infinite pagination

// ── Cookie helpers ───────────────────────────────────────────────────────────

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

// ── Delay helper ─────────────────────────────────────────────────────────────

function _delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ── Voyager response parsers ─────────────────────────────────────────────────

/**
 * Parse conversations from GraphQL messengerConversations response.
 * Response shape: data.messengerConversationsBySyncToken.elements[]
 * or data.messengerConversations.elements[]
 */
function _parseConversations(raw) {
  // GraphQL: data -> messengerConversationsBySyncToken -> elements
  const bySyncToken = raw?.data?.messengerConversationsBySyncToken?.elements ?? [];
  if (bySyncToken.length > 0) return bySyncToken;

  // GraphQL alt: data -> messengerConversations -> elements
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
function _eventToMessage(msg, conversationUrn, partnerPublicId, partnerName, selfUrnSuffix) {
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

  // Direction: compare sender identity to the logged-in user (self), not to the
  // conversation partner. The sender-vs-partner comparison was fragile — when
  // publicIdentifier was null (ACo-anonymized profiles) or when partner
  // resolution picked the wrong participant, every message in the thread got
  // flipped to the opposite side. Matching against the stable self URN
  // decouples direction from partner identification.
  const senderUrn = msg?.sender?.hostIdentityUrn ?? sender?.entityUrn ?? null;
  const senderUrnSuffix = senderUrn ? senderUrn.split(":").pop() : null;
  const senderPublicId = sender?.publicIdentifier ?? null;

  let isFromSelf;
  if (selfUrnSuffix && senderUrnSuffix) {
    isFromSelf = senderUrnSuffix === selfUrnSuffix;
  } else {
    isFromSelf = !!(senderPublicId && partnerPublicId && senderPublicId !== partnerPublicId);
  }

  return {
    conversation_id: conversationUrn,
    profile_id: partnerPublicId,
    profile_name: partnerName ?? partnerPublicId ?? "",
    direction: isFromSelf ? "outbound" : "inbound",
    content_preview: String(text).substring(0, 500),
    timestamp: createdAt ? new Date(createdAt).toISOString() : new Date().toISOString(),
    source: "voyager",
    raw_reference_id: `linkedin:voyager:${msg?.entityUrn ?? msg?.backendUrn ?? ""}`,
  };
}

// ── Error handler ────────────────────────────────────────────────────────────

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
  } else if (e.message === "NO_LINKEDIN_TAB" || e.message === "PROXY_NO_RESPONSE") {
    console.warn("[Sync] No LinkedIn tab open — open linkedin.com and try again");
  } else if (e.message === "AUTH_EXPIRED") {
    // Verify cookies are actually gone before marking session expired.
    // A 401/403 from LinkedIn can happen for reasons other than session expiry
    // (API changes, CSRF mismatch, rate-limiting disguised as 403).
    try {
      await _readLinkedInCookies();
      // Cookies still exist — this is an API error, not a session expiry
      console.warn("[Sync] Voyager returned 401/403 but cookies are still present — not marking session expired");
      result.error = "VOYAGER_AUTH_REJECTED";
    } catch {
      // Cookies are actually gone — mark session as expired
      await chrome.storage.local.set({ cookiesValid: false });
    }
  }

  return result;
}
