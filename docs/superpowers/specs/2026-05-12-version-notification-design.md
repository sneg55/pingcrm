# Self-Hoster Version Notification — Design

**Date:** 2026-05-12
**Status:** Approved — ready for implementation plan

## Problem

PingCRM is self-hostable via Docker Compose + GHCR images. Today there is no mechanism for a self-hoster to find out a newer release is available short of watching the GitHub repo manually. We also don't bake a version identifier into images: every build is tagged only `:latest` and `:<sha>`, and the FastAPI app advertises a hardcoded `version="0.1.0"` unrelated to the git tags (currently up to `v1.6.0`).

The goal is: a self-hoster running `:latest` should see an in-app banner when a new semver release ships, with an inline changelog and a link to the GitHub release, without sending any telemetry to a central PingCRM-operated server.

## Non-Goals

- SaaS users on `pingcrm.sawinyh.com` — they get features by virtue of the operator deploying; no banner needed.
- Auto-updates / in-app upgrade button — self-hosters control their own deploys; we surface info only.
- Telemetry / install counts — the check goes directly to GitHub from the self-hoster's instance; we do not phone home.
- Multi-user "instance admin" permission model — PingCRM is single-player; every authenticated user sees the banner.

## Decisions Locked In

| Decision | Choice |
|---|---|
| Audience | Self-hosters |
| Surface | In-app banner, top of authenticated layout |
| Latest-version source | Poll GitHub Releases API directly from the self-hoster's instance |
| Self-identity | `APP_VERSION` baked at image build time from git tag (or short SHA on main) |
| Visibility | All authenticated users (single-player) |
| Default behavior | On by default; opt-out via `DISABLE_UPDATE_CHECK=1` |
| CTA | Inline rendered changelog + "View on GitHub" link |
| Dismissal | Per-browser localStorage keyed by target version |

## Architecture

```
┌─────────────────┐                  ┌─────────────────┐
│  Celery beat    │  every 6h        │  api.github.com │
│  check_for_     │ ───────────────▶ │ /releases/latest│
│  updates task   │                  └─────────────────┘
└────────┬────────┘
         │ cache result
         ▼
┌─────────────────┐
│  Redis          │  key: pingcrm:version:latest, TTL 12h
└────────┬────────┘
         │ read
         ▼
┌─────────────────┐                  ┌─────────────────┐
│ GET /api/v1/    │ ◀──── auth req ──│ Frontend hook   │
│ version         │                  │ use-version.ts  │
└─────────────────┘                  └────────┬────────┘
                                              │
                                              ▼
                                     ┌─────────────────┐
                                     │ <VersionBanner/>│
                                     │ in app layout   │
                                     └─────────────────┘
```

Three layers:

1. **Build-time:** CI stamps `APP_VERSION` env into images and tags GHCR with semver fan-out on git-tag pushes.
2. **Backend:** Celery beat polls GitHub every 6h, caches in Redis. Authenticated endpoint serves cached comparison.
3. **Frontend:** React Query hook fetches once per session; banner renders if update available and not locally dismissed.

## Build-Time Versioning

### Dockerfiles
Both `backend/Dockerfile` and `frontend/Dockerfile`:

```dockerfile
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
```

### CI workflow (`.github/workflows/deploy.yml`)

- On push to `main`: existing build step gains `build-args: APP_VERSION=${{ github.sha }}` (use short sha — first 7 chars).
- New workflow trigger for `push: tags: ['v*']` using `docker/metadata-action@v5` to generate semver tag fan-out: `:v1.7.0`, `:1.7`, `:1`, plus `:latest`. Pass `APP_VERSION=${{ github.ref_name }}` as build arg. Tag pushes and main-branch pushes are distinct events so the jobs don't race; both produce `:latest`, with the tag-build winning when both happen (which is fine — they're built from the same commit).
- The existing `:latest` + `:<sha>` tagging on `main` pushes is preserved unchanged. Self-hosters who pin nothing keep working.

### Backend startup
`backend/app/core/version.py`:

```python
import os
import re
from packaging.version import Version, InvalidVersion

APP_VERSION = os.getenv("APP_VERSION", "dev")
_SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+([-.+].*)?$")

def is_semver_build() -> bool:
    return bool(_SEMVER_RE.match(APP_VERSION))

def parse_current() -> Version | None:
    if not is_semver_build():
        return None
    try:
        return Version(APP_VERSION.lstrip("v"))
    except InvalidVersion:
        return None
```

`backend/app/main.py` swaps the hardcoded `version="0.1.0"` for `version=APP_VERSION`.

## Backend Service

### Files added

