"use strict";

const express = require("express");
const config = require("./config");
const { createWebhookSender } = require("./webhook");
const SessionManager = require("./session-manager");
const buildRouter = require("./routes");

function log(level, msg, extra = {}) {
  process.stdout.write(
    JSON.stringify({ level, msg, ...extra, ts: new Date().toISOString() }) + "\n"
  );
}

const app = express();

// JSON body parser
app.use(express.json());

// Health check
app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "whatsapp-sidecar" });
});

// Wire up dependencies
const webhookSender = createWebhookSender(config.webhookUrl, config.webhookSecret);
const sessionManager = new SessionManager(webhookSender);
const sessionRouter = buildRouter(sessionManager);

// Mount routes
app.use("/sessions", sessionRouter);

// 404 fallback
app.use((_req, res) => {
  res.status(404).json({ error: "Not found" });
});

// Start server, then restore any persisted sessions
app.listen(config.port, () => {
  log("info", "whatsapp-sidecar started", {
    port: config.port,
    webhookUrl: config.webhookUrl,
    maxSessions: config.maxSessions,
    sessionDir: config.sessionDir,
  });

  // Restore sessions in the background — don't block the health check
  sessionManager.autoRestore().catch((err) => {
    log("error", "autoRestore error", { error: err.message });
  });
});

module.exports = app;
