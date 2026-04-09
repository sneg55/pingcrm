"use strict";

const { Client, LocalAuth } = require("whatsapp-web.js");
const path = require("path");
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
   * Start a WhatsApp session for the given userId.
   * Returns a promise that resolves once the client is initialised
   * (QR may still be pending at that point).
   * @param {string} userId
   */
  async startSession(userId) {
    if (this._sessions.has(userId)) {
      log("info", "session already exists", { userId });
      return;
    }

    if (this._sessions.size >= config.maxSessions) {
      throw new Error(`Max sessions (${config.maxSessions}) reached`);
    }

    log("info", "starting session", { userId });

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
      this._webhook.send("qr", { userId, qr }).catch(() => {});
    });

    client.on("authenticated", () => {
      state.status = "authenticated";
      state.qr = null;
      log("info", "session authenticated", { userId });
      this._webhook.send("authenticated", { userId }).catch(() => {});
    });

    client.on("ready", () => {
      state.status = "ready";
      log("info", "session ready", { userId });
      this._webhook.send("ready", { userId }).catch(() => {});
    });

    client.on("disconnected", (reason) => {
      state.status = "disconnected";
      log("info", "session disconnected", { userId, reason });
      this._webhook.send("disconnected", { userId, reason }).catch(() => {});
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

    log("info", "message_received", { userId, chatId: chat.id._serialized });

    await this._webhook.send("message_received", {
      userId,
      messageId: msg.id._serialized,
      chatId: chat.id._serialized,
      chatName: chat.name,
      fromMe: msg.fromMe,
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
    if (!state || state.status !== "ready") {
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
    if (!state || state.status !== "ready") {
      throw new Error(`Session not ready for userId ${userId}`);
    }

    const cutoff = Date.now() / 1000 - daysBack * 86400;
    log("info", "backfill started", { userId, daysBack, batchSize });

    const chats = await state.client.getChats();
    const directChats = chats.filter((c) => !c.isGroup);

    let batch = [];
    let totalMessages = 0;

    for (const chat of directChats) {
      let messages;
      try {
        messages = await chat.fetchMessages({ limit: 100 });
      } catch (err) {
        log("warn", "backfill: failed to fetch messages for chat", {
          userId,
          chatId: chat.id._serialized,
          error: err.message,
        });
        continue;
      }

      const recent = messages.filter((m) => m.timestamp >= cutoff);

      for (const msg of recent) {
        batch.push({
          messageId: msg.id._serialized,
          chatId: chat.id._serialized,
          chatName: chat.name,
          fromMe: msg.fromMe,
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
    }

    // Send remaining messages
    if (batch.length > 0) {
      await this._webhook.send("backfill_batch", { userId, messages: batch });
      totalMessages += batch.length;
      log("info", "backfill batch sent", { userId, batchSize: batch.length, totalMessages });
    }

    await this._webhook.send("backfill_complete", { userId, totalMessages });
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