| File | Purpose |
|---|---|
| `backend/app/core/version.py` | `APP_VERSION` constant + semver helpers |
| `backend/app/services/version_checker.py` | Fetches/parses GitHub release, semver-compares, reads/writes cache |
| `backend/app/services/task_jobs/version_check.py` | Celery task wrapper |
| `backend/app/api/version.py` | `GET /api/v1/version` endpoint |
| `backend/app/schemas/version.py` | `VersionData` Pydantic schema |

### `version_checker.py` — responsibilities

- `async def fetch_latest_release() -> dict | None`
  - GET `https://api.github.com/repos/sneg55/pingcrm/releases/latest` with `Accept: application/vnd.github+json` and 10s timeout.
  - Returns the parsed JSON dict on success, `None` on any failure (caller logs).
- `async def refresh_cache() -> None`
  - Calls `fetch_latest_release`, stores JSON-encoded `{tag_name, html_url, body, name, fetched_at}` in Redis key `pingcrm:version:latest` with 12h TTL (43200s).
  - On failure, writes a short-lived `pingcrm:version:failure` marker (5min TTL) so the endpoint can avoid synchronous re-fetches when GitHub is down.
- `async def get_cached_status() -> VersionData`
  - Reads cache, computes `update_available` by comparing `parse_current()` to the cached `tag_name`.
  - Returns a `VersionData` dict (see schema below).

### `VersionData` schema

```python
class VersionData(BaseModel):
    current: str                          # APP_VERSION, e.g. "v1.6.0" or "abc1234" or "dev"
    latest: str | None                    # e.g. "v1.7.0" or None if cache empty / disabled
    release_url: str | None
    release_notes: str | None             # raw markdown from GitHub `body`
    update_available: bool | None         # None when comparison impossible (dev build, cache empty, disabled)
    checked_at: datetime | None
    disabled: bool                        # true when DISABLE_UPDATE_CHECK=1
```

### Endpoint

```python
@router.get("/version", response_model=Envelope[VersionData])
async def get_version(
    current_user: User = Depends(get_current_user),
) -> Envelope[VersionData]:
    ...
```

- Requires auth (matches the rest of `/api/v1/*`).
- If `DISABLE_UPDATE_CHECK` env set → returns `disabled=true`, `update_available=None`, no GitHub call.
- If cache is empty AND no recent failure marker → enqueues `check_for_updates.delay()` and returns `update_available=None` for this request.
- Otherwise returns the cached comparison.

### Celery task

`app/services/task_jobs/version_check.py`:

```python
@celery_app.task(name="version.check_for_updates")
def check_for_updates() -> None:
    if os.getenv("DISABLE_UPDATE_CHECK"):
        return
    asyncio.run(refresh_cache())
```

Re-export from `app/services/tasks.py` (both import line and `__all__`) per the project rule about Celery task discovery.

### Celery beat schedule

`backend/app/core/celery_app.py` — add to `beat_schedule`:

```python
"version-check": {
    "task": "version.check_for_updates",
    "schedule": crontab(minute=0, hour="*/6"),  # every 6 hours on the hour
},
```

### Error handling

Per `.claude/rules/exception-handling.md`:

```python
except httpx.HTTPStatusError as e:
    logger.warning(
        "github release fetch failed",
        extra={"provider": "github", "status": e.response.status_code},
    )
    return None
except (httpx.TimeoutException, httpx.NetworkError) as e:
    logger.warning("github release fetch network error",
                   extra={"provider": "github", "err": str(e)})
    return None
except Exception:
    logger.exception("github release fetch unexpected failure",
                     extra={"provider": "github"})
    return None
```

403 with `X-RateLimit-Remaining: 0` is logged as warning and skipped to next scheduled run; no retry storm.

## Frontend

### Files added

| File | Purpose |
|---|---|
| `frontend/src/hooks/use-version.ts` | React Query hook |
| `frontend/src/components/version-banner.tsx` | Banner UI |

### Hook

```typescript
export function useVersion() {
  return useQuery({
    queryKey: ["version"],
    queryFn: () => api.GET("/api/v1/version"),
    staleTime: 60 * 60 * 1000,        // 1 hour
    refetchOnWindowFocus: false,
    retry: false,
  });
}
```

### Banner component

Mounted in the authenticated app layout (above page content, dismissible). Renders only when:

```typescript
data?.update_available === true && dismissedVersion !== data.latest
```

Layout:

```
┌─────────────────────────────────────────────────────────┐
│ 🎉 PingCRM v1.7.0 is available (you're on v1.6.0)       │
│    [▼ Show release notes]    [View on GitHub]    [×]    │
└─────────────────────────────────────────────────────────┘
```

Expanding `▼` reveals `release_notes` rendered via `react-markdown` + `rehype-sanitize` (add to deps if not already present). Sanitizer is required because the body comes from GitHub release authors — we are the author today, but the dependency on our own discipline shouldn't be a security boundary.

