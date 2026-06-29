/**
 * Layer 2 — full message-router harness.
 *
 * Loads the REAL service-worker.js (and everything it importScripts) and drives
 * it by dispatching the same message objects the popup sends — SYNC_NOW,
 * START_PAIRING, DISCONNECT — observing outgoing fetches and badge updates.
 * This exercises the actual router + module wiring, not a reimplementation.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { makeChrome } from "./helpers/chrome-stub.mjs";
import { makeFakeBackend } from "./helpers/fake-backend.mjs";
import { makeVoyagerRouter } from "./helpers/voyager-router.mjs";
import { loadModules, SERVICE_WORKER_FILES } from "./helpers/loader.mjs";

const FIXED_NOW = 1750000000000;
const LINKEDIN_COOKIES = [
  { name: "li_at", value: "li-at-stub", domain: ".linkedin.com" },
  { name: "JSESSIONID", value: '"ajax:1234"', domain: ".linkedin.com" },
];

function serviceWorker({ seed = {}, cookies = LINKEDIN_COOKIES, tabs, backend = {} } = {}) {
  const fake = makeFakeBackend(backend);
  const stub = makeChrome({ executeScript: makeVoyagerRouter(), cookies, tabs });
  for (const [k, v] of Object.entries(seed)) stub.store.set(k, v);
  // Loading registers the SW's onMessage listener via the chrome stub.
  loadModules({
    chrome: stub.chrome,
    fetchImpl: fake.fetchImpl,
    files: SERVICE_WORKER_FILES,
    fixedNow: FIXED_NOW,
  });
  return { ...stub, ...fake };
}

test("service worker boots and registers a message listener", () => {
  const sw = serviceWorker();
  assert.equal(sw.listeners.message.length, 1, "exactly one onMessage router");
});

test("SYNC_NOW (paired) runs a full sync and responds with counts", async () => {
  const sw = serviceWorker({ seed: { apiUrl: "http://localhost:8000", token: "tok" } });

  const resp = await sw.sendMessage({ type: "SYNC_NOW" });

  assert.equal(resp.ok, true);
  assert.equal(resp.conversations, 2);
  assert.equal(resp.messages, 3);
  assert.ok(sw.badges.includes("OK"), "success badge set");
  assert.ok(sw.pushes().length >= 1, "pushed to backend");
});

test("SYNC_NOW (unpaired) responds Not paired without touching the network", async () => {
  const sw = serviceWorker(); // empty store

  const resp = await sw.sendMessage({ type: "SYNC_NOW" });

  assert.equal(resp.ok, false);
  assert.equal(resp.error, "Not paired");
  assert.equal(sw.pushes().length, 0);
});

test("START_PAIRING saves the instance URL and returns a pairing code", async () => {
  const sw = serviceWorker();

  const resp = await sw.sendMessage({ type: "START_PAIRING", apiUrl: "http://localhost:8000/" });

  assert.equal(resp.ok, true);
  assert.match(resp.code, /^PING-[A-Z2-9]{6}$/);
  assert.equal(sw.store.get("apiUrl"), "http://localhost:8000", "trailing slash stripped + persisted");
});

test("START_PAIRING with no URL is rejected", async () => {
  const sw = serviceWorker();
  const resp = await sw.sendMessage({ type: "START_PAIRING", apiUrl: "" });
  assert.equal(resp.ok, false);
  assert.equal(resp.error, "Instance URL is required");
});

test("DISCONNECT clears storage and reports success", async () => {
  const sw = serviceWorker({ seed: { apiUrl: "http://x", token: "tok", watermark: "2026-01-01T00:00:00Z" } });

  const resp = await sw.sendMessage({ type: "DISCONNECT" });

  assert.equal(resp.ok, true);
  assert.equal(sw.store.size, 0, "all storage cleared");
});
