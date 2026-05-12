# Self-Hoster Version Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show an in-app banner to self-hosters when a newer PingCRM release is available on GitHub, with inline release notes and an opt-out env var.

**Architecture:** CI bakes `APP_VERSION` into images and fans out semver Docker tags on git-tag pushes. A Celery beat task polls `api.github.com/repos/sneg55/pingcrm/releases/latest` every 6h and caches the result in Redis. An authenticated `GET /api/v1/version` endpoint serves the cached comparison. A React Query hook drives a dismissible banner in the root layout.

**Tech Stack:** Python (FastAPI, Celery, httpx, packaging, redis-py), TypeScript (Next.js, React Query, react-markdown), Docker, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-05-12-version-notification-design.md`

---

### Task 1: Add APP_VERSION build arg to backend Dockerfile

**Files:**
- Modify: `backend/Dockerfile`

- [ ] **Step 1: Add the ARG/ENV near the top of the Dockerfile**

Open `backend/Dockerfile` and add right after the `FROM python:3.12-slim` line:

```dockerfile
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
```

So the top of the file becomes:

```dockerfile
FROM python:3.12-slim

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

RUN apt-get update && \
    ...
```

- [ ] **Step 2: Verify the Dockerfile still parses**

Run: `docker build --build-arg APP_VERSION=v1.6.0-test -t pingcrm-backend-test backend/ 2>&1 | tail -5`
Expected: build succeeds (or fails on something unrelated like network — the ARG line should not be the failure).

If you don't want to do a full build, at minimum:
```bash
docker build --build-arg APP_VERSION=v1.6.0-test --target deps -t pingcrm-backend-test backend/ 2>&1 | head -20 || true
```
(There's no `deps` stage in this Dockerfile, so this errors fast — that's fine. We just want syntax validation, which buildx does upfront.)

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "build(backend): accept APP_VERSION build arg"
```

---

### Task 2: Add APP_VERSION build arg to frontend Dockerfile

**Files:**
- Modify: `frontend/Dockerfile`

- [ ] **Step 1: Add ARG to build stage and ENV to runner stage**

The frontend Dockerfile has 3 stages (`deps`, `build`, `runner`). We need `APP_VERSION` available at runtime (in `runner`) AND at build time (in `build`, so Next.js can inline it if needed). Add `ARG APP_VERSION=dev` and `ENV APP_VERSION=${APP_VERSION}` to both the `build` and `runner` stages.

Edit `frontend/Dockerfile`:

```dockerfile
# Stage 2: Build the application
FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

ARG NEXT_PUBLIC_API_URL=http://backend:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# Stage 3: Production runner
FROM node:20-alpine AS runner
WORKDIR /app

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
```