Dismissal:
- Click `×` → write `pingcrm.dismissed_version = data.latest` to `localStorage`.
- On next mount, banner hidden if stored value equals current `latest`.
- When `latest` advances to a newer version, stored value no longer matches → banner re-appears automatically. No expiry needed.

### API regeneration

Per CLAUDE.md workflow:
```bash
cd backend && PYTHONPATH=. python3 -c "import json; from app.main import app; from fastapi.openapi.utils import get_openapi; schema = get_openapi(title=app.title, version=app.version, routes=app.routes); open('openapi.json','w').write(json.dumps(schema, indent=2))"
cd frontend && npm run generate:api
```

## Opt-out

`DISABLE_UPDATE_CHECK=1` env var:
- Celery task short-circuits without hitting GitHub.
- Endpoint returns `{disabled: true, update_available: null}`.
- Banner stays hidden.
- Documented as the supported way to disable for air-gapped deployments or privacy-conscious self-hosters.

## Testing

### Backend

`backend/tests/test_version_checker.py`:
- Semver compare matrix:
  - `current="v1.6.0"`, `latest="v1.7.0"` → `update_available=True`
  - `current="v1.7.0"`, `latest="v1.7.0"` → `False`
  - `current="v1.8.0"`, `latest="v1.7.0"` → `False` (running ahead, e.g. local build)
  - `current="dev"` → `None`
  - `current="abc1234"` (sha) → `None`
  - `current="v1.7.0-rc.1"` → handled by `packaging.version.Version` (pre-releases compare lower than final)
- GitHub fetch (mocked with `respx`):
  - 200 happy path → cache populated
  - 403 rate-limit → warning logged, failure marker written, no exception
  - 5xx → warning logged, no cache write
  - Malformed JSON → exception logged, no cache write
- `DISABLE_UPDATE_CHECK=1` → fetch not called.

`backend/tests/test_api_version.py`:
- Unauthenticated → 401.
- Authenticated, cache populated → envelope shape correct, all fields present.
- Authenticated, cache empty, no failure marker → returns `update_available=None`, asserts `check_for_updates.delay` was called.
- Authenticated, cache empty, failure marker present → returns `update_available=None`, no enqueue.
- `DISABLE_UPDATE_CHECK=1` → returns `disabled=true`, never reads cache.

`backend/tests/test_route_inventory.py` — no update needed. The inventory snapshot only tracks `/api/v1/contacts/*` routes (see `_collect_contact_routes`), so the new `/api/v1/version` endpoint is out of its scope.

`scripts/check_response_models.py` — passes automatically since endpoint declares `response_model=Envelope[VersionData]`.

### Frontend

`frontend/src/components/__tests__/version-banner.test.tsx`:
- Hidden when `update_available=false`.
- Hidden when `update_available=null` (dev build).
- Visible with version pair when `update_available=true`.
- Click `×` writes localStorage key, banner hides on re-render.
- Different `latest` value with same dismissed value → banner reappears.
- Expanded state renders markdown body (assert sanitization strips `<script>` if present).

## Rollout

1. **PR 1 — Versioned images.** Dockerfile `ARG`/`ENV`, CI changes for semver tag fan-out, `app/core/version.py`, FastAPI version string change. No user-visible behavior. Merge, verify CI publishes `:v1.7.0` etc. on next git tag.
2. **PR 2 — Backend service + endpoint.** `version_checker`, Celery task + beat entry, `/api/v1/version` endpoint, schemas, tests, OpenAPI regen, route-inventory update. Endpoint live, no UI yet.
3. **PR 3 — Frontend banner.** Hook, component, layout integration, dismissal localStorage, tests, API types regen.
4. **First real tagged release.** Cut `v1.7.0` (or whatever's next) manually. Self-hosters running `:latest` pull, get the new image stamped `v1.7.0`. Subsequent releases will surface as banners.

Self-hosters whose currently-running image predates PR 1 will show `current="dev"` and see no banner — acceptable; the next pull fixes it.

## Docs

- New page `docs/docs/operations/updates.md`:
  - How the check works (GitHub poll, no telemetry to PingCRM)
  - `DISABLE_UPDATE_CHECK=1` env var
  - How to pin to a specific version (`image: ghcr.io/sneg55/pingcrm/backend:v1.7.0`)
  - Air-gapped deployment guidance
- README "Self-hosting" section: one-line mention with link to the new page.

## Open Questions Resolved During Brainstorm

- **Phone-home vs direct GitHub poll** → direct GitHub poll. Matches Gitea/Vaultwarden norms, no central infra dependency, self-hosters keep autonomy.
- **Single-player visibility** → all authenticated users see the banner; no per-user "is owner" flag required.
- **Pre-release filtering** → `/releases/latest` already excludes pre-releases. No extra logic needed.
- **Dismissal granularity** → per-version, stored in browser localStorage. No backend storage of dismissal state. Per-user-per-browser is acceptable for single-player.
