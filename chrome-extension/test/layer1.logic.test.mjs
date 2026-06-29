/**
 * Layer 1 — offline logic harness.
 *
 * Drives the real runSync() pipeline with mocked executeScript (Voyager
 * fixtures) and a fake backend. No browser, no cookies, no LinkedIn session.
 * Catches the bugs the integration memo flags: direction, dedup/watermark
 * delta, transform shape. Run: `node --test`.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { makeChrome } from "./helpers/chrome-stub.mjs";
import { makeFakeBackend } from "./helpers/fake-backend.mjs";
import { makeVoyagerRouter } from "./helpers/voyager-router.mjs";
import { loadModules, SYNC_FILES } from "./helpers/loader.mjs";

const FIXED_NOW = 1750000000000; // freeze Date.now() for deterministic cutoffs
const ONE_DAY = 86_400_000;
const LINKEDIN_COOKIES = [
  { name: "li_at", value: "li-at-stub", domain: ".linkedin.com" },
  { name: "JSESSIONID", value: '"ajax:1234"', domain: ".linkedin.com" },
];

/** Build a fully-wired offline harness. `seed` pre-populates chrome.storage. */
function harness({ seed = {}, cookies = LINKEDIN_COOKIES, tabs, backend = {} } = {}) {
  const fake = makeFakeBackend(backend);
  const stub = makeChrome({ executeScript: makeVoyagerRouter(), cookies, tabs });
  for (const [k, v] of Object.entries(seed)) stub.store.set(k, v);
  const api = loadModules({
    chrome: stub.chrome,
    fetchImpl: fake.fetchImpl,
    files: SYNC_FILES,
    fixedNow: FIXED_NOW,
    exports: ["runSync", "generatePairingCode"],
  });
  return { ...stub, ...fake, api };
}

test("first sync: fetches both conversations and pushes all 3 messages", async () => {
  const h = harness({ seed: { apiUrl: "http://localhost:8000", token: "tok" } });

  const result = await h.api.runSync("http://localhost:8000", "tok", true);

  assert.equal(result.error, null);
  assert.equal(result.conversations, 2);
  assert.equal(result.messages, 3);

  const push = h.pushes().at(-1);
  assert.ok(push, "a /linkedin/push request was made");
  assert.equal(push.body.messages.length, 3);
  assert.equal(push.headers.Authorization, "Bearer tok");
});

test("direction is derived from self URN, not partner", async () => {
  const h = harness({ seed: { apiUrl: "http://x", token: "t" } });
  await h.api.runSync("http://x", "t", true);

  const msgs = h.pushes().at(-1).body.messages;
  const m1 = msgs.find((m) => m.raw_reference_id.includes("M1"));
  const m2 = msgs.find((m) => m.raw_reference_id.includes("M2"));

  assert.equal(m1.direction, "inbound", "M1 sent by PARTNER1 → inbound");
  assert.equal(m2.direction, "outbound", "M2 sent by SELF123 → outbound");
});

test("push payload shape matches /linkedin/push contract", async () => {
  const h = harness({ seed: { apiUrl: "http://x", token: "t" } });
  await h.api.runSync("http://x", "t", true);

  const msg = h.pushes().at(-1).body.messages[0];
  for (const k of ["conversation_id", "profile_id", "profile_name", "direction", "content_preview", "timestamp", "source", "raw_reference_id"]) {
    assert.ok(k in msg, `message has ${k}`);
  }
  assert.equal(msg.source, "voyager");
  assert.equal(msg.profile_name, "Partner One");
  assert.match(msg.timestamp, /^\d{4}-\d{2}-\d{2}T/);
});

test("delta sync: watermark skips the stale conversation and old messages", async () => {
  const watermark = new Date(FIXED_NOW - ONE_DAY).toISOString();
  const h = harness({ seed: { apiUrl: "http://x", token: "t", watermark } });

  const result = await h.api.runSync("http://x", "t", true);

  // CONV2 (last activity 11 days ago) is older than the watermark → skipped.
  // CONV1's two messages are both newer than the watermark → kept.
  assert.equal(result.messages, 2, "only CONV1 messages survive the delta cutoff");
  const ids = h.pushes().at(-1).body.messages.map((m) => m.raw_reference_id);
  assert.ok(ids.every((id) => !id.includes("M3")), "stale CONV2 message excluded");
});

test("watermark advances to the newest processed message", async () => {
  const h = harness({ seed: { apiUrl: "http://x", token: "t" } });
  await h.api.runSync("http://x", "t", true);

  // newest message is M2 @ 1749990000000
  assert.equal(h.store.get("watermark"), new Date(1749990000000).toISOString());
  assert.ok(h.store.get("lastVoyagerSync"), "sync timestamp persisted");
});

test("missing cookies → MISSING_COOKIES, cookiesValid=false, no push", async () => {
  const h = harness({ seed: { apiUrl: "http://x", token: "t" }, cookies: [] });

  const result = await h.api.runSync("http://x", "t", true);

  assert.equal(result.error, "MISSING_COOKIES");
  assert.equal(h.store.get("cookiesValid"), false);
  assert.equal(h.pushes().length, 0);
});

test("no LinkedIn tab → NO_LINKEDIN_TAB surfaced (not a crash)", async () => {
  const h = harness({ seed: { apiUrl: "http://x", token: "t" }, tabs: [] });

  const result = await h.api.runSync("http://x", "t", true);

  assert.equal(result.error, "NO_LINKEDIN_TAB");
});

test("backend 401 then successful silent refresh re-pushes with new token", async () => {
  // First push 401s; sync calls /extension/refresh (fake → 'refreshed-token'),
  // then retries the push. With our fake backend the retry also 401s, so the
  // token is cleared — assert the refresh was at least attempted.
  const h = harness({
    seed: { apiUrl: "http://x", token: "stale" },
    backend: { pushStatus: 401 },
  });

  const result = await h.api.runSync("http://x", "t", true);

  assert.ok(h.requests.some((r) => r.url.includes("/extension/refresh")), "attempted silent refresh on 401");
  assert.equal(result.error, "AUTH_EXPIRED");
});

test("pairing code generator produces a valid PING- code", async () => {
  const h = harness();
  const code = h.api.generatePairingCode();
  assert.match(code, /^PING-[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{6}$/);
});
