/**
 * apiFetch timeout guard.
 *
 * pairing.js was hardened against hung requests, but every other call to the
 * user's PingCRM instance still used bare fetch() with no timeout. Chrome
 * allows ~6 concurrent connections per host, so a few wedged background
 * requests starve the PingCRM tab's own API calls and the dashboard renders
 * zeros because its requests never leave the browser.
 *
 * These tests assert the guard is applied at the call sites, not just that the
 * helper exists — a helper nobody calls was the original bug.
 *
 * Run: `node --test` from chrome-extension/test.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeChrome } from "./helpers/chrome-stub.mjs";
import { loadModules, EXT_DIR, SERVICE_WORKER_FILES } from "./helpers/loader.mjs";

const BG = path.join(EXT_DIR, "background");

/** Load just the helper with a recording fetch. */
function harness() {
  const calls = [];
  const fetchImpl = async (url, opts = {}) => {
    calls.push({ url, opts, signal: opts.signal });
    return { ok: true, status: 200, json: async () => ({}), text: async () => "" };
  };
  const sandbox = loadModules({
    chrome: makeChrome().chrome,
    fetchImpl,
    files: [path.join(BG, "api-fetch.js")],
    exports: ["apiFetch", "API_FETCH_TIMEOUT_MS"],
  });
  return { api: sandbox.__exports, calls };
}

test("attaches an abort signal so a hung request cannot hold a connection open", async () => {
  const h = harness();

  await h.api.apiFetch("http://x/api/v1/suggestions");

  assert.equal(h.calls.length, 1);
  assert.ok(h.calls[0].signal, "fetch was given an AbortSignal");
  assert.equal(h.calls[0].signal.aborted, false);
});

test("preserves method, headers, and body while adding the signal", async () => {
  const h = harness();

  await h.api.apiFetch("http://x/api/v1/linkedin/push", {
    method: "POST",
    headers: { Authorization: "Bearer tok" },
    body: '{"a":1}',
  });

  const { opts } = h.calls[0];
  assert.equal(opts.method, "POST");
  assert.equal(opts.headers.Authorization, "Bearer tok");
  assert.equal(opts.body, '{"a":1}');
  assert.ok(opts.signal);
});

test("respects a caller-supplied signal instead of silently replacing it", async () => {
  const h = harness();
  const controller = new AbortController();

  await h.api.apiFetch("http://x/api/v1/suggestions", { signal: controller.signal });

  assert.equal(h.calls[0].signal, controller.signal);
});

test("the timeout actually aborts a request that never settles", async () => {
  const calls = [];
  // A fetch that only ever settles when its signal aborts.
  const fetchImpl = (url, opts = {}) => {
    calls.push({ url });
    return new Promise((_resolve, reject) => {
      opts.signal.addEventListener("abort", () =>
        reject(Object.assign(new Error("aborted"), { name: "TimeoutError" }))
      );
    });
  };
  const sandbox = loadModules({
    chrome: makeChrome().chrome,
    fetchImpl,
    files: [path.join(BG, "api-fetch.js")],
    exports: ["apiFetch"],
  });

  // 10ms rather than the 30s default so the test does not sit there waiting.
  await assert.rejects(
    () => sandbox.__exports.apiFetch("http://x/api/v1/suggestions", {}, 10),
    /aborted/
  );
  assert.equal(calls.length, 1);
});

test("every call to the PingCRM instance goes through apiFetch", () => {
  // Guards against a new call site reintroducing a bare, unbounded fetch.
  const offenders = [];
  for (const file of SERVICE_WORKER_FILES) {
    const src = fs.readFileSync(file, "utf8");
    src.split("\n").forEach((line, i) => {
      // A bare fetch( targeting ${apiUrl} — apiFetch( does not match \bfetch(.
      if (/(?<!api)\bfetch\(\s*`\$\{apiUrl\}/.test(line)) {
        offenders.push(`${path.basename(file)}:${i + 1}: ${line.trim()}`);
      }
    });
  }
  assert.deepEqual(offenders, [], `bare fetch() to apiUrl found:\n${offenders.join("\n")}`);
});

test("service worker exposes a handler for every routed message type", () => {
  // The router now dispatches through a table; a typo'd key would silently
  // return false and drop the message.
  const sandbox = loadModules({
    chrome: makeChrome().chrome,
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    files: SERVICE_WORKER_FILES,
    exports: ["MESSAGE_HANDLERS"],
  });

  const table = sandbox.__exports.MESSAGE_HANDLERS;
  const expected = [
    "LINKEDIN_PAGE_VISIT", "PROFILE_VISIT", "SYNC_NOW", "START_PAIRING",
    "DISCONNECT", "GET_SUGGESTION", "REGENERATE_SUGGESTION", "META_PAGE_VISIT",
    "META_SYNC_NOW", "pingcrm:connect-twitter", "pingcrm:refresh-twitter-cookies",
  ];
  for (const type of expected) {
    assert.equal(typeof table[type], "function", `no handler for ${type}`);
  }
});
