"use strict";

const { Client, LocalAuth } = require("whatsapp-web.js");
const path = require("path");
const fs = require("fs");
const config = require("./config");

/**
 * Structured JSON logger — never logs phone numbers.
 */
function log(level, msg, extra = {}) {
  process.stdout.write(
    JSON.stringify({ level, msg, ...extra, ts: new Date().toISOString() }) + "\n"
  );
}

/**
 * Manages per-userId whatsapp-web.js Client instances.
 */
class SessionManager {
  /**
   * @param {{ send: (event: string, data: object) => Promise<void> }} webhookSender
   */
  constructor(webhookSender) {
    this._webhook = webhookSender;
    /** @type {Map<string, { client: Client, status: string, qr: string|null }>} */
    this._sessions = new Map();
  }

  /**
   * Scan the session directory and restore any previously-authenticated sessions.
   * Called once on startup so sessions survive container restarts.
   */
  async autoRestore() {
    const sessionDir = path.resolve(config.sessionDir);
    let entries;
    try {
      entries = fs.readdirSync(sessionDir, { withFileTypes: true });
    } catch {
      return;
    }

    const prefix = "session-";
    const userIds = entries
      .filter((e) => e.isDirectory() && e.name.startsWith(prefix))
      .map((e) => e.name.slice(prefix.length));

    if (userIds.length === 0) return;

    log("info", "auto-restoring sessions", { count: userIds.length });

    for (const userId of userIds) {
      try {
        await this.startSession(userId);
        log("info", "auto-restore initiated", { userId });
      } catch (err) {
        log("warn", "auto-restore failed", { userId, error: err.message });
      }
    }
  }

  /**
   * Start a WhatsApp session for the given userId.
   * Returns a promise that resolves once the client is initialised
   * (QR may still be pending at that point).
   * @param {string} userId
   */
  async startSession(userId) {
    const existing = this._sessions.get(userId);
    if (existing) {
      // If session is active (connected, authenticating, or awaiting QR scan), keep it
      if (existing.status === "connected" || existing.status === "authenticated" || existing.status === "qr_pending") {
        log("info", "session already active", { userId, status: existing.status });
        return;
      }
      // Otherwise destroy the stale session and recreate
      log("info", "destroying stale session", { userId, status: existing.status });
      await this.destroySession(userId);
    }

    if (this._sessions.size >= config.maxSessions) {
      throw new Error(`Max sessions (${config.maxSessions}) reached`);
    }

    log("info", "starting session", { userId });

    // Clean up stale Chromium lock files from previous container restarts
    const profileDir = path.resolve(config.sessionDir, `session-${userId}`);
    for (const lockFile of ["SingletonLock", "SingletonSocket", "SingletonCookie"]) {
      const lockPath = path.join(profileDir, lockFile);
      try { fs.unlinkSync(lockPath); } catch { /* doesn't exist, fine */ }
    }

    const client = new Client({
      authStrategy: new LocalAuth({
        clientId: userId,
        dataPath: path.resolve(config.sessionDir),
      }),
      puppeteer: {
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
        args: [
          "--no-sandbox",
          "--disable-setuid-sandbox",
          "--disable-dev-shm-usage",
          "--disable-gpu",
        ],
        headless: true,
      },
    });

    const state = { client, status: "initializing", qr: null };
    this._sessions.set(userId, state);

    client.on("qr", (qr) => {
      state.qr = qr;
      state.status = "qr_pending";
      log("info", "QR code received", { userId });
    });

    client.on("authenticated", () => {
      state.status = "authenticated";
      state.qr = null;
      log("info", "session authenticated", { userId });
    });

    client.on("ready", () => {
      state.status = "connected";
      log("info", "session ready", { userId });
      this._webhook.send("session_connected", { userId }).catch(() => {});
    });

    client.on("disconnected", (reason) => {
      state.status = "disconnected";
      log("info", "session disconnected", { userId, reason });
      this._webhook.send("session_disconnected", { userId }).catch(() => {});
      this._sessions.delete(userId);
    });

    client.on("message", (msg) => {
      this._handleMessage(userId, msg).catch((err) => {
        log("error", "message handler error", { userId, error: err.message });
      });
    });

    await client.initialize();
  }

