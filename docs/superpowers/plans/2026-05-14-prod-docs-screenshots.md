# Prod Docs Screenshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture multi-shot, PII-redacted screenshots from prod for every page under `docs/docs/features/`, embed them inline in the same PR, and ship via a single PR.

**Architecture:** Drive `pingcrm.sawinyh.com` through the **agent-browser** skill (per project rule: no custom Playwright scripts). Apply PII redaction in-browser via CSS `filter: blur` injected immediately before each capture, with rules version-controlled in `docs/screenshots/redaction-rules.json`. Save PNGs under `docs/static/img/screenshots/<feature>/<name>.png` and embed via standard Markdown image syntax with absolute paths.

**Tech Stack:** agent-browser CLI, Docusaurus (existing), Markdown.

**Spec:** `docs/superpowers/specs/2026-05-14-prod-docs-screenshots-design.md`

**Total shot count:** ~45 across 14 feature pages.

---

## Per-shot procedure (referenced by every per-feature task)

Each shot follows this sequence. Where a task table provides inputs (route, state setup steps, output filename, blur selectors), substitute them in.

1. **Navigate** to the target route on `https://pingcrm.sawinyh.com` (e.g., `/contacts`).
2. **Wait for content load** — wait for the primary content selector named in the shot's state-setup column to be visible (e.g. `[data-testid="contacts-table"]`). If no selector is listed, wait for `networkidle`.
3. **Run state-setup steps** listed in the shot's "State setup" column (e.g. "click row checkboxes 1–3", "open kebab menu", "scroll to anchor #timeline").
4. **Inject the blur stylesheet** by evaluating the following JS in the page (substituting `<selectors>` with the comma-separated selector list from `redaction-rules.json` for this route, plus the global fallback selectors):

   ```js
   (() => {
     const s = document.createElement('style');
     s.id = 'pingcrm-redaction';
     s.textContent = `<selectors> { filter: blur(5px) !important; }`;
     document.head.appendChild(s);
   })();
   ```

5. **Wait 200ms** for the blur to render.
6. **Capture viewport screenshot** at 1440×900, light theme, devicePixelRatio=2, output PNG.
7. **Save** to `docs/static/img/screenshots/<feature>/<filename>.png`.
8. **Remove the blur stylesheet** (`document.getElementById('pingcrm-redaction')?.remove()`) so the next shot in the session starts clean.

Login session is established once per agent-browser session (see Task 2). Once logged in, the cookie persists for subsequent navigations in that session.

If the agent-browser CLI does not expose direct JS evaluation, fall back to its equivalent (e.g. `agent-browser eval`, `--inject-script`, or whatever the skill documents). Consult the **agent-browser:agent-browser** skill for the exact command surface.

**Parameterized route lookup:** When navigating to a concrete URL like `/contacts/abc-123` or `/organizations/xyz-987`, look up the redaction rules under the templated key `/contacts/:id` or `/organizations/:id` in `redaction-rules.json`. The JSON uses `:id` as a placeholder; the live URL has the real UUID.

**Embed step anchoring:** Each per-feature task's embed step lists absolute line numbers like "After line 12" alongside a content anchor in parentheses like `(## Contact List opening paragraph)`. **Use the content anchor, not the line number.** Line numbers were computed against the unmodified file; as you apply earlier inserts in the same task, subsequent line numbers shift down. The content anchor (heading, end of paragraph, or specific sentence) is stable.

---

## Phase 1 — Infrastructure

### Task 1: Create screenshot tooling directory

**Files:**
- Create: `docs/screenshots/redaction-rules.json`
- Create: `docs/screenshots/capture.md`
- Create: `docs/static/img/screenshots/.gitkeep`

- [ ] **Step 1: Create the redaction rules file**

Create `docs/screenshots/redaction-rules.json` with this exact content:

```json
{
  "version": 1,
  "global": {
    "blur": [
      "[data-pii]",
      ".contact-name",
      ".contact-email",
      "img.avatar",
      ".avatar img",
      "img[alt*='avatar' i]"
    ]
  },
  "routes": {
    "/contacts": { "blur": [] },
    "/contacts/:id": { "blur": [] },
    "/dashboard": { "blur": [] },
    "/identity": { "blur": [] },
    "/map": { "blur": [] },
    "/notifications": { "blur": [] },
    "/organizations": { "blur": [] },
    "/organizations/:id": { "blur": [] },
    "/settings": { "blur": [] },
    "/suggestions": { "blur": [] }
  }
}
```

Per-route `blur` arrays start empty and are filled in by the per-feature tasks as actual PII selectors are identified on the live page.

- [ ] **Step 2: Create the capture README**

Create `docs/screenshots/capture.md` with this exact content:

```markdown
# Capturing Docs Screenshots

All screenshots in `docs/static/img/screenshots/<feature>/` are captured from production (`pingcrm.sawinyh.com`) using the **agent-browser** skill, with PII redacted via in-browser CSS blur before each capture.

## Procedure

For each shot:

1. Navigate to the target route.
2. Wait for the primary content selector to be visible.
3. Run the shot's state-setup steps (open modal, select rows, scroll, etc.).
4. Inject the redaction stylesheet — concat the `global.blur` list and the route-specific `routes["<route>"].blur` list from `redaction-rules.json`, then evaluate:

   ```js
   const s = document.createElement('style');
   s.id = 'pingcrm-redaction';
   s.textContent = `<selector-list> { filter: blur(5px) !important; }`;
   document.head.appendChild(s);
   ```

5. Wait 200ms.
6. Capture at 1440×900, light theme, DPR=2.
7. Save to `docs/static/img/screenshots/<feature>/<filename>.png`.
8. Remove the blur stylesheet before the next shot.

## Adding a new shot

1. Add the route to `redaction-rules.json` under `routes` if not already present.
2. Inspect the page in DevTools and add any new PII selectors specific to that route to its `blur` array.
3. Run the procedure.
4. Eyeball the resulting PNG. If anything legible leaks (a name, email, message body, avatar with recognizable face), add the missing selector and re-capture.

## Re-running for a single feature

The implementation plan at `docs/superpowers/plans/2026-05-14-prod-docs-screenshots.md` contains per-feature shot tables that double as a re-capture script. Find the feature, follow its table, commit.
```

