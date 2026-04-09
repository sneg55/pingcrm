"""WhatsApp integration — HTTP client for the whatsapp-sidecar service."""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SIDECAR_BASE = settings.WHATSAPP_SIDECAR_URL
SIDECAR_TIMEOUT = 30.0


async def start_session(user_id: str) -> dict:
    """POST /sessions/{user_id}/start — returns {status, qr}."""
    async with httpx.AsyncClient(timeout=SIDECAR_TIMEOUT) as client:
        resp = await client.post(f"{SIDECAR_BASE}/sessions/{user_id}/start")
        resp.raise_for_status()
        return resp.json()


async def get_qr(user_id: str) -> dict:
    """GET /sessions/{user_id}/qr — returns {status, qr}."""
    async with httpx.AsyncClient(timeout=SIDECAR_TIMEOUT) as client:
        resp = await client.get(f"{SIDECAR_BASE}/sessions/{user_id}/qr")
        resp.raise_for_status()
        return resp.json()


async def get_status(user_id: str) -> str:
    """GET /sessions/{user_id}/status — returns status string."""
    async with httpx.AsyncClient(timeout=SIDECAR_TIMEOUT) as client:
        resp = await client.get(f"{SIDECAR_BASE}/sessions/{user_id}/status")
        resp.raise_for_status()
        return resp.json()["status"]


async def trigger_backfill(user_id: str) -> dict:
    """POST /sessions/{user_id}/backfill — 300s timeout, returns summary."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{SIDECAR_BASE}/sessions/{user_id}/backfill")
        resp.raise_for_status()
        return resp.json()


async def get_contacts(user_id: str) -> list[dict]:
    """GET /sessions/{user_id}/contacts — returns contacts list."""
    async with httpx.AsyncClient(timeout=SIDECAR_TIMEOUT) as client:
        resp = await client.get(f"{SIDECAR_BASE}/sessions/{user_id}/contacts")
        resp.raise_for_status()
        return resp.json()


async def destroy_session(user_id: str) -> None:
    """DELETE /sessions/{user_id}."""
    async with httpx.AsyncClient(timeout=SIDECAR_TIMEOUT) as client:
        resp = await client.delete(f"{SIDECAR_BASE}/sessions/{user_id}")
        resp.raise_for_status()
