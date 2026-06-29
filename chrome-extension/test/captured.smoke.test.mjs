/**
 * Layer 1.5 — run REAL captured Voyager data through the actual parsers.
 *
 * Bridges Layers 1 and 3: when a `--capture` run has produced
 * fixtures/voyager/_captured/, this asserts the shipping parsers
 * (_parseConversations / _parseParticipants / _parseMessages / _eventToMessage)
 * still handle LinkedIn's *current* schema — i.e. the synthetic fixtures
 * haven't drifted from reality.
 *
 * Skips automatically when no capture exists (e.g. in CI), so it never blocks
 * the offline suite.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeChrome } from "./helpers/chrome-stub.mjs";
import { loadModules, SYNC_FILES } from "./helpers/loader.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CAP = path.join(HERE, "fixtures/voyager/_captured");
const hasCapture = fs.existsSync(path.join(CAP, "conversations.page1.json"));

test("captured LinkedIn data parses into valid push messages", { skip: !hasCapture && "no capture present (run: npm run capture)" }, () => {
  const convs = JSON.parse(fs.readFileSync(path.join(CAP, "conversations.page1.json"), "utf8"));
  const selfUrn = JSON.parse(fs.readFileSync(path.join(CAP, "self-urn.json"), "utf8")).selfUrn;

  const stub = makeChrome({ executeScript: async () => ({ ok: true, status: 200, data: {} }) });
  const api = loadModules({
    chrome: stub.chrome,
    fetchImpl: async () => ({ ok: true, json: async () => ({}) }),
    files: SYNC_FILES,
    exports: ["_parseConversations", "_parseParticipants", "_parseMessages", "_eventToMessage"],
  });

  const els = api._parseConversations(convs);
  assert.ok(els.length > 0, "real conversations parsed");

  const selfSuffix = selfUrn.split(":").pop();
  let total = 0;
  let named = 0;
  for (const conv of els) {
    const parts = api._parseParticipants(conv);
    const other = parts.find((p) => (p.profileUrn || "").split(":").pop() !== selfSuffix) || parts[0];
    const pubId = other?.publicIdentifier;
    const name = [other?.firstName, other?.lastName].filter(Boolean).join(" ") || conv?.title?.text || pubId || "Unknown";
    const events = api._parseMessages({ data: { messengerMessages: { elements: conv?.messages?.elements ?? [] } } });
    for (const ev of events) {
      const m = api._eventToMessage(ev, conv.entityUrn, pubId, name, selfSuffix);
      total++;
      if (m.profile_name && m.profile_name !== "Unknown") named++;
      assert.ok(["inbound", "outbound"].includes(m.direction), "valid direction");
      assert.equal(m.source, "voyager");
      assert.ok(m.timestamp && !Number.isNaN(Date.parse(m.timestamp)), "valid ISO timestamp");
      assert.ok(m.conversation_id, "has conversation_id");
    }
  }
  assert.ok(total > 0, "at least one real message parsed");
  // Most threads should resolve a human name; allow a few group/anonymized ones.
  assert.ok(named / total >= 0.6, `name resolution healthy (${named}/${total})`);
});