- [ ] **Step 3: Create the placeholder for the screenshots directory**

Create `docs/static/img/screenshots/.gitkeep` (empty file). This ensures the directory exists in git even before the first feature is captured.

- [ ] **Step 4: Commit**

```bash
git add docs/screenshots/redaction-rules.json docs/screenshots/capture.md docs/static/img/screenshots/.gitkeep
git commit -m "docs: scaffold screenshot capture infrastructure"
```

---

### Task 2: Login smoke test — verify capture pipeline on /dashboard

**Files:**
- Create: `docs/static/img/screenshots/_smoke/dashboard-smoke.png` (temporary, will be deleted in Step 6)

**Purpose:** Before scaling to 45 shots, verify end-to-end: login works, viewport size is correct, blur injection works, PNG output is sharp.

- [ ] **Step 1: Start an agent-browser session and log in**

Invoke the agent-browser skill. Open `https://pingcrm.sawinyh.com/auth/login`. Sign in with the prod credentials from `CLAUDE.local.md`:

- Email: `nsawinyh@gmail.com`
- Password: `gdn.nxt3vjw6amj@XHM`

Wait for redirect to `/dashboard`. Confirm you see the dashboard layout (stat cards, "Pending Follow-ups" heading).

- [ ] **Step 2: Set viewport and DPR**

Resize the viewport to **1440×900** and set device pixel ratio to **2**. Confirm via `window.innerWidth === 1440` and `window.devicePixelRatio === 2`.

- [ ] **Step 3: Inject blur using global selectors only**

Evaluate in the page:

```js
const s = document.createElement('style');
s.id = 'pingcrm-redaction';
s.textContent = `[data-pii], .contact-name, .contact-email, img.avatar, .avatar img, img[alt*='avatar' i] { filter: blur(5px) !important; }`;
document.head.appendChild(s);
```

Wait 200ms.

- [ ] **Step 4: Capture and save**

Capture a viewport screenshot, save as `docs/static/img/screenshots/_smoke/dashboard-smoke.png`.

- [ ] **Step 5: Eyeball the PNG**

Open `docs/static/img/screenshots/_smoke/dashboard-smoke.png` and check:

- Dimensions are 2880×1800 (1440×900 at 2× DPR). If 1440×900, DPR is 1 and shots will look soft on retina — fix and re-capture.
- Light theme (white background, dark text).
- Any avatars in the "Needs Attention" panel or "Recent Activity" feed are blurred.
- Names and emails in those panels are visible — that confirms the global selectors didn't catch them; per-route selectors will be added in Task 4 (dashboard capture).

- [ ] **Step 6: Delete smoke file and commit a sanity note (no image checked in)**

```bash
rm -rf docs/static/img/screenshots/_smoke
```

Do **not** commit the smoke PNG — it has unredacted PII. The smoke shot's purpose is verification only.

If the smoke shot looked correct, proceed. If anything was off (wrong dimensions, wrong theme, blur not applied), debug before continuing — every subsequent task assumes the pipeline works.

No commit for this task — it's a checkpoint.

---

## Phase 2 — Per-feature captures

Tasks 3–16 each: (a) identify any per-route blur selectors not yet in `redaction-rules.json` and add them, (b) capture all shots in the feature's manifest table using the per-shot procedure, (c) embed the images into the matching `.md` at the listed anchor points, (d) commit PNGs + `.md` + updated rules in one commit.

**Common file targets for every Phase 2 task:**
- Modify: `docs/screenshots/redaction-rules.json` (add per-route selectors as needed)

---

### Task 3: Capture screenshots for `contacts.md`

**Files:**
- Create: `docs/static/img/screenshots/contacts/list.png`
- Create: `docs/static/img/screenshots/contacts/list-bulk-actions.png`
- Create: `docs/static/img/screenshots/contacts/detail.png`
- Create: `docs/static/img/screenshots/contacts/detail-timeline.png`
- Create: `docs/static/img/screenshots/contacts/detail-composer.png`
- Create: `docs/static/img/screenshots/contacts/import.png`
- Modify: `docs/docs/features/contacts.md`
- Modify: `docs/screenshots/redaction-rules.json`

- [ ] **Step 1: Identify and add per-route blur selectors**

In a logged-in agent-browser session, navigate to `/contacts` and `/contacts/<some-id>`. Open DevTools and identify selectors covering: contact-row names, emails, avatars, message body text in the timeline, BCC address strings.

Add to `docs/screenshots/redaction-rules.json`:

```json
"/contacts": {
  "blur": [
    "table tbody tr td:nth-child(2)",
    "table tbody tr td:nth-child(3)",
    "table tbody tr img"
  ]
},
"/contacts/:id": {
  "blur": [
    "[data-testid='contact-name']",
    "[data-testid='contact-email']",
    "[data-testid='contact-phone']",
    "[data-testid='bcc-address']",
    ".timeline-message-body",
    ".timeline img"
  ]
}
```

If the actual DOM doesn't match these selectors, swap them for the real ones — the goal is to blur PII, not to match this exact list verbatim.

- [ ] **Step 2: Capture all six shots**

| Filename | Route | State setup |
|---|---|---|
| `contacts/list.png` | `/contacts` | Wait for the table to load with rows visible. Scroll to top. |
| `contacts/list-bulk-actions.png` | `/contacts` | Click the checkbox on rows 1, 2, and 3. Wait for the bulk-action toolbar to appear. |
| `contacts/detail.png` | `/contacts/[id]` | Pick any non-archived contact ID. Wait for the contact header to render. Scroll to top. |
| `contacts/detail-timeline.png` | `/contacts/[id]` | Same contact. Scroll the timeline section into view (`scrollIntoView` on the timeline container). |
| `contacts/detail-composer.png` | `/contacts/[id]` | Same contact. Click "Compose message" / the compose button. Wait for the composer modal to render. |
| `contacts/import.png` | `/contacts` | Click the "Import" button. Wait for the import modal/dropzone to render. |

Pick the contact for detail shots carefully: choose one with non-empty timeline, an avatar, a company, and at least 5 timeline entries so the timeline shot is illustrative. Note the chosen contact ID — use the same one for all `detail-*` shots so they tell a coherent story.