  /**
   * Handle an incoming WhatsApp message — skips group and status messages.
   * Never logs phone numbers.
   * @param {string} userId
   * @param {import("whatsapp-web.js").Message} msg
   */
  async _handleMessage(userId, msg) {
    // Skip group messages
    if (msg.isGroupMsg) return;
    // Skip status broadcasts
    if (msg.from === "status@broadcast") return;

    const chat = await msg.getChat();
    const chatId = chat.id._serialized;

    log("info", "message_received", { userId, chatId });

    // Resolve real phone — LID chats don't have phone in the ID
    let phone = "";
    if (chatId.endsWith("@c.us")) {
      phone = chat.id.user;
    } else {
      // Try to get phone from the contact object
      const contact = await msg.getContact().catch(() => null);
      phone = contact?.number || chat.id.user || "";
    }
    if (!phone || phone === "0") return;

    await this._webhook.send("message_received", {
      userId,
      message_id: msg.id._serialized,
      from: phone,
      sender_name: chat.name || "",
      direction: msg.fromMe ? "outbound" : "inbound",
      body: msg.body,
      type: msg.type,
      timestamp: msg.timestamp,
    });
  }

  /**
   * Return the current QR code string for a session, or null.
   * @param {string} userId
   * @returns {string|null}
   */
  getQr(userId) {
    return this._sessions.get(userId)?.qr ?? null;
  }

  /**
   * Return the current status string for a session.
   * @param {string} userId
   * @returns {string|null}
   */
  getStatus(userId) {
    return this._sessions.get(userId)?.status ?? null;
  }

  /**
   * Fetch the WhatsApp contacts from a ready session.
   * @param {string} userId
   * @returns {Promise<Array<{ id: string, name: string, pushname: string, isMyContact: boolean }>>}
   */
  async getContacts(userId) {
    const state = this._sessions.get(userId);
    if (!state || state.status !== "connected") {
      throw new Error(`Session not ready for userId ${userId}`);
    }

    const contacts = await state.client.getContacts();
    log("info", "fetched contacts", { userId, count: contacts.length });

    return contacts
      .filter((c) => !c.isGroup && !c.isMe)
      .map((c) => ({
        id: c.id._serialized,
        name: c.name || c.pushname || "",
        pushname: c.pushname || "",
        isMyContact: c.isMyContact,
      }));
  }

