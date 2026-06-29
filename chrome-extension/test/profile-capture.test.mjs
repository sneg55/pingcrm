/**
 * Tests for profile-visit capture (the avatar/company enrichment fix).
 *
 *  Layer 1 — _extractProfileFields against synthetic + real captured profiles.
 *  Layer 2 — the PROFILE_VISIT service-worker handler end to end (mocked Voyager
 *            + fake backend), asserting the enrich_only push carries company and
 *            the member_id needed to repair ACo-anonymized contacts.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeChrome } from "./helpers/chrome-stub.mjs";
import { makeFakeBackend } from "./helpers/fake-backend.mjs";
import { makeVoyagerRouter } from "./helpers/voyager-router.mjs";
import { loadModules, SYNC_FILES, SERVICE_WORKER_FILES } from "./helpers/loader.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXED_NOW = 1750000000000;
const COOKIES = [
  { name: "li_at", value: "li-at-stub", domain: ".linkedin.com" },
  { name: "JSESSIONID", value: '"ajax:1234"', domain: ".linkedin.com" },
];

// ── Layer 1: the extractor ───────────────────────────────────────────────────
function extractor() {
  const stub = makeChrome({ executeScript: async () => ({ ok: true, status: 200, data: {} }) });
  return loadModules({
    chrome: stub.chrome,
    fetchImpl: async () => ({ ok: true, json: async () => ({}) }),
    files: SYNC_FILES,
    exports: ["_extractProfileFields"],
  })._extractProfileFields;
}

test("_extractProfileFields pulls company from the current position", () => {
  const raw = JSON.parse(fs.readFileSync(path.join(HERE, "fixtures/voyager/profile.json"), "utf8"));
  const f = extractor()(raw);

  assert.equal(f.memberId, "ACoTESTMEMBER1");
  assert.equal(f.fullName, "Partner One");
  assert.equal(f.company, "Acme", "current position (no end date) wins over OldCo");
  assert.equal(f.headline, "COO at Acme");
  assert.equal(f.location, "San Francisco Bay Area");
  assert.equal(f.avatarUrl, "https://media.licdn.com/dms/image/test/800_800.jpg", "largest artifact");
});

test("_extractProfileFields returns null when no profile object present", () => {
  assert.equal(extractor()({ included: [] }), null);
});

const captured = path.join(HERE, "fixtures/voyager/_captured/profile-mattjlam.json");
test("_extractProfileFields handles real captured profile", { skip: !fs.existsSync(captured) && "no capture present" }, () => {
  const raw = JSON.parse(fs.readFileSync(captured, "utf8"));
  const f = extractor()(raw);
  assert.ok(f, "extracted a profile");
  assert.match(f.memberId, /^ACo/, "member id from URN");
  assert.ok(f.company, "a current company was resolved");
  assert.match(f.avatarUrl, /media\.licdn\.com/, "avatar url resolved");
});

// ── Layer 2: the PROFILE_VISIT handler ───────────────────────────────────────
function serviceWorker({ seed = {}, cookies = COOKIES } = {}) {
  const fake = makeFakeBackend();
  const stub = makeChrome({ executeScript: makeVoyagerRouter(), cookies });
  for (const [k, v] of Object.entries(seed)) stub.store.set(k, v);
  loadModules({
    chrome: stub.chrome,
    fetchImpl: fake.fetchImpl,
    files: SERVICE_WORKER_FILES,
    fixedNow: FIXED_NOW,
  });
  return { ...stub, ...fake };
}

test("PROFILE_VISIT enriches an existing contact with company + member_id", async () => {
  const sw = serviceWorker({ seed: { apiUrl: "http://localhost:8000", token: "tok" } });

  const resp = await sw.sendMessage({ type: "PROFILE_VISIT", slug: "mattjlam" });

  assert.equal(resp.ok, true);
  assert.equal(resp.company, "Acme");
  assert.equal(resp.avatar, true);

  const push = sw.pushes().at(-1);
  assert.ok(push, "pushed to /linkedin/push");
  assert.equal(push.body.enrich_only, true, "enrich-only so it never creates strangers");
  const p = push.body.profiles[0];
  assert.equal(p.profile_id, "mattjlam");
  assert.equal(p.member_id, "ACoTESTMEMBER1", "ACo id sent so backend can repair the contact");
  assert.equal(p.company, "Acme");
  assert.equal(p.profile_url, "https://www.linkedin.com/in/mattjlam");
  assert.ok(p.avatar_data, "avatar bytes attached");
});

test("PROFILE_VISIT rejects ACo member-id slugs (no usable public slug)", async () => {
  const sw = serviceWorker({ seed: { apiUrl: "http://x", token: "t" } });
  const resp = await sw.sendMessage({ type: "PROFILE_VISIT", slug: "ACoAAAFS80wB" });
  assert.equal(resp.ok, false);
  assert.equal(resp.error, "NO_SLUG");
  assert.equal(sw.pushes().length, 0);
});

test("PROFILE_VISIT is throttled per slug", async () => {
  const sw = serviceWorker({ seed: { apiUrl: "http://x", token: "t" } });

  const first = await sw.sendMessage({ type: "PROFILE_VISIT", slug: "mattjlam" });
  const second = await sw.sendMessage({ type: "PROFILE_VISIT", slug: "mattjlam" });

  assert.equal(first.ok, true);
  assert.equal(second.throttled, true);
  assert.equal(sw.pushes().length, 1, "second visit within window does not re-push");
});

test("PROFILE_VISIT requires pairing", async () => {
  const sw = serviceWorker(); // empty store
  const resp = await sw.sendMessage({ type: "PROFILE_VISIT", slug: "mattjlam" });
  assert.equal(resp.ok, false);
  assert.equal(resp.error, "Not paired");
  assert.equal(sw.pushes().length, 0);
});
