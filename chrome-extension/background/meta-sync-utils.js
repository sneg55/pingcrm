/**
 * Shared utilities for Meta sync: constants, cookie helpers,
 * response parsers.
 *
 * Loaded via importScripts before sync-facebook.js / sync-instagram.js.
 */

// ── Constants ────────────────────────────────────────────────────────────────

const META_SYNC_THROTTLE_MS = 15 * 60 * 1000;       // 15 min between auto-syncs
const META_RATE_LIMIT_DELAY_MS = 1000;                // 1 sec between GraphQL calls
const META_BACKFILL_WINDOW_MS = 30 * 24 * 60 * 60 * 1000; // 30 days for first sync
const META_CONVERSATION_MAX = 50;                     // max conversations per sync cycle
const META_MESSAGES_PER_CONV_MAX = 100;               // max messages per conversation

// ── Cookie helpers ───────────────────────────────────────────────────────────

async function _readMetaCookies() {
  const cookies = await chrome.cookies.getAll({ domain: ".facebook.com" });
  const map = Object.fromEntries(cookies.map(c => [c.name, c.value]));
  const cUser = map["c_user"];
  const xs = map["xs"];
  if (!cUser || !xs) throw new Error("MISSING_META_COOKIES");
  return { cUser, xs };
}

// ── Delay helper ─────────────────────────────────────────────────────────────

function _metaDelay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ── Stable hash for sidebar snippets ─────────────────────────────────────────
// Sidebar scrapes don't expose real message IDs, so derive a stable key from
// the snippet itself. Re-syncs of the same snippet produce the same key,
// letting the backend's raw_reference_id dedup catch them.

async function _metaSnippetHash(text) {
  const bytes = new TextEncoder().encode(String(text ?? ""));
  const buf = await crypto.subtle.digest("SHA-1", bytes);
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
}

// ── Messenger parsers ────────────────────────────────────────────────────────

function _parseMetaConversations(raw) {
  const threads = raw?.data?.viewer?.message_threads?.nodes ?? [];
  if (threads.length > 0) return threads;
  const edges = raw?.data?.viewer?.message_threads?.edges ?? [];
  return edges.map(e => e.node).filter(Boolean);
}

function _parseMetaMessages(raw) {
  const nodes = raw?.data?.message_thread?.messages?.nodes ?? [];
  if (nodes.length > 0) return nodes;
  const edges = raw?.data?.message_thread?.messages?.edges ?? [];
  return edges.map(e => e.node).filter(Boolean);
}

function _metaMessageToPayload(msg, conversationId, partnerId, partnerName, selfUserId) {
  const text = msg?.snippet ?? msg?.message?.text ?? msg?.body ?? "";
  const timestamp = msg?.timestamp_precise
    ? new Date(parseInt(msg.timestamp_precise)).toISOString()
    : new Date(msg?.timestamp ?? Date.now()).toISOString();

  const senderId = msg?.message_sender?.id ?? msg?.sender?.id ?? null;
  const direction = senderId === selfUserId ? "outbound" : "inbound";

  const reactions = (msg?.message_reactions ?? []).map(r => ({
    reactor_id: r?.user?.id ?? "",
    type: r?.reaction ?? "like",
  }));

  const readBy = (msg?.read_receipts?.nodes ?? []).map(r => r?.user?.id).filter(Boolean);

  return {
    message_id: msg?.message_id ?? `${conversationId}:${msg?.timestamp_precise ?? Date.now()}`,
    conversation_id: conversationId,
    platform_id: partnerId,
    sender_name: partnerName ?? partnerId ?? "",
    direction,
    content_preview: String(text).substring(0, 500),
    timestamp,
    reactions,
    read_by: readBy,
  };
}

// ── Instagram DM parsers ─────────────────────────────────────────────────────

function _parseInstagramThreads(raw) {
  const threads = raw?.data?.viewer?.inbox?.threads?.nodes ?? [];
  if (threads.length > 0) return threads;
  const edges = raw?.data?.viewer?.inbox?.threads?.edges ?? [];
  return edges.map(e => e.node).filter(Boolean);
}

function _parseInstagramMessages(raw) {
  const items = raw?.data?.message_thread?.messages?.nodes
    ?? raw?.data?.xdt_message_thread?.messages?.nodes
    ?? [];
  if (items.length > 0) return items;
  const edges = raw?.data?.message_thread?.messages?.edges
    ?? raw?.data?.xdt_message_thread?.messages?.edges
    ?? [];
  return edges.map(e => e.node).filter(Boolean);
}

function _igMessageToPayload(msg, conversationId, partnerId, partnerName, selfUserId) {
  const text = msg?.text ?? msg?.message?.text ?? "";
  const timestamp = msg?.timestamp
    ? new Date(parseInt(msg.timestamp) / 1000).toISOString()
    : new Date().toISOString();

  const senderId = msg?.sender?.id ?? msg?.user_id ?? null;
  const direction = senderId === selfUserId ? "outbound" : "inbound";

  const reactions = (msg?.reactions ?? []).map(r => ({
    reactor_id: r?.user?.id ?? r?.sender_id ?? "",
    type: r?.emoji ?? r?.reaction ?? "like",
  }));

  const seenBy = (msg?.seen_by ?? []).map(u => u?.id ?? u).filter(Boolean);

  return {
    message_id: msg?.item_id ?? msg?.message_id ?? `ig:${conversationId}:${Date.now()}`,
    conversation_id: conversationId,
    platform_id: partnerId,
    sender_name: partnerName ?? partnerId ?? "",
    direction,
    content_preview: String(text).substring(0, 500),
    timestamp,
    reactions,
    read_by: seenBy,
  };
}

// ── Error handler ────────────────────────────────────────────────────────────

async function _handleMetaSyncError(e, result) {
  result.error = e.message;

  if (e.message === "RATE_LIMITED") {
    const waitMs = (e.retryAfter ?? 900) * 1000;
    const nextRetryAt = new Date(Date.now() + waitMs).toISOString();
    await chrome.storage.local.set({ metaNextRetryAt: nextRetryAt });
  } else if (e.message === "NO_META_TAB") {
    console.warn("[MetaSync] No Facebook/Instagram tab open");
  } else if (e.message === "AUTH_EXPIRED") {
    try {
      await _readMetaCookies();
      console.warn("[MetaSync] GraphQL auth rejected but cookies present");
      result.error = "META_AUTH_REJECTED";
    } catch {
      await chrome.storage.local.set({ metaCookiesValid: false });
    }
  }

  return result;
}
