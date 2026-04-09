"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");

const { signPayload, createWebhookSender } = require("../src/webhook.js");

test("signPayload produces correct HMAC-SHA256 hex digest", () => {
  const body = JSON.stringify({ event: "test", data: { foo: "bar" } });
  const secret = "my-secret";

  const expected = crypto.createHmac("sha256", secret).update(body).digest("hex");
  const actual = signPayload(body, secret);

  assert.equal(actual, expected, "HMAC digest should match crypto reference");
});

test("signPayload produces a 64-char hex string", () => {
  const body = "hello world";
  const secret = "another-secret";

  const digest = signPayload(body, secret);
  assert.match(digest, /^[0-9a-f]{64}$/, "digest must be 64 lowercase hex chars");
});

test("signPayload is deterministic for same inputs", () => {
  const body = "deterministic-test";
  const secret = "stable-secret";

  const first = signPayload(body, secret);
  const second = signPayload(body, secret);

  assert.equal(first, second, "same input should always yield same digest");
});

test("signPayload produces different digests for different secrets", () => {
  const body = "same-body";

  const digest1 = signPayload(body, "secret-one");
  const digest2 = signPayload(body, "secret-two");

  assert.notEqual(digest1, digest2, "different secrets should produce different digests");
});

test("signPayload produces different digests for different bodies", () => {
  const secret = "same-secret";

  const digest1 = signPayload("body-one", secret);
  const digest2 = signPayload("body-two", secret);

  assert.notEqual(digest1, digest2, "different bodies should produce different digests");
});

test("createWebhookSender returns object with send function", () => {
  const sender = createWebhookSender("http://localhost:8000/webhook", "test-secret");
  assert.equal(typeof sender.send, "function", "sender.send should be a function");
});