Follow the per-shot procedure for each row (navigate → setup → inject blur → capture → save → remove blur).

- [ ] **Step 3: Eyeball every PNG**

Open all six images. For each, confirm: viewport size correct, blur applied to names/emails/avatars/messages, no full names or email addresses legible, no message body text legible. Re-capture any that leaks.

- [ ] **Step 4: Embed images into `contacts.md`**

Apply these edits to `docs/docs/features/contacts.md`:

After line 12 (`## Contact List` opening paragraph), insert:

```markdown

![Contact list view](/img/screenshots/contacts/list.png)
```

After line 44 (end of "Bulk Actions" subsection, after "**2nd Tier bulk delete API:**" block — place the image after the API description but before `## Contact Detail`), insert:

```markdown

![Bulk actions toolbar with three contacts selected](/img/screenshots/contacts/list-bulk-actions.png)
```

After line 53 (`### Inline Editing` opening — actually place under `## Contact Detail` header at line 51, before `### Inline Editing`), insert:

```markdown

![Contact detail page](/img/screenshots/contacts/detail.png)
```

After line 102 (end of "Interaction Timeline" first paragraph block, just before "Messages longer than 400 characters..."), insert:

```markdown

![Interaction timeline showing messages across platforms](/img/screenshots/contacts/detail-timeline.png)
```

After line 85 (end of "Message Composer" subsection — after the AI composer paragraph and before `### BCC Email Logging`), insert:

```markdown

![Message composer drafting an AI-suggested message](/img/screenshots/contacts/detail-composer.png)
```

After line 173 (end of the "Manual Entry" bullet under `## Importing Contacts`, before "Additionally, the LinkedIn Chrome extension..."), insert:

```markdown

![CSV import modal](/img/screenshots/contacts/import.png)
```

Verify each image renders by reading the modified file and checking the paths.

- [ ] **Step 5: Commit**

```bash
git add docs/static/img/screenshots/contacts docs/docs/features/contacts.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): contacts page"
```

---

### Task 4: Capture screenshots for `dashboard.md`

**Files:**
- Create: `docs/static/img/screenshots/dashboard/overview.png`
- Create: `docs/static/img/screenshots/dashboard/followup-expanded.png`
- Create: `docs/static/img/screenshots/dashboard/needs-attention.png`
- Modify: `docs/docs/features/dashboard.md`
- Modify: `docs/screenshots/redaction-rules.json`

- [ ] **Step 1: Add per-route blur selectors**

In `docs/screenshots/redaction-rules.json`, set `routes["/dashboard"].blur` to:

```json
"/dashboard": {
  "blur": [
    "[data-testid='recent-activity'] .contact-name",
    "[data-testid='recent-activity'] .message-snippet",
    "[data-testid='needs-attention'] .contact-name",
    "[data-testid='pending-followups'] .contact-name",
    "[data-testid='pending-followups'] .ai-draft-text"
  ]
}
```

Adjust selectors to match actual DOM. Use DevTools to find the real testids/classes.

- [ ] **Step 2: Capture all three shots**

| Filename | Route | State setup |
|---|---|---|
| `dashboard/overview.png` | `/dashboard` | Scroll to top. Wait for stat cards, follow-ups list, and recent activity to all render. |
| `dashboard/followup-expanded.png` | `/dashboard` | Click the first pending follow-up card to expand it. Wait for the AI-drafted message body to render inside the card. |
| `dashboard/needs-attention.png` | `/dashboard` | Resize/scroll so the right-hand "Needs Attention" panel fills the frame (or shoot the panel via a tighter clip if agent-browser supports element-level capture; otherwise full viewport). |

Follow the per-shot procedure.

- [ ] **Step 3: Eyeball every PNG**

Confirm: no contact names visible in any panel, no AI draft text legible, no message snippets in the activity feed legible.

- [ ] **Step 4: Embed images into `dashboard.md`**

Apply edits to `docs/docs/features/dashboard.md`:

After line 8 (the page opening paragraph, before `## Stat Cards`), insert:

```markdown

![Dashboard overview](/img/screenshots/dashboard/overview.png)
```

After line 28 (end of "Pending Follow-ups" subsection, before `## Recent Activity`), insert:

```markdown

![Follow-up card expanded with AI-drafted message](/img/screenshots/dashboard/followup-expanded.png)
```

After line 38 (end of "Needs Attention" subsection), insert:

```markdown

![Needs Attention panel](/img/screenshots/dashboard/needs-attention.png)
```

- [ ] **Step 5: Commit**

```bash
git add docs/static/img/screenshots/dashboard docs/docs/features/dashboard.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): dashboard page"
```

---

### Task 5: Capture screenshots for `gmail.md`

**Files:**
- Create: `docs/static/img/screenshots/gmail/settings-section.png`
- Create: `docs/static/img/screenshots/gmail/bcc-address.png`
- Create: `docs/static/img/screenshots/gmail/timeline-thread.png`
- Modify: `docs/docs/features/gmail.md`

- [ ] **Step 1: Capture three shots**

