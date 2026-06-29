# Debugging the PingCRM companion extension without a manual browser

Three layers, each removing more manual work. Layers 1–2 are fully offline
(no browser, no LinkedIn login, no cookies) and run in <1s. Layer 3 exercises
real Voyager but is fully scripted — no clicking.

```
test/
├── helpers/
│   ├── chrome-stub.mjs     in-memory chrome.* (storage, cookies, tabs, scripting, action)
│   ├── loader.mjs          loads the REAL sw modules into a Node vm context (importScripts emulation)
│   ├── fake-backend.mjs    fetch() replacement recording /linkedin/push etc.
│   └── voyager-router.mjs  maps executeScript Voyager calls → fixtures (the one browser seam)
├── fixtures/voyager/*.json synthetic Voyager responses the parsers accept
├── layer1.logic.test.mjs   drives runSync() directly
├── layer2.router.test.mjs  loads service-worker.js, drives it via SYNC_NOW / START_PAIRING / DISCONNECT
└── capture-and-e2e.mjs     Layer 3: CDP-driven real-Voyager capture + smoke
```

## Why this works

The entire sync path is plain JS that loads via `importScripts` and shares one
global scope. The **only** browser-coupled seam is one call in
`voyager-client.js`:

```
voyagerFetch() → chrome.scripting.executeScript({target:{tabId}, func})
```

`loader.mjs` reproduces the `importScripts` global-scope model by concatenating
the real module sources and running them once in a `node:vm` context whose
globals are our stubs (`chrome`, `fetch`, a frozen `Date`, `crypto`). Nothing in
the extension is modified or duplicated — the tests run the shipping code.

## Layer 1 & 2 — offline (default)

```bash
cd chrome-extension/test
node --test "**/*.test.mjs"      # or: npm test
```

Covers: first-sync vs delta (watermark) filtering, message direction from self
URN, `/linkedin/push` payload shape, missing-cookie / no-tab error surfacing,
401→silent-refresh, pairing-code format, and the full popup→SW message router.

Determinism: `Date.now()` is frozen to `FIXED_NOW = 1750000000000`, and the
1s Voyager rate-limit delays resolve instantly (`loader.mjs` stubs `setTimeout`).

### Testing against a real local backend (optional)
Skip `fake-backend.mjs` and pass Node's global `fetch` with a real `API_URL` and
a paired extension token instead of `tok`. Useful to verify the backend dedup /
auto-merge path end-to-end while still mocking Voyager.

## Layer 3 — scripted real Voyager (needs your li_at once)

Talks to Chrome over the DevTools Protocol (built-in `WebSocket`, no Playwright/
puppeteer) because an MV3 service worker can't be reached by page-automation
tools. Loads the unpacked extension, injects `li_at`, opens a LinkedIn tab, then
attaches to the SW target and calls its own `runSync` / Voyager globals — no
popup clicking.

```bash
# Capture fresh fixtures from a live session (→ fixtures/voyager/_captured/, gitignored)
LINKEDIN_LI_AT=AQ... node capture-and-e2e.mjs --capture

# Real end-to-end smoke against a local backend (needs a paired token)
LINKEDIN_LI_AT=AQ... API_URL=http://localhost:8000 EXT_TOKEN=... \
  node capture-and-e2e.mjs --e2e
```

Env: `LINKEDIN_LI_AT` (required), `CHROME_BIN` (default macOS Chrome),
`CDP_PORT` (default 9222), `API_URL`/`EXT_TOKEN` (--e2e only).

**Refreshing offline fixtures:** run `--capture`, review/sanitize the JSON in
`fixtures/voyager/_captured/`, then copy into `fixtures/voyager/`. That keeps
Layers 1–2 aligned with LinkedIn's current Voyager schema.
