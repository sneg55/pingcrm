"use strict";

const crypto = require("crypto");

/**
 * Compute HMAC-SHA256 hex digest of the given body string using secret.
 * @param {string} body - The raw JSON string to sign
 * @param {string} secret - The shared secret
 * @returns {string} hex digest
 */
function signPayload(body, secret) {
  return crypto.createHmac("sha256", secret).update(body).digest("hex");
}

/**
 * Create a webhook sender bound to a URL and secret.
 * @param {string} url - Destination URL for webhook POSTs
 * @param {string} secret - Shared HMAC secret
 * @returns {{ send: (event: string, data: object) => Promise<void> }}
 */
function createWebhookSender(url, secret) {
  return {
    async send(event, data) {
      const payload = JSON.stringify({ event, data, ts: Date.now() });
      const sig = signPayload(payload, secret);

      const log = (level, msg, extra = {}) =>
        process.stdout.write(
          JSON.stringify({ level, msg, event, ...extra, ts: new Date().toISOString() }) + "\n"
        );

      try {
        const res = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Webhook-Signature": sig,
          },
          body: payload,
        });

        if (!res.ok) {
          log("warn", "webhook delivery failed", { status: res.status });
        } else {
          log("info", "webhook delivered", { status: res.status });
        }
      } catch (err) {
        log("error", "webhook send error", { error: err.message });
      }
    },
  };
}

module.exports = { signPayload, createWebhookSender };
