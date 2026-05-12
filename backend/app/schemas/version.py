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
