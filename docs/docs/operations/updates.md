---
sidebar_position: 3
description: "How self-hosted PingCRM instances detect new releases and show an in-app update banner, and how to upgrade your deployment."
---

# Update Notifications

Self-hosted PingCRM instances show an in-app banner when a new release is
available on GitHub. This page covers how the check works, how to turn it
off, and how to pin image versions.

## How it works

- A Celery beat task polls `https://api.github.com/repos/sneg55/pingcrm/releases/latest`
  every 6 hours. The backend also triggers a check when a logged-in user
  loads the version status and nothing is cached yet.
- The latest release tag is cached in Redis (12-hour TTL) and compared to the
  version baked into your running image (the `APP_VERSION` env, set at build
  time from the git tag). A failed fetch is remembered for 5 minutes before
  the next on-demand attempt.
- When a newer version exists, logged-in users see a banner with a link to
  the GitHub release page and expandable release notes. Dismissing it hides
  that version in the current browser until a newer release appears.
- The check is a direct HTTPS call from your server to `api.github.com`, and
  no data about your instance is sent. PingCRM has no telemetry endpoint.

## Disabling the check

Set `DISABLE_UPDATE_CHECK=1` in the environment of the backend and worker (any non-empty value works, including `0`):

```bash
DISABLE_UPDATE_CHECK=1
```

This stops the beat task from calling GitHub and hides the banner. It suits
air-gapped deployments and anyone who does not want the dependency.

`docker-compose.prod.yml` does not forward this variable, so add it under the
`environment` block of the `backend` and `worker` services.

## Pinning to a specific version

`docker-compose.prod.yml` uses `:latest` by default. To pin a release:

```yaml
services:
  backend:
    image: ghcr.io/sneg55/pingcrm/backend:1.9.0
  frontend:
    image: ghcr.io/sneg55/pingcrm/frontend:1.9.0
```

Available tag forms for the backend and frontend images:
- `:1.9.0`: exact version
- `:1.9`: latest patch in the 1.9 line
- `:1`: latest minor in the 1.x line
- `:latest`: the newest build, from either a release tag or a push to `main`
- `:<short sha>` and the long SHA: a specific `main` build

The `whatsapp-sidecar` image is published only as `:latest` and by commit SHA.

## Dev / SHA builds

Images built from a `main` branch push (not a tagged release) set
`APP_VERSION` to the 7-character commit SHA, and images built locally without
the build argument use `dev`. In both cases the banner stays hidden, because a
SHA cannot be compared to a semver tag. Since `:latest` is also pushed on
every `main` build, it can carry a SHA version. Pull a tagged image to
re-enable the check.
