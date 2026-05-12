---
sidebar_position: 3
---

# Update Notifications

Self-hosted PingCRM instances show an in-app banner when a new release is
available on GitHub. This page explains how the check works and how to turn
it off.

## How it works

- Your backend polls `https://api.github.com/repos/sneg55/pingcrm/releases/latest`
  every 6 hours via a Celery beat task.
- The latest release tag is cached in Redis (12-hour TTL) and compared to the
  version baked into your running image (the `APP_VERSION` env, set at build
  time from the git tag).
- When a newer version exists, all logged-in users see a dismissible banner
  with the inline changelog and a link to the GitHub release page.
- **No data leaves your instance.** The check is a direct HTTPS call from your
  server to `api.github.com`. PingCRM doesn't operate any telemetry endpoint.

## Disabling the check

Set `DISABLE_UPDATE_CHECK=1` in your `.env`:

```bash
DISABLE_UPDATE_CHECK=1
```

This stops the beat task from calling GitHub and hides the banner. Useful for
air-gapped deployments or if you simply don't want the dependency.

## Pinning to a specific version

By default `docker-compose.prod.yml` uses `:latest`. To pin:

```yaml
services:
  backend:
    image: ghcr.io/sneg55/pingcrm/backend:v1.7.0
  frontend:
    image: ghcr.io/sneg55/pingcrm/frontend:v1.7.0
```

Available tag forms:
- `:v1.7.0` — exact version
- `:1.7` — latest patch in the 1.7 line
- `:1` — latest minor in the 1.x line
- `:latest` — most recent release

## Dev / SHA builds

If your image was built from a `main` branch push (not a tagged release),
`APP_VERSION` is set to the short commit SHA. In that case the banner stays
hidden — we can't compare a SHA to a semver tag. Pull a tagged image to
re-enable the check.
