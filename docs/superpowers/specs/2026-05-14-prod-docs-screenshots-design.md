# Prod Screenshots for Docs Site

**Date:** 2026-05-14
**Status:** Design approved, awaiting plan

## Goal

Every feature page in `docs/docs/features/` gets multiple screenshots illustrating its key subsections, captured from prod (`pingcrm.sawinyh.com`), embedded inline in the `.md` files, in a single PR. Screenshots are PII-redacted before publication.

## Scope

### In scope

- All 14 files under `docs/docs/features/`: contacts, dashboard, gmail, identity, linkedin, map, mcp, notifications, organizations, settings, suggestions, telegram, twitter, whatsapp.
- Multi-shot per page: one screenshot per meaningful subsection (estimated 40–60 total).
- Desktop viewport, light theme.
- Capture from prod.
- Inline embedding in the same PR as the image assets.

### Out of scope

- `architecture.md`, `api-reference.md`, `contributing.md`, `intro.md`, `setup.md` — text-only or OAuth screens we don't own.
- `operations/updates.md` — text-only.
- Mobile breakpoints, dark theme, animated GIFs.

## Capture workflow

Use the **agent-browser** skill end-to-end (per project rule: never write custom Playwright scripts).

For each shot:

1. Log into prod with the prod account (creds in `CLAUDE.local.md`).
2. Navigate to the target route.
3. Set up the required UI state (open modal, select rows for bulk actions, scroll to a specific section, apply a filter, etc.).
4. Inject the PII-blur stylesheet for that route.
5. Capture screenshot.
6. Save to `docs/static/img/screenshots/<feature>/<shot-name>.png`.

**Viewport:** 1440×900, light theme, 2× device pixel ratio for sharper retina output.

**Session strategy:** the plan may split capture into per-feature subagent tasks running in parallel to avoid one long brittle session.

## PII redaction

**CSS-based in-browser blur applied immediately before each screenshot.** Not post-capture image editing.

### Rationale

Same visual result (names, emails, avatars, message bodies blurred), but:

- Reproducible — redaction rules are part of the capture script, so re-shooting later does not require a separate editing pass.
- Faster — no per-image manual editing in Preview or scripted Pillow/ImageMagick steps.
- Consistent — every shot of the same route applies the same blur to the same selectors.

### Mechanics

Before screenshotting each route, inject a `<style>` block that applies `filter: blur(5px)` to selectors known to contain PII for that route.

Redaction rules live in a single `docs/screenshots/redaction-rules.json` colocated with the capture script (new `docs/screenshots/` directory at the docs-site root, not under `static/`). Shape:

```json
{
  "routes": {
    "/contacts": {
      "blur": [".contact-row .name", ".contact-row .email", ".contact-row img.avatar"]
    },
    "/contacts/:id": {
      "blur": [".contact-header .name", ".contact-header .email", ".timeline .message-body", ".timeline img.avatar"]
    }
  }
}
```

Generic fallback selectors apply globally (any `[data-pii]`, common contact-name / contact-email class names).

### Human review

Before merging, every screenshot is reviewed by eye for missed PII. Any miss adds a selector to `redaction-rules.json` and triggers a re-capture for that shot.

## Storage and naming

- Path: `docs/static/img/screenshots/<feature>/<shot-name>.png`
- One folder per feature page, folder name matches the `.md` filename without extension.
- Filenames: kebab-case, descriptive of the state shown.

Examples:

| Feature page | Shots |
|---|---|
| `contacts.md` | `contacts/list.png`, `contacts/list-bulk-actions.png`, `contacts/detail.png`, `contacts/detail-timeline.png` |
| `suggestions.md` | `suggestions/inbox.png`, `suggestions/composer.png` |
| `map.md` | `map/overview.png`, `map/focus.png` |

The full per-feature shot list is enumerated in the implementation plan, not here.

## Embedding

Screenshots are referenced inline directly under the subsection they illustrate, using standard Markdown with an absolute path from the site root:

```markdown
## Contact List

The `/contacts` page displays all contacts in a searchable, sortable, paginated table.

![Contact list view](/img/screenshots/contacts/list.png)
```

A one-line italic caption is added underneath when the shot needs explanation. No `ThemedImage` (light theme only).

## Manifest as a separate artifact

The exact shot list per feature page belongs in the **implementation plan**, not in this design doc. It is enumerable rather than architectural, and pinning it now would require reading all 14 `.md` files mid-brainstorm.

The plan produces `screenshot-manifest.md` enumerating, per shot:

- Feature `.md` file and target subsection
- Route to navigate to
- UI state setup steps (modal, selection, filter)
- Output filename
- Redaction selectors specific to this route

The manifest doubles as a re-capture script.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Prod UI evolves; screenshots go stale. | Manifest is the re-capture script — re-running it reproduces the same states. |
| New UI element introduces PII not covered by existing selectors. | Human review pass before merge; redaction rules colocated with the capture script so they are version-controlled and re-applied on re-capture. |
| Long single agent-browser session is brittle (~40–60 captures). | Plan may dispatch per-feature subagent tasks in parallel. |
| Real names of the user's contacts leak via incomplete blur. | Two-layer defense: per-route blur rules plus generic fallback selectors; human review gate before merge. |

## Deliverables

1. `docs/static/img/screenshots/<feature>/*.png` — redacted PNG assets.
2. Updated `docs/docs/features/*.md` — inline image references and captions.
3. `docs/screenshots/redaction-rules.json` — version-controlled blur rules.
4. `docs/screenshots/capture.md` — short README explaining how to re-run capture for a given feature.
5. Single PR bundling all of the above.
