/**
 * Layer 3 — scripted real-Voyager capture + E2E smoke (NO manual clicking).
 *
 * Launches a headed Chrome with the unpacked extension loaded, injects the
 * user's li_at cookie, opens a LinkedIn tab, then attaches to the extension's
 * *service-worker* target over the Chrome DevTools Protocol and calls the SW's
 * own globals directly. This is the only layer that exercises real cookies /
 * CSRF / Voyager, so it's the one that catches "LinkedIn changed their schema".
 *
 * It talks raw CDP over Node's built-in WebSocket (no Playwright/puppeteer,
 * zero dependencies) because page-automation tools cannot reach an MV3 service
 * worker — only CDP can.
 *
 *   Capture fresh fixtures (writes test/fixtures/voyager/_captured/, gitignored):
 *     LINKEDIN_LI_AT=AQ... node test/capture-and-e2e.mjs --capture
 *
 *   Real end-to-end smoke against a local backend (requires a paired token):
 *     LINKEDIN_LI_AT=AQ... API_URL=http://localhost:8000 EXT_TOKEN=... \
 *       node test/capture-and-e2e.mjs --e2e
 *
 * Env:
 *   LINKEDIN_LI_AT  (required) the li_at cookie value from a logged-in session
 *   CHROME_BIN      (optional) path to Chrome; defaults to macOS Google Chrome
 *   CDP_PORT        (optional) remote-debugging port (default 9222)
 *   API_URL,EXT_TOKEN  (--e2e only) backend base URL + extension bearer token
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const EXT_DIR = path.resolve(HERE, "..");
// --profile=<slug> probes one profile through the backfill extraction logic.
// --enrich=<slug> runs the real profile-visit push against API_URL/EXT_TOKEN.
const PROFILE_ARG = process.argv.find((a) => a.startsWith("--profile"));
const ENRICH_ARG = process.argv.find((a) => a.startsWith("--enrich"));
const SLUG_ARG = ENRICH_ARG || PROFILE_ARG;
const PROFILE_SLUG = SLUG_ARG ? (SLUG_ARG.split("=")[1] || process.argv[process.argv.indexOf(SLUG_ARG) + 1]) : null;
const MODE = ENRICH_ARG ? "enrich" : PROFILE_ARG ? "profile" : process.argv.includes("--capture") ? "capture" : "e2e";
const PORT = Number(process.env.CDP_PORT || 9222);
const CHROME_BIN =
  process.env.CHROME_BIN || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const LI_AT = process.env.LINKEDIN_LI_AT;

if (!LI_AT) {
  console.error("✖ LINKEDIN_LI_AT env var is required (li_at cookie from a logged-in LinkedIn session).");
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── Minimal CDP client over the built-in WebSocket ───────────────────────────
function cdp(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let nextId = 1;
  const pending = new Map();
  const handlers = [];
  const ready = new Promise((res, rej) => {
    ws.addEventListener("open", () => res());
    ws.addEventListener("error", (e) => rej(e));
  });
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method) {
      for (const h of handlers) h(msg);
    }
  });
  const send = (method, params = {}, sessionId) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  return { ready, send, on: (h) => handlers.push(h), close: () => ws.close() };
}

const httpJson = async (url) => (await fetch(url)).json();

// ── Launch Chrome with the unpacked extension ────────────────────────────────
async function launchChrome() {
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "pingcrm-ext-"));
  const args = [
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${userDataDir}`,
    `--load-extension=${EXT_DIR}`,
    `--disable-extensions-except=${EXT_DIR}`,
    "--no-first-run",
    "--no-default-browser-check",
    // Recent Chrome (137+) disables the --load-extension switch via this
    // feature; turn it back off so the unpacked extension actually loads.
    "--disable-features=DialMediaRouteProvider,DisableLoadExtensionCommandLineSwitch",
    "about:blank",
  ];
  const proc = spawn(CHROME_BIN, args, { stdio: "ignore" });
  proc.on("error", (e) => {
    console.error(`✖ Failed to launch Chrome at ${CHROME_BIN}: ${e.message}`);
    console.error("  Set CHROME_BIN to your Chrome path.");
    process.exit(2);
  });
  // Wait for the debugging endpoint and grab the browser-level ws.
  for (let i = 0; i < 50; i++) {
    try {
      const ver = await httpJson(`http://localhost:${PORT}/json/version`);
      return { proc, userDataDir, browserWs: ver.webSocketDebuggerUrl };
    } catch {
      await sleep(200);
    }
  }
  throw new Error("Chrome devtools endpoint never came up");
}

// Connect to the browser endpoint and turn on target discovery. Extension
// service workers are NOT listed by /json/list — they only surface via the
// Target domain, so everything below multiplexes over this one connection
// (flatten mode: each attached target gets a sessionId).
async function connectBrowser(browserWs) {
  const b = cdp(browserWs);
  await b.ready;
  const targets = new Map();
  b.on((msg) => {
    if (msg.method === "Target.targetCreated" || msg.method === "Target.targetInfoChanged") {
      targets.set(msg.params.targetInfo.targetId, msg.params.targetInfo);
    } else if (msg.method === "Target.targetDestroyed") {
      targets.delete(msg.params.targetId);
    }
  });
  // Explicit empty filter clause {} = "match everything", incl. service_worker,
  // which the default discovery filter omits.
  await b.send("Target.setDiscoverTargets", { discover: true, filter: [{}] });
  // Seed from a snapshot too, in case targetCreated fired before we subscribed.
  const seed = await b.send("Target.getTargets", { filter: [{}] });
  for (const t of seed.targetInfos ?? []) targets.set(t.targetId, t);
  return { b, targets };
}

async function waitForTargetInfo(targets, pred, label, timeoutMs = 25000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const t of targets.values()) if (pred(t)) return t;
    await sleep(300);
  }
  const seen = [...targets.values()].map((t) => `${t.type} ${t.url}`).join("\n   ");
  throw new Error(`Timed out waiting for target: ${label}\n   discovered targets:\n   ${seen || "(none)"}`);
}

// Attach to a target in flatten mode → session-scoped send().
async function attach(b, targetId) {
  const { sessionId } = await b.send("Target.attachToTarget", { targetId, flatten: true });
  return { sessionId, send: (method, params) => b.send(method, params, sessionId) };
}

// Create a tab, inject li_at, navigate to LinkedIn so cookies+CSRF exist.
async function openLinkedInTab(b) {
  const { targetId } = await b.send("Target.createTarget", { url: "about:blank" });
  const s = await attach(b, targetId);
  await s.send("Network.enable", {});
  await s.send("Network.setCookie", {
    name: "li_at",
    value: LI_AT,
    domain: ".linkedin.com",
    path: "/",
    secure: true,
    httpOnly: true,
  });
  await s.send("Page.enable", {});
  await s.send("Page.navigate", { url: "https://www.linkedin.com/feed/" });
  await sleep(6000); // let the SPA settle so JSESSIONID lands on document.cookie
  return s;
}

// Attach to the extension service worker → eval() helper + console streaming.
async function attachServiceWorker(b, targets) {
  const sw = await waitForTargetInfo(
    targets,
    (t) => t.type === "service_worker" && /service-worker\.js/.test(t.url),
    "extension service worker",
  );
  const s = await attach(b, sw.targetId);
  await s.send("Runtime.enable", {});
  b.on((msg) => {
    if (msg.sessionId === s.sessionId && msg.method === "Runtime.consoleAPICalled") {
      const text = msg.params.args.map((a) => a.value ?? a.description ?? "").join(" ");
      console.log("   [SW]", text);
    }
  });
  const evaluate = async (expression) => {
    const r = await s.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (r.exceptionDetails) {
      throw new Error("SW eval failed: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    }
    return r.result.value;
  };
  return { evaluate };
}

// ── Modes ────────────────────────────────────────────────────────────────────
async function runCapture(evaluate) {
  console.log("→ Capturing raw Voyager responses via the SW's own client...");
  const raw = await evaluate(`(async () => {
    const { liAt, jsessionid } = await _readLinkedInCookies();
    const selfUrn = await voyagerGetSelfUrn(liAt, jsessionid);
    const conversations = await voyagerGetConversations(liAt, jsessionid, selfUrn);
    const firstConv = (conversations?.data?.messengerConversationsBySyncToken?.elements
      ?? conversations?.data?.messengerConversations?.elements ?? [])[0];
    const convUrn = firstConv?.backendUrn ?? firstConv?.entityUrn ?? null;
    const messages = convUrn ? await voyagerGetConversationMessages(liAt, jsessionid, convUrn) : null;
    return { selfUrn, me: { selfUrn }, conversations, messages };
  })()`);

  const outDir = path.join(EXT_DIR, "test/fixtures/voyager/_captured");
  fs.mkdirSync(outDir, { recursive: true });
  const write = (name, obj) => fs.writeFileSync(path.join(outDir, name), JSON.stringify(obj, null, 2));
  write("self-urn.json", { selfUrn: raw.selfUrn });
  write("conversations.page1.json", raw.conversations);
  if (raw.messages) write("messages.conv1.json", raw.messages);
  console.log(`✓ Wrote raw fixtures to ${outDir} (gitignored — contains real data).`);
  console.log("  Review + sanitize, then copy into test/fixtures/voyager/ to update the offline suite.");
}

async function runE2E(evaluate) {
  const apiUrl = process.env.API_URL;
  const token = process.env.EXT_TOKEN;
  if (!apiUrl || !token) {
    console.error("✖ --e2e requires API_URL and EXT_TOKEN (a paired extension bearer token).");
    process.exit(2);
  }
  console.log(`→ Running real sync against ${apiUrl} ...`);
  const result = await evaluate(`(async () => {
    await chrome.storage.local.set({ apiUrl: ${JSON.stringify(apiUrl)}, token: ${JSON.stringify(token)} });
    return await runSync(${JSON.stringify(apiUrl)}, ${JSON.stringify(token)}, true);
  })()`);
  console.log("→ runSync result:", JSON.stringify(result));
  if (result.error) {
    console.error(`✖ Sync reported error: ${result.error}`);
    process.exitCode = 1;
  } else if (result.messages === 0) {
    console.warn("⚠ Sync ran but pushed 0 messages — check watermark / account has recent DMs.");
  } else {
    console.log(`✓ E2E smoke passed: ${result.conversations} conversations, ${result.messages} messages.`);
  }
}

// Diagnostic: fetch one profile and run it through the SAME extraction the
// backfill uses, so we can see exactly what avatar/company/headline come out.
async function runProfileProbe(evaluate, slug) {
  console.log(`→ Probing profile "${slug}" through the backfill extraction...`);
  const out = await evaluate(`(async () => {
    const { liAt, jsessionid } = await _readLinkedInCookies();
    const raw = await voyagerGetProfile(liAt, jsessionid, ${JSON.stringify(slug)});
    const included = raw?.included ?? [];
    const positions = included.filter(i => /\\.Position$/.test(i?.$type || ""));
    return { raw, positionSample: positions.slice(0, 6) };
  })()`);

  const outDir = path.join(EXT_DIR, "test/fixtures/voyager/_captured");
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, `profile-${slug}.json`), JSON.stringify(out.raw, null, 2));
  console.log(`✓ Wrote raw profile to _captured/profile-${slug}.json`);
  console.log("\nPosition objects (company lives here):");
  for (const p of out.positionSample) {
    console.log(JSON.stringify({
      companyName: p.companyName, title: p.title,
      timePeriod: p.timePeriod, dateRange: p.dateRange,
      company: p.company, keys: Object.keys(p),
    }, null, 2));
  }
}

// Run the REAL profile-visit push against a live backend (mirrors the SW's
// PROFILE_VISIT handler body) and report what the backend did.
async function runEnrich(evaluate, slug) {
  const apiUrl = (process.env.API_URL || "").replace(/\/+$/, "");
  const token = process.env.EXT_TOKEN;
  if (!apiUrl || !token) {
    console.error("✖ --enrich requires API_URL and EXT_TOKEN (web or extension JWT).");
    process.exit(2);
  }
  console.log(`→ Enriching "${slug}" against ${apiUrl} (real Voyager + avatar + push)...`);
  const out = await evaluate(`(async () => {
    const apiUrl = ${JSON.stringify(apiUrl)}, token = ${JSON.stringify(token)};
    const { liAt, jsessionid } = await _readLinkedInCookies();
    const raw = await voyagerGetProfile(liAt, jsessionid, ${JSON.stringify(slug)});
    const fields = _extractProfileFields(raw);
    if (!fields) return { error: "NO_PROFILE" };
    let avatarData = null;
    if (fields.avatarUrl) { try { avatarData = await fetchLinkedInImageAsBase64(fields.avatarUrl); } catch (e) {} }
    const resp = await fetch(apiUrl + "/api/v1/linkedin/push", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
      body: JSON.stringify({
        enrich_only: true,
        profiles: [{
          profile_id: ${JSON.stringify(slug)}, member_id: fields.memberId,
          profile_url: "https://www.linkedin.com/in/" + ${JSON.stringify(slug)},
          full_name: fields.fullName, headline: fields.headline, company: fields.company,
          location: fields.location, avatar_url: fields.avatarUrl, avatar_data: avatarData,
        }],
        messages: [],
      }),
    });
    const json = await resp.json().catch(() => null);
    return { status: resp.status, memberId: fields.memberId, company: fields.company,
             headline: fields.headline, avatarBytes: !!avatarData, data: json?.data };
  })()`);
  console.log(JSON.stringify(out, null, 2));
  if (out.status === 200) {
    console.log(`✓ Push accepted — updated ${out.data?.contacts_updated ?? "?"} contact(s), company="${out.company}", avatar bytes=${out.avatarBytes}`);
  } else {
    console.error(`✖ Push returned ${out.status}`);
    process.exitCode = 1;
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────
(async () => {
  console.log(`PingCRM extension Layer 3 — mode: ${MODE}`);
  const { proc, browserWs } = await launchChrome();
  let browser;
  try {
    const conn = await connectBrowser(browserWs);
    browser = conn.b;
    console.log("→ Opening LinkedIn tab and injecting li_at...");
    await openLinkedInTab(conn.b);
    console.log("→ Attaching to extension service worker...");
    const { evaluate } = await attachServiceWorker(conn.b, conn.targets);
    if (MODE === "enrich") await runEnrich(evaluate, PROFILE_SLUG);
    else if (MODE === "profile") await runProfileProbe(evaluate, PROFILE_SLUG);
    else if (MODE === "capture") await runCapture(evaluate);
    else await runE2E(evaluate);
  } catch (e) {
    console.error("✖", e.message);
    process.exitCode = 1;
  } finally {
    browser?.close();
    proc.kill();
  }
})();
