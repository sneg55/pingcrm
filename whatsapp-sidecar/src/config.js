"use strict";
const config = {
  port: parseInt(process.env.PORT || "3001", 10),
  webhookUrl: process.env.WEBHOOK_URL || "http://localhost:8000/api/v1/webhooks/whatsapp",
  webhookSecret: process.env.WEBHOOK_SECRET || "dev-secret",
  sessionDir: process.env.SESSION_DIR || "./data/sessions",
  maxSessions: parseInt(process.env.MAX_SESSIONS || "50", 10),
};
module.exports = config;
