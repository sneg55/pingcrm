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