(The frontend doesn't directly need `APP_VERSION` since the backend will serve `current` via the API. But baking it in both stages future-proofs us and lets a future "About" page read it.)

- [ ] **Step 2: Commit**

```bash
git add frontend/Dockerfile
git commit -m "build(frontend): accept APP_VERSION build arg"
```

---

### Task 3: Add backend version helper module

**Files:**
- Create: `backend/app/core/version.py`
- Test: `backend/tests/test_app_version.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_app_version.py`:

```python
"""Tests for app.core.version helpers."""
import importlib
import os

import pytest
from packaging.version import Version


def reload_version_module(monkeypatch, value: str | None):
    """Reload app.core.version with APP_VERSION set/unset for this test."""
    if value is None:
        monkeypatch.delenv("APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("APP_VERSION", value)
    import app.core.version as v
    importlib.reload(v)
    return v


def test_app_version_defaults_to_dev(monkeypatch):
    v = reload_version_module(monkeypatch, None)
    assert v.APP_VERSION == "dev"
    assert v.is_semver_build() is False
    assert v.parse_current() is None


def test_app_version_reads_env(monkeypatch):
    v = reload_version_module(monkeypatch, "v1.6.0")
    assert v.APP_VERSION == "v1.6.0"
    assert v.is_semver_build() is True
    parsed = v.parse_current()
    assert parsed == Version("1.6.0")


def test_app_version_strips_v_prefix(monkeypatch):
    v = reload_version_module(monkeypatch, "1.6.0")
    assert v.is_semver_build() is True
    assert v.parse_current() == Version("1.6.0")


def test_app_version_rejects_sha(monkeypatch):
    v = reload_version_module(monkeypatch, "abc1234")
    assert v.is_semver_build() is False
    assert v.parse_current() is None


def test_app_version_handles_prerelease(monkeypatch):
    v = reload_version_module(monkeypatch, "v1.7.0-rc.1")
    assert v.is_semver_build() is True
    assert v.parse_current() == Version("1.7.0rc1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. pytest tests/test_app_version.py -v`
Expected: ImportError or ModuleNotFoundError on `app.core.version`.

- [ ] **Step 3: Create the module**

Create `backend/app/core/version.py`:

```python
"""Application version detection.

APP_VERSION is set by Docker build at image creation time. When running from
source or without CI stamping, it defaults to "dev" and disables the
version-check banner.
"""
import os
import re

from packaging.version import InvalidVersion, Version

APP_VERSION: str = os.getenv("APP_VERSION", "dev")

_SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+([-.+].*)?$")


def is_semver_build() -> bool:
    """True iff APP_VERSION looks like a semantic version."""
    return bool(_SEMVER_RE.match(APP_VERSION))


def parse_current() -> Version | None:
    """Return the parsed current version, or None for dev/SHA builds."""
    if not is_semver_build():
        return None
    try:
        return Version(APP_VERSION.lstrip("v"))
    except InvalidVersion:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_app_version.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/version.py backend/tests/test_app_version.py
git commit -m "feat(backend): add APP_VERSION helper module"
```

---

### Task 4: Use APP_VERSION in FastAPI app

**Files:**
- Modify: `backend/app/main.py:68-73`

- [ ] **Step 1: Replace hardcoded version string**

In `backend/app/main.py`, find the FastAPI instantiation (around line 68) and import + use `APP_VERSION`.

Add the import at the top of the imports section (after the other `from app.core` imports):

```python
from app.core.version import APP_VERSION
```

Change the FastAPI instantiation from:

```python
app = FastAPI(
    title="PingCRM API",
    description="AI-powered networking assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)
```

to:

```python
app = FastAPI(
    title="PingCRM API",
    description="AI-powered networking assistant backend",
    version=APP_VERSION,
    lifespan=lifespan,
)
```

- [ ] **Step 2: Verify app still imports**

Run: `cd backend && PYTHONPATH=. python -c "from app.main import fastapi_app; print('version:', fastapi_app.version)"`
Expected: prints `version: dev` (since APP_VERSION is unset locally).

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(backend): use APP_VERSION in FastAPI app metadata"
```

---

### Task 5: Update CI to fan out semver tags and pass APP_VERSION

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Add tag trigger and metadata-action steps**

Edit `.github/workflows/deploy.yml`. Change the top of the file from:

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:
```

to:

```yaml
on:
  push:
    branches: [main]
    tags: ['v*']
  workflow_dispatch:
```

Then in the `build` job, before the "Build and push backend" step, add:

```yaml
      - name: Extract backend image metadata
        id: meta-backend
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.BACKEND_IMAGE }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,enable={{is_default_branch}},format=long
            type=sha,enable={{is_default_branch}}
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=semver,pattern={{major}}
            type=raw,value=latest,enable=${{ github.ref_type == 'tag' }}

      - name: Extract frontend image metadata
        id: meta-frontend
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.FRONTEND_IMAGE }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,enable={{is_default_branch}},format=long
            type=sha,enable={{is_default_branch}}
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=semver,pattern={{major}}
            type=raw,value=latest,enable=${{ github.ref_type == 'tag' }}
```

- [ ] **Step 2: Compute the APP_VERSION build arg**

Add this step right after the metadata-action steps:

```yaml
      - name: Compute APP_VERSION
        id: app-version
        run: |
          if [ "${{ github.ref_type }}" = "tag" ]; then
            echo "value=${{ github.ref_name }}" >> "$GITHUB_OUTPUT"
          else
            echo "value=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
          fi
```

- [ ] **Step 3: Replace the backend build step to consume the metadata + build arg**

Change the "Build and push backend" step from:

```yaml
      - name: Build and push backend
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: ${{ env.BACKEND_IMAGE }}:latest,${{ env.BACKEND_IMAGE }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

to:

```yaml
      - name: Build and push backend
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: ${{ steps.meta-backend.outputs.tags }}
          labels: ${{ steps.meta-backend.outputs.labels }}
          build-args: |
            APP_VERSION=${{ steps.app-version.outputs.value }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 4: Replace the frontend build step**

Change the "Build and push frontend" step from:

```yaml
      - name: Build and push frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          push: true
          tags: ${{ env.FRONTEND_IMAGE }}:latest,${{ env.FRONTEND_IMAGE }}:${{ github.sha }}
          build-args: |
            NEXT_PUBLIC_API_URL=https://pingcrm.sawinyh.com/api
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

to:

```yaml
      - name: Build and push frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          push: true
          tags: ${{ steps.meta-frontend.outputs.tags }}
          labels: ${{ steps.meta-frontend.outputs.labels }}
          build-args: |
            NEXT_PUBLIC_API_URL=https://pingcrm.sawinyh.com/api
            APP_VERSION=${{ steps.app-version.outputs.value }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 5: Guard the deploy job to main-only**

Tag pushes should produce versioned images but NOT trigger a production deploy. Add an `if:` to the deploy job. Change:

```yaml
  deploy:
    needs: build
    runs-on: ubuntu-latest
```

to:

```yaml
  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
```

- [ ] **Step 6: Validate the workflow file syntax**

Run: `cd /Users/sneg55-pro13/Documents/github/pingcrm && python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))" && echo OK`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: fan out semver image tags on git tag and bake APP_VERSION"
```

---

### Task 6: Add VersionData schema

**Files:**
- Create: `backend/app/schemas/version.py`

- [ ] **Step 1: Create the schema file**

Create `backend/app/schemas/version.py`:

```python
"""Schemas for the version-check endpoint."""
from datetime import datetime

from pydantic import BaseModel


class VersionData(BaseModel):
    """Response payload for GET /api/v1/version."""

    current: str
    latest: str | None = None
    release_url: str | None = None
    release_notes: str | None = None
    update_available: bool | None = None
    checked_at: datetime | None = None
    disabled: bool = False
```

- [ ] **Step 2: Verify import**

Run: `cd backend && PYTHONPATH=. python -c "from app.schemas.version import VersionData; print(VersionData(current='dev').model_dump())"`
Expected: prints a dict with `current='dev'` and other fields as `None`/`False`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/version.py
git commit -m "feat(backend): add VersionData schema"
```

---

### Task 7: Implement GitHub release fetch with tests

**Files:**
- Create: `backend/app/services/version_checker.py`
- Test: `backend/tests/test_version_checker.py`

- [ ] **Step 1: Write the failing tests for fetch_latest_release**

Create `backend/tests/test_version_checker.py`:

```python
"""Tests for app.services.version_checker."""
import httpx
import pytest
import respx

from app.services.version_checker import GITHUB_RELEASES_URL, fetch_latest_release


@pytest.mark.asyncio
async def test_fetch_returns_payload_on_200():
    with respx.mock(assert_all_called=True) as mock:
        mock.get(GITHUB_RELEASES_URL).respond(
            200,
            json={
                "tag_name": "v1.7.0",
                "name": "v1.7.0 — birthday suggestions",
                "html_url": "https://github.com/sneg55/pingcrm/releases/tag/v1.7.0",
                "body": "## What's new\n- birthday suggestions",
            },
        )
        result = await fetch_latest_release()

    assert result is not None
    assert result["tag_name"] == "v1.7.0"
    assert result["html_url"].endswith("v1.7.0")


@pytest.mark.asyncio
async def test_fetch_returns_none_on_403_rate_limit(caplog):
    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(
            403,
            headers={"X-RateLimit-Remaining": "0"},
            json={"message": "API rate limit exceeded"},
        )
        result = await fetch_latest_release()

    assert result is None
    assert any("github" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_fetch_returns_none_on_5xx(caplog):
    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(503)
        result = await fetch_latest_release()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_network_error():
    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).mock(side_effect=httpx.ConnectError("boom"))
        result = await fetch_latest_release()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_malformed_json(caplog):
    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(200, content=b"not json")
        result = await fetch_latest_release()
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. pytest tests/test_version_checker.py -v`
Expected: ImportError or ModuleNotFoundError on `app.services.version_checker`.

- [ ] **Step 3: Implement fetch_latest_release**

Create `backend/app/services/version_checker.py`:

```python
"""Self-hoster version-check: poll GitHub releases, compare, cache."""
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_RELEASES_URL = "https://api.github.com/repos/sneg55/pingcrm/releases/latest"
FETCH_TIMEOUT_S = 10.0
USER_AGENT = "pingcrm-version-check"


async def fetch_latest_release() -> dict[str, Any] | None:
    """Fetch the latest GitHub release JSON.

    Returns None on any failure (timeout, network error, non-2xx, malformed
    JSON). Failures are logged but never re-raised.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S) as client:
            response = await client.get(GITHUB_RELEASES_URL, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        remaining = e.response.headers.get("X-RateLimit-Remaining")
        logger.warning(
            "github release fetch failed",
            extra={
                "provider": "github",
                "status": e.response.status_code,
                "rate_limit_remaining": remaining,
            },
        )
        return None
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.warning(
            "github release fetch network error",
            extra={"provider": "github", "err": str(e)},
        )
        return None
    except ValueError:  # JSONDecodeError subclass
        logger.exception(
            "github release fetch returned malformed JSON",
            extra={"provider": "github"},
        )
        return None
    except Exception:
        logger.exception(
            "github release fetch unexpected failure",
            extra={"provider": "github"},
        )
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_version_checker.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/version_checker.py backend/tests/test_version_checker.py
git commit -m "feat(backend): add GitHub releases fetch for version check"
```

---

### Task 8: Add semver comparison

**Files:**
- Modify: `backend/app/services/version_checker.py`
- Modify: `backend/tests/test_version_checker.py`

- [ ] **Step 1: Write failing tests for compare_versions**

Append to `backend/tests/test_version_checker.py`:

```python
from app.services.version_checker import compare_versions


@pytest.mark.parametrize(
    "current,latest_tag,expected",
    [
        ("v1.6.0", "v1.7.0", True),
        ("1.6.0", "1.7.0", True),
        ("v1.7.0", "v1.7.0", False),
        ("v1.8.0", "v1.7.0", False),
        ("v1.7.0-rc.1", "v1.7.0", True),
        ("dev", "v1.7.0", None),
        ("abc1234", "v1.7.0", None),
        ("v1.6.0", "garbage", None),
        ("v1.6.0", None, None),
    ],
)
def test_compare_versions(current, latest_tag, expected):
    assert compare_versions(current, latest_tag) is expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. pytest tests/test_version_checker.py::test_compare_versions -v`
Expected: ImportError on `compare_versions`.

- [ ] **Step 3: Implement compare_versions**

Edit `backend/app/services/version_checker.py`. First, update the import block at the top of the file to add `re`, `InvalidVersion`, and `Version`:

```python
import logging
import re
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version
```

Then append the new code at the bottom of the file:

```python
_SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+([-.+].*)?$")


def _parse(tag: str | None) -> Version | None:
    if not tag or not _SEMVER_RE.match(tag):
        return None
    try:
        return Version(tag.lstrip("v"))
    except InvalidVersion:
        return None


def compare_versions(current: str, latest_tag: str | None) -> bool | None:
    """Return True iff `latest_tag` is strictly newer than `current`.

    Returns None when comparison is impossible (current is dev/SHA, latest
    is missing or malformed).
    """
    current_v = _parse(current)
    latest_v = _parse(latest_tag)
    if current_v is None or latest_v is None:
        return None
    return latest_v > current_v
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_version_checker.py -v`
Expected: all tests pass (5 fetch tests + 9 parametrized compare tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/version_checker.py backend/tests/test_version_checker.py
git commit -m "feat(backend): semver comparison for version checker"
```

---

### Task 9: Cache read/write and refresh

**Files:**
- Modify: `backend/app/services/version_checker.py`
- Modify: `backend/tests/test_version_checker.py`

- [ ] **Step 1: Write failing tests for cache layer**

Append to `backend/tests/test_version_checker.py`:

```python
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.services.version_checker import (
    CACHE_KEY,
    CACHE_TTL_S,
    FAILURE_KEY,
    FAILURE_TTL_S,
    get_cached_status,
    refresh_cache,
)


@pytest.mark.asyncio
async def test_refresh_cache_stores_release_on_success(monkeypatch):
    fake_redis = AsyncMock()
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )

    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(
            200,
            json={
                "tag_name": "v1.7.0",
                "name": "v1.7.0",
                "html_url": "https://example.com",
                "body": "notes",
            },
        )
        await refresh_cache()

    fake_redis.set.assert_awaited()
    call_args = fake_redis.set.await_args
    key = call_args.args[0]
    payload = json.loads(call_args.args[1])
    assert key == CACHE_KEY
    assert payload["tag_name"] == "v1.7.0"
    assert payload["html_url"] == "https://example.com"
    assert "fetched_at" in payload
    assert call_args.kwargs["ex"] == CACHE_TTL_S


@pytest.mark.asyncio
async def test_refresh_cache_writes_failure_marker_on_error(monkeypatch):
    fake_redis = AsyncMock()
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )

    with respx.mock() as mock:
        mock.get(GITHUB_RELEASES_URL).respond(503)
        await refresh_cache()

    # Failure marker written, main cache NOT written
    set_calls = [c.args[0] for c in fake_redis.set.await_args_list]
    assert FAILURE_KEY in set_calls
    assert CACHE_KEY not in set_calls


@pytest.mark.asyncio
async def test_get_cached_status_returns_data_when_cached(monkeypatch):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=json.dumps({
        "tag_name": "v1.7.0",
        "html_url": "https://example.com/v1.7.0",
        "body": "notes",
        "name": "v1.7.0",
        "fetched_at": datetime(2026, 5, 12, tzinfo=timezone.utc).isoformat(),
    }))
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    status = await get_cached_status()

    assert status.current == "v1.6.0"
    assert status.latest == "v1.7.0"
    assert status.update_available is True
    assert status.release_url == "https://example.com/v1.7.0"
    assert status.disabled is False


@pytest.mark.asyncio
async def test_get_cached_status_empty_cache(monkeypatch):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    status = await get_cached_status()

    assert status.current == "v1.6.0"
    assert status.latest is None
    assert status.update_available is None
    assert status.disabled is False


@pytest.mark.asyncio
async def test_get_cached_status_disabled_env(monkeypatch):
    monkeypatch.setenv("DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )
    status = await get_cached_status()
    assert status.disabled is True
    assert status.update_available is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. pytest tests/test_version_checker.py -v`
Expected: ImportError on the new symbols.

- [ ] **Step 3: Implement cache layer**

Edit `backend/app/services/version_checker.py`. Update the import block at the top of the file to add the new imports:

```python
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version

from app.core.redis import get_redis
from app.core.version import APP_VERSION
from app.schemas.version import VersionData
```

Then append the new code at the bottom of the file:

```python
CACHE_KEY = "pingcrm:version:latest"
FAILURE_KEY = "pingcrm:version:failure"
CACHE_TTL_S = 12 * 60 * 60       # 12 hours
FAILURE_TTL_S = 5 * 60           # 5 minutes
DISABLE_ENV = "DISABLE_UPDATE_CHECK"


def is_disabled() -> bool:
    return bool(os.getenv(DISABLE_ENV))


async def refresh_cache() -> None:
    """Fetch latest release and persist to Redis, or write failure marker."""
    if is_disabled():
        return

    payload = await fetch_latest_release()
    redis = get_redis()

    if payload is None:
        await redis.set(FAILURE_KEY, "1", ex=FAILURE_TTL_S)
        return

    record = {
        "tag_name": payload.get("tag_name"),
        "name": payload.get("name"),
        "html_url": payload.get("html_url"),
        "body": payload.get("body"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.set(CACHE_KEY, json.dumps(record), ex=CACHE_TTL_S)


async def get_cached_status() -> VersionData:
    """Read cached release info and compute the user-facing status."""
    if is_disabled():
        return VersionData(current=APP_VERSION, disabled=True)

    redis = get_redis()
    raw = await redis.get(CACHE_KEY)
    if raw is None:
        return VersionData(current=APP_VERSION)

    if isinstance(raw, bytes):
        raw = raw.decode()
    record = json.loads(raw)
    latest_tag = record.get("tag_name")

    fetched_at = record.get("fetched_at")
    checked_at = datetime.fromisoformat(fetched_at) if fetched_at else None

    return VersionData(
        current=APP_VERSION,
        latest=latest_tag,
        release_url=record.get("html_url"),
        release_notes=record.get("body"),
        update_available=compare_versions(APP_VERSION, latest_tag),
        checked_at=checked_at,
    )


async def has_recent_failure() -> bool:
    """True if a recent GitHub fetch failure marker exists."""
    redis = get_redis()
    return bool(await redis.get(FAILURE_KEY))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_version_checker.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/version_checker.py backend/tests/test_version_checker.py
git commit -m "feat(backend): Redis caching for version checker"
```

---

### Task 10: Celery task and beat schedule

**Files:**
- Create: `backend/app/services/task_jobs/version_check.py`
- Modify: `backend/app/services/tasks.py`
- Modify: `backend/app/core/celery_app.py`

- [ ] **Step 1: Create the task module**

Create `backend/app/services/task_jobs/version_check.py`:

```python
"""Celery task: poll GitHub for latest release and cache result."""
import asyncio
import logging

from app.core.celery_app import celery_app
from app.services.version_checker import is_disabled, refresh_cache

logger = logging.getLogger(__name__)


@celery_app.task(name="app.services.tasks.check_for_updates")
def check_for_updates() -> None:
    """Periodic task: refresh the version-check cache from GitHub."""
    if is_disabled():
        return
    try:
        asyncio.run(refresh_cache())
    except Exception:
        logger.exception(
            "version check task failed",
            extra={"provider": "github"},
        )
```

- [ ] **Step 2: Re-export from tasks.py**

Edit `backend/app/services/tasks.py`. Find the section near the other `from app.services.task_jobs.<module> import (...)` blocks and add:

```python
from app.services.task_jobs.version_check import (
    check_for_updates,
)
```

If `tasks.py` has an `__all__` list, append `"check_for_updates"` to it. (Inspect the file to confirm.)

- [ ] **Step 3: Add beat schedule entry**

Edit `backend/app/core/celery_app.py`. Inside the `beat_schedule={...}` block, add:

```python
        # Check GitHub for new PingCRM releases every 6 hours
        "version-check-every-6h": {
            "task": "app.services.tasks.check_for_updates",
            "schedule": crontab(minute=15, hour="*/6"),
        },
```

(`minute=15` deliberately offsets from other 6h tasks like Gmail sync which run on `minute=0`, to avoid bursts.)

- [ ] **Step 4: Verify Celery picks up the task**

Run: `cd backend && PYTHONPATH=. python -c "from app.core.celery_app import celery_app; print([t for t in celery_app.tasks if 'check_for_updates' in t])"`
Expected: prints `['app.services.tasks.check_for_updates']`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/task_jobs/version_check.py backend/app/services/tasks.py backend/app/core/celery_app.py
git commit -m "feat(backend): Celery task and beat schedule for version check"
```

---

### Task 11: GET /api/v1/version endpoint

**Files:**
- Create: `backend/app/api/version.py`
- Create: `backend/tests/test_api_version.py`
- Modify: `backend/app/main.py` (register router)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api_version.py`:

```python
"""Tests for GET /api/v1/version."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_version_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/version")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_version_returns_cached_status(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=json.dumps({
        "tag_name": "v1.7.0",
        "html_url": "https://github.com/sneg55/pingcrm/releases/tag/v1.7.0",
        "body": "notes",
        "name": "v1.7.0",
        "fetched_at": datetime(2026, 5, 12, tzinfo=timezone.utc).isoformat(),
    }))
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    resp = await client.get("/api/v1/version", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    data = body["data"]
    assert data["current"] == "v1.6.0"
    assert data["latest"] == "v1.7.0"
    assert data["update_available"] is True
    assert data["release_url"].endswith("v1.7.0")
    assert data["disabled"] is False


@pytest.mark.asyncio
async def test_version_empty_cache_enqueues_refresh(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)  # cache miss + no failure marker
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    fake_task = MagicMock()
    monkeypatch.setattr("app.api.version.check_for_updates", fake_task)

    resp = await client.get("/api/v1/version", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["update_available"] is None
    fake_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_version_empty_cache_with_failure_marker_does_not_enqueue(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    fake_redis = AsyncMock()
    # First get() returns None (cache miss), second returns truthy (failure marker)
    fake_redis.get = AsyncMock(side_effect=[None, b"1"])
    monkeypatch.setattr(
        "app.services.version_checker.get_redis", lambda: fake_redis
    )
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )

    fake_task = MagicMock()
    monkeypatch.setattr("app.api.version.check_for_updates", fake_task)

    resp = await client.get("/api/v1/version", headers=auth_headers)

    assert resp.status_code == 200
    fake_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_version_disabled(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setenv("DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setattr(
        "app.services.version_checker.APP_VERSION", "v1.6.0"
    )
    resp = await client.get("/api/v1/version", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["disabled"] is True
    assert data["update_available"] is None
```

The `client` and `auth_headers` fixtures live in `backend/tests/conftest.py` and are used the same way across the existing test suite (see `test_contacts_api.py` for reference).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_version.py -v`
Expected: 404 (route not registered) or fixture errors.

- [ ] **Step 3: Implement the endpoint**

Create `backend/app/api/version.py`:

```python
"""Version-check endpoint for self-hosters."""
from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.responses import Envelope
from app.schemas.version import VersionData
from app.services.tasks import check_for_updates
from app.services.version_checker import (
    get_cached_status,
    has_recent_failure,
    is_disabled,
)

router = APIRouter(prefix="/api/v1", tags=["version"])


@router.get("/version", response_model=Envelope[VersionData])
async def get_version(
    current_user: User = Depends(get_current_user),
) -> Envelope[VersionData]:
    """Return current app version and latest available release, if known."""
    status = await get_cached_status()
    if (
        not is_disabled()
        and status.latest is None
        and not await has_recent_failure()
    ):
        check_for_updates.delay()
    return {"data": status, "error": None}
```

- [ ] **Step 4: Register the router in main.py**

Edit `backend/app/main.py`. Near the other `from app.api.<x> import router as <x>_router` imports, add:

```python
from app.api.version import router as version_router
```

Near the other `app.include_router(...)` calls, add:

```python
app.include_router(version_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_version.py -v`
Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/version.py backend/tests/test_api_version.py backend/app/main.py
git commit -m "feat(backend): GET /api/v1/version endpoint"
```

---

### Task 12: Regenerate OpenAPI schema and frontend API types

**Files:**
- Modify: `backend/openapi.json`
- Modify: `frontend/src/lib/api-types.d.ts`

The `test_route_inventory.py` snapshot only tracks `/api/v1/contacts/*` routes (per CLAUDE.md and the test's `_collect_contact_routes` helper), so the new `/api/v1/version` endpoint does NOT require an inventory update.

- [ ] **Step 1: Regenerate OpenAPI**

Run (from project root):
```bash
cd backend && PYTHONPATH=. python3 -c "
import json
from app.main import fastapi_app
from fastapi.openapi.utils import get_openapi
schema = get_openapi(title=fastapi_app.title, version=fastapi_app.version, routes=fastapi_app.routes)
with open('openapi.json', 'w') as f:
    json.dump(schema, f, indent=2)
print('openapi.json regenerated')
"
```
Expected: prints `openapi.json regenerated`.

- [ ] **Step 2: Regenerate frontend API types**

Run: `cd frontend && npm run generate:api`
Expected: completes without error; `src/lib/api-types.d.ts` is modified.

- [ ] **Step 3: Verify the new route appears in types**

Run: `grep -n '"/api/v1/version"' frontend/src/lib/api-types.d.ts | head -2`
Expected: at least one match.

- [ ] **Step 4: Commit**

```bash
git add backend/openapi.json frontend/src/lib/api-types.d.ts
git commit -m "chore: regenerate OpenAPI + API types for /api/v1/version"
```

---

### Task 13: Add react-markdown + sanitizer dependencies

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Install runtime deps**

Run: `cd frontend && npm install react-markdown rehype-sanitize`
Expected: deps added to `package.json`, lockfile updated. No errors.

- [ ] **Step 2: Verify versions**

Run: `cd frontend && grep -E '"react-markdown|"rehype-sanitize' package.json`
Expected: both appear under dependencies.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add react-markdown and rehype-sanitize"
```

---

### Task 14: useVersion hook

**Files:**
- Create: `frontend/src/hooks/use-version.ts`

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/use-version.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";

import { client } from "@/lib/api-client";

export type VersionStatus = {
  current: string;
  latest: string | null;
  release_url: string | null;
  release_notes: string | null;
  update_available: boolean | null;
  checked_at: string | null;
  disabled: boolean;
};

export function useVersion() {
  return useQuery<VersionStatus | null>({
    queryKey: ["version"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/version");
      if (!data?.data) return null;
      return data.data as VersionStatus;
    },
    staleTime: 60 * 60 * 1000, // 1 hour
    refetchOnWindowFocus: false,
    retry: false,
  });
}
```

The `client` import and `client.GET("/api/v1/...")` call shape match the existing hooks (see `frontend/src/hooks/use-suggestions.ts`). The double `data.data` is the envelope shape: outer `data` is the response body, inner `data` is the `Envelope` payload.

- [ ] **Step 2: Verify the hook typechecks**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -E "use-version|error TS" | head -20`
Expected: no errors mentioning `use-version.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/use-version.ts
git commit -m "feat(frontend): useVersion React Query hook"
```

---

### Task 15: VersionBanner component with tests

**Files:**
- Create: `frontend/src/components/version-banner.tsx`
- Create: `frontend/src/components/version-banner.test.tsx`

- [ ] **Step 1: Inspect a peer component for test style**

Run: `cat frontend/src/components/empty-state.test.tsx | head -40`
Note: the test runner (`vitest` or `jest`), how `render` is imported, how authentication is mocked.

- [ ] **Step 2: Write failing tests for the banner**

Create `frontend/src/components/version-banner.test.tsx`:

```tsx
import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { VersionBanner } from "./version-banner";

vi.mock("@/hooks/use-version", () => ({
  useVersion: vi.fn(),
}));
import { useVersion } from "@/hooks/use-version";

const baseStatus = {
  current: "v1.6.0",
  latest: "v1.7.0",
  release_url: "https://github.com/sneg55/pingcrm/releases/tag/v1.7.0",
  release_notes: "## What's new\n- birthday suggestions",
  update_available: true,
  checked_at: "2026-05-12T14:00:00Z",
  disabled: false,
};

describe("VersionBanner", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("renders nothing when update_available is false", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...baseStatus, update_available: false },
    });
    const { container } = render(<VersionBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when update_available is null", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...baseStatus, update_available: null },
    });
    const { container } = render(<VersionBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the banner with version pair when update available", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({ data: baseStatus });
    render(<VersionBanner />);
    expect(screen.getByText(/v1\.7\.0 is available/)).toBeInTheDocument();
    expect(screen.getByText(/v1\.6\.0/)).toBeInTheDocument();
  });

  it("hides the banner when dismissed value matches latest", () => {
    localStorage.setItem("pingcrm.dismissed_version", "v1.7.0");
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({ data: baseStatus });
    const { container } = render(<VersionBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("reappears when latest advances past dismissed value", () => {
    localStorage.setItem("pingcrm.dismissed_version", "v1.7.0");
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...baseStatus, latest: "v1.8.0" },
    });
    render(<VersionBanner />);
    expect(screen.getByText(/v1\.8\.0 is available/)).toBeInTheDocument();
  });

  it("stores dismissed version in localStorage when dismiss clicked", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({ data: baseStatus });
    render(<VersionBanner />);
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(localStorage.getItem("pingcrm.dismissed_version")).toBe("v1.7.0");
  });

  it("expands release notes when toggle clicked", () => {
    (useVersion as ReturnType<typeof vi.fn>).mockReturnValue({ data: baseStatus });
    render(<VersionBanner />);
    expect(screen.queryByText(/birthday suggestions/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /release notes/i }));
    expect(screen.getByText(/birthday suggestions/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/version-banner.test.tsx 2>&1 | tail -20`
Expected: file `./version-banner` not found.

- [ ] **Step 4: Implement the banner**

Create `frontend/src/components/version-banner.tsx`:

```tsx
"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

import { useVersion } from "@/hooks/use-version";

const DISMISS_KEY = "pingcrm.dismissed_version";

export function VersionBanner() {
  const { data } = useVersion();
  const [expanded, setExpanded] = useState(false);
  const [dismissedTick, setDismissedTick] = useState(0);

  if (!data || data.update_available !== true || !data.latest) {
    return null;
  }

  // Read dismissed value at render time (dismissedTick busts the read after click)
  const dismissed =
    typeof window !== "undefined"
      ? localStorage.getItem(DISMISS_KEY)
      : null;
  void dismissedTick;
  if (dismissed === data.latest) {
    return null;
  }

  const handleDismiss = () => {
    localStorage.setItem(DISMISS_KEY, data.latest!);
    setDismissedTick((n) => n + 1);
  };

  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 dark:border-amber-900/40 dark:bg-amber-950/30">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">
          🎉 PingCRM {data.latest} is available
        </span>
        <span className="text-stone-600 dark:text-stone-400">
          (you&apos;re on {data.current})
        </span>
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="text-stone-700 underline-offset-2 hover:underline dark:text-stone-300"
          aria-label={expanded ? "Hide release notes" : "Show release notes"}
        >
          {expanded ? "▲ Hide release notes" : "▼ Show release notes"}
        </button>
        {data.release_url && (
          <a
            href={data.release_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-stone-700 underline-offset-2 hover:underline dark:text-stone-300"
          >
            View on GitHub →
          </a>
        )}
        <button
          type="button"
          onClick={handleDismiss}
          className="ml-2 text-stone-500 hover:text-stone-800 dark:text-stone-400 dark:hover:text-stone-100"
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
      {expanded && data.release_notes && (
        <div className="mx-auto mt-2 max-w-6xl border-t border-amber-200/60 pt-2 text-sm dark:border-amber-900/40 prose prose-sm dark:prose-invert">
          <Markdown rehypePlugins={[rehypeSanitize]}>
            {data.release_notes}
          </Markdown>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/version-banner.test.tsx 2>&1 | tail -20`
Expected: all 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/version-banner.tsx frontend/src/components/version-banner.test.tsx
git commit -m "feat(frontend): VersionBanner component with dismissal"
```

---

### Task 16: Mount banner in root layout

**Files:**
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Add the import and mount the component**

In `frontend/src/app/layout.tsx`, add the import alongside the other component imports:

```typescript
import { VersionBanner } from "@/components/version-banner";
```

Mount the banner inside `<AuthProvider>` so it only fetches after auth context is initialized, and place it right above `<Nav />`:

```tsx
<AuthProvider>
  <ErrorReporter />
  <VersionBanner />
  <Nav />
  {children}
</AuthProvider>
```

(Banner self-suppresses when not authenticated because `useVersion` will get a 401 and React Query returns `data === null` from our `queryFn`.)

- [ ] **Step 2: Sanity-check typechecking**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -E "error TS" | head -20`
Expected: no new errors.

- [ ] **Step 3: Verify in dev server**

Run (in a separate terminal): `cd frontend && npm run dev`
Then load `http://localhost:3000`. Log in. Expected: no banner visible yet (because backend's `APP_VERSION` defaults to `dev`, so `update_available` is `null`). This confirms the suppression path works. Stop the dev server with Ctrl-C.

To actually see the banner in development, you can temporarily set `APP_VERSION=v1.5.0` when starting the backend and seed Redis with a `v1.7.0` payload — but that's manual QA, not part of the commit.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/layout.tsx
git commit -m "feat(frontend): mount VersionBanner in root layout"
```

---

### Task 17: Documentation

**Files:**
- Create: `docs/docs/operations/updates.md`
- Modify: `README.md`

- [ ] **Step 1: Inspect docs structure**

Run: `ls docs/docs/ && ls docs/docs/operations/ 2>/dev/null || echo "no operations dir yet"`
Expected: prints the docs/docs subdirectories. If `operations/` doesn't exist, create it.

- [ ] **Step 2: Create the docs page**

Create `docs/docs/operations/updates.md`:

```markdown
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
```

- [ ] **Step 3: Link from README**

Open `README.md` and find the self-hosting section (search for "Self-host" or "Deploy"). Add a line:

```markdown
### Staying up to date

PingCRM checks GitHub for new releases and shows an in-app banner when one
is available. See [Update Notifications](docs/docs/operations/updates.md)
for details and opt-out.
```

(Place it wherever it fits naturally — likely right after the deployment instructions.)

- [ ] **Step 4: Commit**

```bash
git add docs/docs/operations/updates.md README.md
git commit -m "docs: self-hoster update notification guide"
```

---

## After all tasks complete

Run the full local test suite once before opening the PR:

```bash
cd backend && PYTHONPATH=. pytest -x
cd frontend && npm test
```

CI guards to confirm:

```bash
cd backend && PYTHONPATH=. python3 scripts/check_response_models.py
cd frontend && bash scripts/check-as-any.sh
```

Then push.

The first time a `v*` tag is pushed after this lands, CI will publish the new semver-tagged images. Existing self-hosters on `:latest` will pull the new image on their next `docker compose pull`, which stamps their instance with the proper `APP_VERSION`. From then on, subsequent releases surface as banners automatically.