  /**
   * Backfill recent chats, streaming batches to the webhook.
   * @param {string} userId
   * @param {{ daysBack?: number, batchSize?: number }} options
   */
  async backfill(userId, { daysBack = 30, batchSize = 50 } = {}) {
    const state = this._sessions.get(userId);
    if (!state || state.status !== "connected") {
      throw new Error(`Session not ready for userId ${userId}`);
    }

    const cutoff = Date.now() / 1000 - daysBack * 86400;
    log("info", "backfill started", { userId, daysBack, batchSize });

    // Extract messages directly from WhatsApp Web's internal Store.
    // chat.fetchMessages() is broken in current WhatsApp Web (missing
    // waitForChatLoading), so we bypass it entirely.
    const pupPage = state.client.pupPage;

    const allMessages = await pupPage.evaluate((cutoffTs) => {
      try {
        const store = window.Store;
        if (!store) return { error: "window.Store not available" };

        // Diagnostic: discover what's in the Store
        const storeKeys = Object.keys(store).slice(0, 30);
        const hasChat = !!store.Chat;
        const hasMsg = !!store.Msg;

        if (!hasChat) return { error: "Store.Chat missing", storeKeys };

        const chats = store.Chat.getModelsArray ? store.Chat.getModelsArray() : [];
        const chatDiag = chats.slice(0, 5).map((c) => ({
          id: c.id?._serialized,
          name: c.name || c.formattedTitle || "",
          isGroup: c.isGroup,
          msgCount: c.msgs?.getModelsArray ? c.msgs.getModelsArray().length : -1,
        }));

        // Build a LID → phone lookup from Store.Contact
        const phoneLookup = {};
        const lidDiag = []; // diagnostic for first few LID contacts
        if (store.Contact) {
          const contacts = store.Contact.getModelsArray ? store.Contact.getModelsArray() : [];
          for (const ct of contacts) {
            const ctId = ct.id?._serialized || "";
            // Try multiple fields for the phone number.
            // For LID contacts, userid is an object {server, user, _serialized}
            const useridPhone = ct.userid?.user || (typeof ct.userid === "string" ? ct.userid : "");
            const phone = ct.phoneNumber || ct.number || useridPhone
              || (ctId.endsWith("@c.us") ? ctId.replace(/@c\.us$/, "") : "");
            if (phone && ctId) phoneLookup[ctId] = phone;

            // Diagnostic: dump properties of LID contacts
            if (ctId.endsWith("@lid") && lidDiag.length < 3) {
              const keys = Object.keys(ct).filter((k) => !k.startsWith("_")).slice(0, 20);
              lidDiag.push({ id: ctId, name: ct.name || ct.pushname || "", phone, keys });
            }
          }
        }

        // Also try to resolve via Store.Lid if available
        if (store.Lid) {
          const lids = store.Lid.getModelsArray ? store.Lid.getModelsArray() : [];
          for (const l of lids) {
            const lid = l.id?._serialized || l.lid?._serialized || "";
            const phone = l.phoneNumber || l.number || l.user || "";
            if (lid && phone && !phoneLookup[lid]) phoneLookup[lid] = phone;
          }
        }

        const results = [];

        for (const chat of chats) {
          if (chat.isGroup) continue;

          const chatId = chat.id?._serialized || "";
          const chatName = chat.name || chat.formattedTitle || "";

          // Resolve real phone: try contact lookup, then chat.contact, then parse chatId
          let phone = phoneLookup[chatId] || "";
          if (!phone && chat.contact) {
            phone = chat.contact.phoneNumber || "";
          }
          if (!phone && chatId.endsWith("@c.us")) {
            phone = chatId.replace(/@c\.us$/, "");
          }
          // Skip chats where we can't resolve a phone number (e.g. 0@c.us)
          if (!phone || phone === "0") continue;

          const msgModels = chat.msgs?.getModelsArray ? chat.msgs.getModelsArray() : [];

          for (const msg of msgModels) {
            if ((msg.t || 0) < cutoffTs) continue;
            if (msg.type !== "chat") continue;

            results.push({
              message_id: msg.id?._serialized || "",
              chatId,
              chatName,
              phone,
              fromMe: !!msg.id?.fromMe,
              body: msg.body || "",
              type: msg.type,
              timestamp: msg.t || 0,
            });
          }
        }
        return { messages: results, diag: { storeKeys, hasChat, hasMsg, chatCount: chats.length, chatDiag, phoneLookupSize: Object.keys(phoneLookup).length, hasLidStore: !!store.Lid, lidDiag } };
      } catch (err) {
        return { error: err.message, stack: err.stack?.split("\n").slice(0, 3) };
      }
    }, cutoff).catch((err) => ({ error: `evaluate failed: ${err.message}` }));

    if (allMessages.error) {
      log("error", "backfill: Store extraction failed", { userId, error: allMessages.error, storeKeys: allMessages.storeKeys });
      await this._webhook.send("backfill_complete", { userId });
      return;
    }

    const messages = allMessages.messages || [];
    if (allMessages.diag) {
      log("info", "backfill: Store diagnostics", { userId, ...allMessages.diag });
    }
    log("info", "backfill: extracted messages from Store", { userId, count: messages.length });

    let batch = [];
    let totalMessages = 0;

    for (const msg of messages) {
      batch.push({
        message_id: msg.message_id,
        from: msg.phone,
        sender_name: msg.chatName,
        direction: msg.fromMe ? "outbound" : "inbound",
        body: msg.body,
        type: msg.type,
        timestamp: msg.timestamp,
      });

      if (batch.length >= batchSize) {
        await this._webhook.send("backfill_batch", { userId, messages: batch });
        totalMessages += batch.length;
        log("info", "backfill batch sent", { userId, batchSize: batch.length, totalMessages });
        batch = [];
      }
    }

    if (batch.length > 0) {
      await this._webhook.send("backfill_batch", { userId, messages: batch });
      totalMessages += batch.length;
      log("info", "backfill batch sent", { userId, batchSize: batch.length, totalMessages });
    }

    await this._webhook.send("backfill_complete", { userId });
    log("info", "backfill complete", { userId, totalMessages });
  }

  /**
   * Destroy a session and clean up resources.
   * @param {string} userId
   */
  async destroySession(userId) {
    const state = this._sessions.get(userId);
    if (!state) {
      log("warn", "destroySession: no session found", { userId });
      return;
    }

    log("info", "destroying session", { userId });

    try {
      await state.client.destroy();
    } catch (err) {
      log("warn", "destroySession: client.destroy() error", { userId, error: err.message });
    }

    this._sessions.delete(userId);
    log("info", "session destroyed", { userId });
  }
}

module.exports = SessionManager;
