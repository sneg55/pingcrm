"""API responses must never be cacheable.

/api responses are per-user and bearer-scoped, and the app previously sent no
cache headers at all, leaving caching to client heuristics. That is a privacy
problem (a shared proxy or the on-disk browser cache can retain one user's
contacts) and a correctness one (these endpoints exist to report current state).

These tests pin the header at the middleware layer so a new endpoint cannot
forget it.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_authenticated_api_response_is_no_store(client, auth_headers):
    resp = await client.get("/api/v1/contacts/stats", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_unauthenticated_api_response_is_also_no_store(client):
    # 401s travel through the exception handler rather than the normal response
    # path, so they need covering separately.
    resp = await client.get("/api/v1/contacts/stats")

    assert resp.status_code == 401
    assert resp.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_health_endpoint_is_no_store(client):
    # /api/health is what the container healthcheck polls; a cached "healthy"
    # would be actively misleading.
    resp = await client.get("/api/health")

    assert resp.headers["cache-control"] == "no-store"
