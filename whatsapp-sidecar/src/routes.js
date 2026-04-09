"use strict";

const { Router } = require("express");

/**
 * Build the sessions router.
 * @param {import("./session-manager")} sessionManager
 * @returns {Router}
 */
function buildRouter(sessionManager) {
  const router = Router();

  function log(level, msg, extra = {}) {
    process.stdout.write(
      JSON.stringify({ level, msg, ...extra, ts: new Date().toISOString() }) + "\n"
    );
  }

  // POST /sessions/:userId/start — start session, wait up to 2s for QR, return {status, qr}
  router.post("/:userId/start", async (req, res) => {
    const { userId } = req.params;
    log("info", "POST start session", { userId });

    try {
      // Fire off session start without awaiting full init (it blocks until Puppeteer is ready)
      const startPromise = sessionManager.startSession(userId);

      // Wait up to 2 seconds for a QR code to appear or session to become ready
      await Promise.race([
        startPromise,
        new Promise((resolve) => setTimeout(resolve, 2000)),
      ]);

      const status = sessionManager.getStatus(userId) || "initializing";
      const qr = sessionManager.getQr(userId);

      return res.status(202).json({ status, qr });
    } catch (err) {
      log("error", "start session error", { userId, error: err.message });
      return res.status(500).json({ error: err.message });
    }
  });

  // GET /sessions/:userId/qr — get current QR string (rendered by frontend)
  router.get("/:userId/qr", (req, res) => {
    const { userId } = req.params;

    const qr = sessionManager.getQr(userId);
    if (!qr) {
      const status = sessionManager.getStatus(userId);
      if (!status) {
        return res.status(404).json({ error: "Session not found" });
      }
      return res.status(200).json({ qr: null, status });
    }

    return res.status(200).json({ qr, status: "qr_pending" });
  });

  // GET /sessions/:userId/status — get session status
  router.get("/:userId/status", (req, res) => {
    const { userId } = req.params;
    const status = sessionManager.getStatus(userId);

    if (status === null) {
      return res.status(404).json({ error: "Session not found" });
    }

    return res.status(200).json({ userId, status });
  });

  // POST /sessions/:userId/backfill — trigger backfill (async, responds immediately)
  router.post("/:userId/backfill", async (req, res) => {
    const { userId } = req.params;
    const { daysBack = 30, batchSize = 50 } = req.body || {};

    const status = sessionManager.getStatus(userId);
    if (status !== "connected") {
      return res.status(400).json({ error: `Session not ready (status: ${status || "not found"})` });
    }

    log("info", "backfill triggered", { userId, daysBack, batchSize });

    // Run backfill asynchronously — don't block the response
    sessionManager.backfill(userId, { daysBack, batchSize }).catch((err) => {
      log("error", "backfill error", { userId, error: err.message });
    });

    return res.status(202).json({ message: "Backfill started", userId, daysBack, batchSize });
  });

  // GET /sessions/:userId/contacts — list contacts
  router.get("/:userId/contacts", async (req, res) => {
    const { userId } = req.params;

    try {
      const contacts = await sessionManager.getContacts(userId);
      return res.status(200).json({ userId, contacts, count: contacts.length });
    } catch (err) {
      log("error", "getContacts error", { userId, error: err.message });
      return res.status(400).json({ error: err.message });
    }
  });

  // DELETE /sessions/:userId — destroy session
  router.delete("/:userId", async (req, res) => {
    const { userId } = req.params;
    log("info", "DELETE session", { userId });

    try {
      await sessionManager.destroySession(userId);
      return res.status(200).json({ message: "Session destroyed", userId });
    } catch (err) {
      log("error", "destroySession error", { userId, error: err.message });
      return res.status(500).json({ error: err.message });
    }
  });

  return router;
}

module.exports = buildRouter;