| Filename | Route | State setup |
|---|---|---|
| `gmail/settings-section.png` | `/settings` | Scroll to the Gmail section. Frame the connected-status badge, connected email (will be blurred), and the Sync Contacts/Sync Calendar/Sync Settings controls. |
| `gmail/bcc-address.png` | `/contacts/[id]` | Use the same contact from Task 3. Scroll to the BCC Email Logging area (or wherever the BCC hash is displayed). The hash itself should be visible (not blurred — it's not PII); the connected email prefix in front of it is blurred. |
| `gmail/timeline-thread.png` | `/contacts/[id]` | Same contact. Scroll the timeline to a Gmail-sourced message (look for the Gmail icon/source badge on a timeline entry). Capture a viewport-height slice showing 2-3 Gmail entries with blurred bodies. |

Reuse blur selectors already in `redaction-rules.json` for `/settings` and `/contacts/:id`. Add new ones only if you discover PII not covered.

- [ ] **Step 2: Eyeball PNGs**

Specifically check: the BCC address shot still shows the unique `+hash` part clearly (the hash is the documented value users copy — don't blur it). Only the user-controlled email prefix should be blurred.

- [ ] **Step 3: Embed images**

In `docs/docs/features/gmail.md`:

After line 12 (end of "Authentication" paragraph, before `## Email Sync`), insert:

```markdown

![Gmail section in Settings](/img/screenshots/gmail/settings-section.png)
```

After line 26 (end of "Email Sync" body, just before `## BCC Email Logging`), insert:

```markdown

![Gmail thread messages in a contact's interaction timeline](/img/screenshots/gmail/timeline-thread.png)
```

After line 40 (end of "BCC Email Logging" body — after "No custom domain or email infrastructure required..."), insert:

```markdown

![BCC address with copy button on the contact detail page](/img/screenshots/gmail/bcc-address.png)
```

- [ ] **Step 4: Commit**

```bash
git add docs/static/img/screenshots/gmail docs/docs/features/gmail.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): gmail integration"
```

---

### Task 6: Capture screenshots for `identity.md`

**Files:**
- Create: `docs/static/img/screenshots/identity/queue.png`
- Create: `docs/static/img/screenshots/identity/comparison-card.png`
- Modify: `docs/docs/features/identity.md`
- Modify: `docs/screenshots/redaction-rules.json`

- [ ] **Step 1: Add per-route blur selectors**

Add to `docs/screenshots/redaction-rules.json`:

```json
"/identity": {
  "blur": [
    ".match-card .contact-name",
    ".match-card .contact-email",
    ".match-card .contact-phone",
    ".match-card .contact-company",
    ".match-card img"
  ]
}
```

Adjust to actual DOM if class names differ.

- [ ] **Step 2: Capture two shots**

| Filename | Route | State setup |
|---|---|---|
| `identity/queue.png` | `/identity` | Wait for the queue to load. Scroll to top. Frame the full queue with multiple side-by-side comparison cards visible. If the queue is empty, surface the empty state instead — note this and skip step 3's comparison shot. |
| `identity/comparison-card.png` | `/identity` | Same page. Focus a single comparison card — either via element capture or by scrolling/zooming so one card fills the viewport. Both contact panels and the Merge/Reject buttons must be visible. |

If the prod queue is empty: trigger an on-demand scan via the **Scan** button, wait for results, then capture. If it remains empty, capture only the empty state as `identity/queue.png` and skip `comparison-card.png` — adjust embed in Step 4 accordingly.

- [ ] **Step 3: Eyeball PNGs**

Confirm names and emails blurred on both sides of each comparison card.

- [ ] **Step 4: Embed images**

In `docs/docs/features/identity.md`:

After line 8 (page opening paragraph, before `## Tier 1: Deterministic Matching`), insert:

```markdown

![Identity resolution queue](/img/screenshots/identity/queue.png)
```

After line 60 (end of "Manual Review Queue" subsection, before `## On-Demand Scan`), insert (skip this insert if `comparison-card.png` was not captured):

```markdown

![Side-by-side comparison card with merge and reject actions](/img/screenshots/identity/comparison-card.png)
```

- [ ] **Step 5: Commit**

```bash
git add docs/static/img/screenshots/identity docs/docs/features/identity.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): identity resolution"
```

---

### Task 7: Capture screenshots for `linkedin.md`

**Files:**
- Create: `docs/static/img/screenshots/linkedin/settings-section.png`
- Create: `docs/static/img/screenshots/linkedin/pairing-modal.png`
- Modify: `docs/docs/features/linkedin.md`

- [ ] **Step 1: Capture two shots**

| Filename | Route | State setup |
|---|---|---|
| `linkedin/settings-section.png` | `/settings` | Scroll to the LinkedIn section. Show connection status, "Connect" or "Disconnect" button, and any sync stats (profiles synced, last sync time — these may need blurring if they expose anything). |
| `linkedin/pairing-modal.png` | `/settings` | Click "Connect" on the LinkedIn row (disconnect first if currently connected — re-connect after the shot). Wait for the pairing-code modal to render. Capture with the pairing-code input field empty. The example code shown (`PING-XXXXXX`) on the modal is not PII. |

If reconnecting after disconnect is risky (might lose extension token, brick a sync), an alternative is to capture the connected-state settings shot only and skip the pairing modal. Decide based on the user's risk tolerance — if unclear, ask before disconnecting.

- [ ] **Step 2: Eyeball PNGs**

Verify the sync statistics don't expose internal counts you'd prefer kept private. If they do, add a selector to the route's blur list and re-capture.

- [ ] **Step 3: Embed images**

In `docs/docs/features/linkedin.md`:

After line 21 (end of "Installing the Extension" steps, before `## Extension Pairing`), insert:

```markdown

![LinkedIn section in Settings](/img/screenshots/linkedin/settings-section.png)
```

After line 31 (end of "Extension Pairing" subsection, after the "Pairing codes expire after 10 minutes..." paragraph), insert:

```markdown

![Pairing code entry modal](/img/screenshots/linkedin/pairing-modal.png)
```

- [ ] **Step 4: Commit**

```bash
git add docs/static/img/screenshots/linkedin docs/docs/features/linkedin.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): linkedin integration"
```

---

### Task 8: Capture screenshots for `map.md`

**Files:**
- Create: `docs/static/img/screenshots/map/overview.png`
- Create: `docs/static/img/screenshots/map/focus.png`
- Create: `docs/static/img/screenshots/map/cluster.png`
- Modify: `docs/docs/features/map.md`
- Modify: `docs/screenshots/redaction-rules.json`

- [ ] **Step 1: Add per-route blur selectors**

Add to `docs/screenshots/redaction-rules.json`:

```json
"/map": {
  "blur": [
    ".map-sidebar .contact-name",
    ".map-sidebar img",
    ".map-popup .contact-name"
  ]
}
```

- [ ] **Step 2: Capture three shots**

| Filename | Route | State setup |
|---|---|---|
| `map/overview.png` | `/map` | Wait for the Mapbox tiles to load (~2s). Default world view. Sidebar populated with contacts in viewport. |
| `map/focus.png` | `/map?focus=<contact-id>` | Use the same contact ID from Task 3 if that contact has a geocoded location; otherwise pick any geocoded contact. Wait for map to zoom to city-level. |
| `map/cluster.png` | `/map` | Zoom out (programmatically via map state, or by clicking the zoom-out control 4-5 times) until multiple cluster bubbles appear. |

Map tiles need extra wait time — add a 1500ms wait after navigation/zoom before capturing.

- [ ] **Step 3: Eyeball PNGs**

Pin markers themselves are fine — they're location dots, not PII. The sidebar contact names and avatars must be blurred. Map popups (if any are open) must have blurred names.

- [ ] **Step 4: Embed images**

In `docs/docs/features/map.md`:

After line 8 (opening paragraph, before `## How it works`), insert:

```markdown

![Map view with contacts plotted globally](/img/screenshots/map/overview.png)
```

After line 19 (end of "Opening the map" — under bullet 2 about `?focus=`, before "If a contact's location..."), insert:

```markdown

![Map focused on a single contact](/img/screenshots/map/focus.png)
```

After line 33 (end of "Clustering" subsection, before `## Geocoding`), insert:

```markdown

![Cluster bubbles at zoomed-out view](/img/screenshots/map/cluster.png)
```

- [ ] **Step 5: Commit**

```bash
git add docs/static/img/screenshots/map docs/docs/features/map.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): map page"
```

---

### Task 9: Capture screenshots for `mcp.md`

**Files:**
- Create: `docs/static/img/screenshots/mcp/settings-section.png`
- Create: `docs/static/img/screenshots/mcp/generated-key-modal.png`
- Modify: `docs/docs/features/mcp.md`

- [ ] **Step 1: Capture two shots**

| Filename | Route | State setup |
|---|---|---|
| `mcp/settings-section.png` | `/settings` | Scroll to "MCP Access" section under Account. Frame the Generate key button and any status indicator. Capture **before** generating a new key (so no plaintext key appears). |
| `mcp/generated-key-modal.png` | `/settings` | Click "Generate key" / "Regenerate". The plaintext key appears once — **this is sensitive, must be blurred**. Add a one-shot blur selector for the key field (e.g. `[data-testid='generated-api-key']` or the code/pre containing the key). Capture, then dismiss the modal and immediately revoke the generated key so it doesn't remain active. |

**Critical:** never commit an unblurred key. Eyeball this shot before committing. If you can read the key, redo with a tighter selector.

- [ ] **Step 2: Eyeball PNGs**

`mcp/generated-key-modal.png` — confirm the plaintext key is fully blurred. Anything starting with `pingcrm_` must not be legible.

- [ ] **Step 3: Embed images**

In `docs/docs/features/mcp.md`:

After line 22 (end of "Available Tools" table, before `## Setup`), insert:

```markdown

![MCP Access section in Settings](/img/screenshots/mcp/settings-section.png)
```

After line 28 (end of "1. Generate an API Key" paragraph, before `### 2. Configure Your AI Client`), insert:

```markdown

![Generated API key modal — shown once, copy immediately](/img/screenshots/mcp/generated-key-modal.png)
```

- [ ] **Step 4: Commit**

```bash
git add docs/static/img/screenshots/mcp docs/docs/features/mcp.md
git commit -m "docs(screenshots): mcp server"
```

---

### Task 10: Capture screenshots for `notifications.md`

**Files:**
- Create: `docs/static/img/screenshots/notifications/feed.png`
- Create: `docs/static/img/screenshots/notifications/filter-unread.png`
- Create: `docs/static/img/screenshots/notifications/navbar-badge.png`
- Modify: `docs/docs/features/notifications.md`
- Modify: `docs/screenshots/redaction-rules.json`

- [ ] **Step 1: Add per-route blur selectors**

```json
"/notifications": {
  "blur": [
    ".notification-row .contact-name",
    ".notification-row .preview-text"
  ]
}
```

- [ ] **Step 2: Capture three shots**

| Filename | Route | State setup |
|---|---|---|
| `notifications/feed.png` | `/notifications` | Wait for feed to load. Default "All" tab. Frame the tabs at top + first 5-7 notification rows. |
| `notifications/filter-unread.png` | `/notifications` | Click the "Unread" tab. Wait for filtered list to render. Capture. |
| `notifications/navbar-badge.png` | `/dashboard` (or any page with the navbar visible) | Ensure there are unread notifications (do not mark all read first). Capture the top navbar area only — if agent-browser supports element-level capture, crop to the navbar; otherwise full viewport and the embed will rely on the badge being visible in context. |

- [ ] **Step 3: Eyeball PNGs**

Contact names in notification rows must be blurred. Notification preview text (e.g. "Alex changed their bio from X to Y") must be blurred where it contains the contact's name or bio content.

- [ ] **Step 4: Embed images**

In `docs/docs/features/notifications.md`:

After line 8 (opening paragraph, before `## Notification Types`), insert:

```markdown

![Notifications feed](/img/screenshots/notifications/feed.png)
```

After line 22 (end of "Notification Types" bullet list, before `## Actions`), insert:

```markdown

![Unread filter tab](/img/screenshots/notifications/filter-unread.png)
```

After line 33 (end of "Actions" subsection navigation list, before `## Filter Tabs`), insert:

```markdown

![Unread badge in the navbar](/img/screenshots/notifications/navbar-badge.png)
```

- [ ] **Step 5: Commit**

```bash
git add docs/static/img/screenshots/notifications docs/docs/features/notifications.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): notifications page"
```

---

### Task 11: Capture screenshots for `organizations.md`

**Files:**
- Create: `docs/static/img/screenshots/organizations/list.png`
- Create: `docs/static/img/screenshots/organizations/detail.png`
- Create: `docs/static/img/screenshots/organizations/merge-selection.png`
- Modify: `docs/docs/features/organizations.md`
- Modify: `docs/screenshots/redaction-rules.json`

- [ ] **Step 1: Add per-route blur selectors**

Organization names are arguably not as sensitive as personal names — many are public companies. But the **linked contact names** on the org detail page are PII. Add:

```json
"/organizations/:id": {
  "blur": [
    "[data-testid='org-contacts-table'] .contact-name",
    "[data-testid='org-contacts-table'] img",
    "[data-testid='org-notes']"
  ]
}
```

Leave `/organizations` route blur empty unless the org list itself shows contact names (it doesn't per the docs — only org name, contact count, scores).

- [ ] **Step 2: Capture three shots**

| Filename | Route | State setup |
|---|---|---|
| `organizations/list.png` | `/organizations` | Default sort. Wait for table to render. Scroll to top. |
| `organizations/detail.png` | `/organizations/[id]` | Pick an org with 5+ linked contacts and non-empty notes. Wait for the stats and contacts table to render. |
| `organizations/merge-selection.png` | `/organizations` | Select 2-3 organization rows. Wait for the merge action button to enable. Capture with rows checked and the merge button visible. |

- [ ] **Step 3: Eyeball PNGs**

`organizations/detail.png` — contact names in the linked-contacts table must be blurred. Notes must be blurred (private content).

- [ ] **Step 4: Embed images**

In `docs/docs/features/organizations.md`:

After line 12 (opening of "Organization List", before `### Table Columns`), insert:

```markdown

![Organizations list](/img/screenshots/organizations/list.png)
```

After line 41 (end of "Actions" subsection bullet list, before `## Organization Detail`), insert:

```markdown

![Selecting multiple organizations for merge](/img/screenshots/organizations/merge-selection.png)
```

After line 45 (opening of "Organization Detail", before `### Inline Editing`), insert:

```markdown

![Organization detail page](/img/screenshots/organizations/detail.png)
```

- [ ] **Step 5: Commit**

```bash
git add docs/static/img/screenshots/organizations docs/docs/features/organizations.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): organizations"
```

---

### Task 12: Capture screenshots for `settings.md`

**Files:**
- Create: `docs/static/img/screenshots/settings/overview.png`
- Create: `docs/static/img/screenshots/settings/connected-accounts.png`
- Create: `docs/static/img/screenshots/settings/followup-rules.png`
- Create: `docs/static/img/screenshots/settings/tags.png`
- Create: `docs/static/img/screenshots/settings/csv-import.png`
- Modify: `docs/docs/features/settings.md`
- Modify: `docs/screenshots/redaction-rules.json`

- [ ] **Step 1: Add per-route blur selectors**

The settings page shows connected email addresses, phone numbers, and Twitter/Telegram handles — all PII. Add:

```json
"/settings": {
  "blur": [
    "[data-testid='connected-email']",
    "[data-testid='connected-phone']",
    "[data-testid='connected-twitter-handle']",
    "[data-testid='connected-linkedin-profile']"
  ]
}
```

- [ ] **Step 2: Capture five shots**

| Filename | Route | State setup |
|---|---|---|
| `settings/overview.png` | `/settings` | Scroll to top. Frame the integrations grid / first viewport-worth. |
| `settings/connected-accounts.png` | `/settings` | Scroll to and frame all integration rows (Gmail, Telegram, Twitter, LinkedIn, WhatsApp) showing their connected/disconnected badges side by side. |
| `settings/followup-rules.png` | `/settings` | Scroll to "Follow-up Rules" section. Capture with the three priority interval inputs visible. |
| `settings/tags.png` | `/settings` | Scroll to "Tags" section. If tag taxonomy is empty, generate or seed a few tags first. |
| `settings/csv-import.png` | `/settings` | Scroll to "CSV Import" section. Frame the dropzone clearly. |

- [ ] **Step 3: Eyeball PNGs**

Connected email and phone must be blurred. Tag names are fine (they're taxonomy, not PII).

- [ ] **Step 4: Embed images**

In `docs/docs/features/settings.md`:

After line 8 (opening paragraph, before `## Gmail`), insert:

```markdown

![Settings page overview](/img/screenshots/settings/overview.png)

![Connected accounts at a glance](/img/screenshots/settings/connected-accounts.png)
```

After line 47 (end of "CSV Import" body), insert:

```markdown

![CSV import dropzone](/img/screenshots/settings/csv-import.png)
```

After line 51 (end of "Follow-up Rules" subsection), insert:

```markdown

![Follow-up interval settings per priority level](/img/screenshots/settings/followup-rules.png)
```

After line 55 (end of "Tags" subsection, before `## MCP Access`), insert:

```markdown

![Tag taxonomy management](/img/screenshots/settings/tags.png)
```

- [ ] **Step 5: Commit**

```bash
git add docs/static/img/screenshots/settings docs/docs/features/settings.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): settings page"
```

---

### Task 13: Capture screenshots for `suggestions.md`

**Files:**
- Create: `docs/static/img/screenshots/suggestions/inbox.png`
- Create: `docs/static/img/screenshots/suggestions/card-expanded.png`
- Create: `docs/static/img/screenshots/suggestions/snooze-menu.png`
- Modify: `docs/docs/features/suggestions.md`
- Modify: `docs/screenshots/redaction-rules.json`

- [ ] **Step 1: Add per-route blur selectors**

```json
"/suggestions": {
  "blur": [
    ".suggestion-card .contact-name",
    ".suggestion-card img",
    ".suggestion-card .ai-draft-text",
    ".suggestion-card .trigger-context"
  ]
}
```

- [ ] **Step 2: Capture three shots**

| Filename | Route | State setup |
|---|---|---|
| `suggestions/inbox.png` | `/suggestions` | Wait for cards to load. Frame 3-5 cards stacked. |
| `suggestions/card-expanded.png` | `/suggestions` | Click the first card to expand. Wait for AI-drafted message body to render. Capture showing the expanded card with action buttons (Send, Snooze, Dismiss). |
| `suggestions/snooze-menu.png` | `/suggestions` | Same expanded card. Click "Snooze" to open the duration menu (2 weeks / 1 month / 3 months). Capture with the menu open. |

If `/suggestions` is empty (no pending suggestions), trigger a fresh suggestion generation via whatever admin path exists or wait for the daily cron. If still empty, capture the empty state ("all caught up") as `inbox.png` and skip the other two.

- [ ] **Step 3: Eyeball PNGs**

AI draft text on the expanded card must be fully blurred — it contains the contact's name and personal context.

- [ ] **Step 4: Embed images**

In `docs/docs/features/suggestions.md`:

After line 8 (opening paragraph, before `## How Suggestions Are Generated`), insert:

```markdown

![Suggestions inbox](/img/screenshots/suggestions/inbox.png)
```

After line 95 (end of "AI Message Composer" section, before `## Contact Avatars`), insert (skip if not captured):

```markdown

![Expanded suggestion card with AI-drafted message](/img/screenshots/suggestions/card-expanded.png)
```

After line 111 (in the "Snooze" bullet under `## Actions`, after "3 months" line and the "Snoozed suggestions..." paragraph), insert (skip if not captured):

```markdown

![Snooze duration menu](/img/screenshots/suggestions/snooze-menu.png)
```

- [ ] **Step 5: Commit**

```bash
git add docs/static/img/screenshots/suggestions docs/docs/features/suggestions.md docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): suggestions page"
```

---

### Task 14: Capture screenshots for `telegram.md`

**Files:**
- Create: `docs/static/img/screenshots/telegram/settings-section.png`
- Create: `docs/static/img/screenshots/telegram/connect-phone.png`
- Create: `docs/static/img/screenshots/telegram/common-groups.png`
- Create: `docs/static/img/screenshots/telegram/timeline-readreceipts.png`
- Modify: `docs/docs/features/telegram.md`

- [ ] **Step 1: Capture four shots**

| Filename | Route | State setup |
|---|---|---|
| `telegram/settings-section.png` | `/settings` | Scroll to Telegram section. Show connected status, 2nd Tier toggle, sync controls. |
| `telegram/connect-phone.png` | `/settings` | Click "Connect via phone" (only if currently disconnected — do NOT disconnect a working integration just to capture this; if currently connected, skip this shot). Wait for the phone-number entry modal. |
| `telegram/common-groups.png` | `/contacts/[id]` | Pick a contact with shared Telegram groups (look for the "Common groups" sidebar card). Scroll the sidebar into view. |
| `telegram/timeline-readreceipts.png` | `/contacts/[id]` | Same or another contact with Telegram messages in the timeline showing read-receipt checkmarks. Frame 2-3 timeline entries with checkmarks visible. |

For the connect-phone shot: only capture if the integration is currently disconnected for some test user, OR if the modal can be opened without actually disconnecting. If neither is possible, skip — the embed step below has a fallback.

- [ ] **Step 2: Eyeball PNGs**

Common group names — these could be sensitive (private group titles). Either blur or pick a contact whose common groups are generic. The contact's name in the timeline header must be blurred.

- [ ] **Step 3: Embed images**

In `docs/docs/features/telegram.md`:

After line 8 (opening paragraph, before `## Authentication`), insert:

```markdown

![Telegram section in Settings](/img/screenshots/telegram/settings-section.png)
```

After line 17 (end of "Authentication" steps numbered list, before "Once authenticated..."), insert (skip if `connect-phone.png` not captured):

```markdown

![Telegram phone-number entry modal](/img/screenshots/telegram/connect-phone.png)
```

After line 121 (end of "Common Groups" subsection), insert:

```markdown

![Common Telegram groups sidebar on the contact detail page](/img/screenshots/telegram/common-groups.png)
```

After line 41 (end of "How it works" subsection under "Chat Sync"), insert:

```markdown

![Telegram messages with read-receipt indicators in the timeline](/img/screenshots/telegram/timeline-readreceipts.png)
```

- [ ] **Step 4: Commit**

```bash
git add docs/static/img/screenshots/telegram docs/docs/features/telegram.md
git commit -m "docs(screenshots): telegram integration"
```

---

### Task 15: Capture screenshots for `twitter.md`

**Files:**
- Create: `docs/static/img/screenshots/twitter/settings-section.png`
- Create: `docs/static/img/screenshots/twitter/bio-change-timeline.png`
- Create: `docs/static/img/screenshots/twitter/event-in-suggestion.png`
- Modify: `docs/docs/features/twitter.md`

- [ ] **Step 1: Capture three shots**

| Filename | Route | State setup |
|---|---|---|
| `twitter/settings-section.png` | `/settings` | Scroll to Twitter section. Show connected status, OAuth state, and bird-cookies status indicator. |
| `twitter/bio-change-timeline.png` | `/contacts/[id]` | Find a contact with a "Bio change" timeline event (search through contacts or trigger an event). Frame the bio-change entry showing old vs new bio (both will be blurred). |
| `twitter/event-in-suggestion.png` | `/suggestions` | Find a suggestion with a Twitter-event trigger (badge says `New event` and the card context mentions a job change / tweet). Capture the expanded card. |

If no bio-change event exists in any contact timeline, skip `bio-change-timeline.png`. If no event-based suggestion exists, skip `event-in-suggestion.png`. Adjust embed step accordingly.

- [ ] **Step 2: Eyeball PNGs**

Bio text (old and new) on the change event must be blurred. AI-draft text on the suggestion card must be blurred.

- [ ] **Step 3: Embed images**

In `docs/docs/features/twitter.md`:

After line 21 (end of "Connecting your X account" — after "self-repairs."), insert:

```markdown

![Twitter section in Settings](/img/screenshots/twitter/settings-section.png)
```

After line 45 (end of "Bio Monitoring" subsection, before `## Event Classification`), insert (skip if not captured):

```markdown

![Bio change event in the contact timeline](/img/screenshots/twitter/bio-change-timeline.png)
```

After line 62 (end of "Event Classification" body — after "See [Follow-Up Suggestions]..."), insert (skip if not captured):

```markdown

![Event-triggered suggestion referencing a recent tweet](/img/screenshots/twitter/event-in-suggestion.png)
```

- [ ] **Step 4: Commit**

```bash
git add docs/static/img/screenshots/twitter docs/docs/features/twitter.md
git commit -m "docs(screenshots): twitter integration"
```

---

### Task 16: Capture screenshots for `whatsapp.md`

**Files:**
- Create: `docs/static/img/screenshots/whatsapp/settings-section.png`
- Create: `docs/static/img/screenshots/whatsapp/qr-code.png`
- Create: `docs/static/img/screenshots/whatsapp/timeline.png`
- Modify: `docs/docs/features/whatsapp.md`

- [ ] **Step 1: Capture three shots**

| Filename | Route | State setup |
|---|---|---|
| `whatsapp/settings-section.png` | `/settings` | Scroll to WhatsApp section. Show connected status. |
| `whatsapp/qr-code.png` | `/settings` | Click "Connect WhatsApp". Wait for QR code to render. The QR code itself is **session-bound and ephemeral** — once the modal is closed it's invalidated, so it's safe to publish (no PII). Do not scan it. Capture, then close the modal without scanning. |
| `whatsapp/timeline.png` | `/contacts/[id]` | Pick a contact with WhatsApp messages in the timeline. Frame 2-3 entries with the WhatsApp source badge visible. |

If currently disconnected, the QR shot is the natural state. If currently connected and you don't want to disconnect/reconnect just for the screenshot, skip the QR shot — the connect button itself in the settings section is enough.

- [ ] **Step 2: Eyeball PNGs**

WhatsApp message bodies in the timeline must be blurred. QR code is fine unblurred (ephemeral and invalidated when modal closes).

- [ ] **Step 3: Embed images**

In `docs/docs/features/whatsapp.md`:

After line 9 (opening paragraph, before `## Architecture`), insert:

```markdown

![WhatsApp section in Settings](/img/screenshots/whatsapp/settings-section.png)
```

After line 25 (end of "Authentication" numbered list, before "Sessions can expire..."), insert (skip if not captured):

```markdown

![QR code for linking a new WhatsApp device](/img/screenshots/whatsapp/qr-code.png)
```

After line 49 (end of "Initial backfill" subsection under "Message Sync"), insert:

```markdown

![WhatsApp messages in a contact's timeline](/img/screenshots/whatsapp/timeline.png)
```

- [ ] **Step 4: Commit**

```bash
git add docs/static/img/screenshots/whatsapp docs/docs/features/whatsapp.md
git commit -m "docs(screenshots): whatsapp integration"
```

---

## Phase 3 — Review and ship

### Task 17: Full-PII review pass

**Files:** none modified directly; may re-capture and re-commit shots that fail review.

- [ ] **Step 1: Enumerate all captured PNGs**

```bash
find docs/static/img/screenshots -name '*.png' -type f | sort
```

Expected count: ~40-45 (depending on which optional shots were skipped per per-task notes).

- [ ] **Step 2: Open every PNG and inspect**

For each image, check:

- No fully legible personal name (first + last together).
- No legible email address (anything matching `<chars>@<chars>` font-rendered, even partial).
- No legible phone number.
- No legible message body text (you should not be able to read more than a couple of characters in a row).
- No legible avatar face (avatars should be blurred enough that you can't identify the person).
- No legible API keys (anything `pingcrm_<chars>` must be fully blurred).
- No legible bio text on bio-change events.
- Sync stats / counts on settings page acceptable (these are about your usage, judge based on what you'd be comfortable publishing).

- [ ] **Step 3: For any image that fails review**

Re-run the relevant Phase 2 task's capture step for that one image. Add the missing selector to `redaction-rules.json` (route-specific or global, depending on whether it applies broadly). Re-capture, re-verify, commit the fix:

```bash
git add docs/static/img/screenshots/<feature>/<file>.png docs/screenshots/redaction-rules.json
git commit -m "docs(screenshots): fix PII leak in <feature>/<file>"
```

- [ ] **Step 4: Confirm task complete**

When every image passes inspection, no further commits in this task. Proceed to Task 18.

---

### Task 18: Docusaurus build verification

**Files:** none modified unless a build error surfaces.

- [ ] **Step 1: Run the Docusaurus dev server**

```bash
cd docs && npm run start
```

Wait for "compiled successfully" output.

- [ ] **Step 2: Walk every modified feature page in the browser**

Open `http://localhost:3000/docs/features/contacts` and visually confirm each embedded screenshot renders correctly (no broken image icons, no 404 in browser devtools network tab). Repeat for: dashboard, gmail, identity, linkedin, map, mcp, notifications, organizations, settings, suggestions, telegram, twitter, whatsapp.

- [ ] **Step 3: Run the production build**

```bash
cd docs && npm run build
```

Confirm exit code 0. The build will fail on broken image links.

- [ ] **Step 4: Stop the dev server**

Ctrl-C the dev server process started in Step 1.

- [ ] **Step 5: If any error surfaced**

Fix the broken paths in the relevant `.md` file. Common causes:

- Typo in `/img/screenshots/<feature>/<file>.png` path.
- Missing PNG file (capture was skipped but embed was added).
- Wrong file extension.

Commit the fix:

```bash
git add docs/docs/features/<file>.md
git commit -m "docs(screenshots): fix broken image reference"
```

Re-run Step 3 until the build is clean.

---

### Task 19: Open the PR

**Files:** no file changes.

- [ ] **Step 1: Push the branch**

If currently on main, branch first:

```bash
git checkout -b docs/prod-screenshots
git push -u origin docs/prod-screenshots
```

If already on a feature branch:

```bash
git push
```

- [ ] **Step 2: Create the PR**

```bash
gh pr create --title "docs: prod screenshots for every feature page" --body "$(cat <<'EOF'
## Summary

- Captures multi-shot screenshots from prod for every page in `docs/docs/features/`.
- PII redacted in-browser via CSS blur before each capture; rules version-controlled at `docs/screenshots/redaction-rules.json`.
- Images embedded inline in each `.md` at relevant subsection anchors.
- ~45 total shots across 14 feature pages.

## Test plan

- [ ] `npm run build` in `docs/` exits 0.
- [ ] Every embedded image loads in `npm run start` locally.
- [ ] Manual PII review pass complete — no legible names, emails, phone numbers, message bodies, API keys, or recognizable avatars.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Report the PR URL**

Echo the PR URL from `gh pr create`'s output to the user.

---

## Notes on agent-browser usage

- This entire plan assumes the executing agent invokes the **agent-browser:agent-browser** skill (Skill tool) at the start of execution and follows its documented command surface for navigation, JS evaluation, viewport sizing, and screenshot capture.
- A single agent-browser session can typically remain logged in across many navigations. Reuse the session across all per-feature tasks where possible. If the session expires (cookie age, server-side eviction), re-log in.
- If capturing many shots in one long session proves brittle (network timeouts, agent-browser process leaks), the per-feature tasks are independent — split into multiple sessions, one per task.
- For tasks that risk disconnecting a working integration (Telegram phone modal, WhatsApp QR, LinkedIn pairing re-issue), prefer to **skip the shot** rather than break a live sync. The plan's embed steps are marked as skippable where applicable.
