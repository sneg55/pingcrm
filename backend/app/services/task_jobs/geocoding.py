"""Geocoding Celery tasks — resolve Contact.location to lat/lng via Mapbox."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app  # noqa: F401 — registers the app
from app.core.config import settings
from app.core.database import task_session
from app.models.contact import Contact
from app.services.geocoding import (
    GeocodingError,
    GeocodingNotFoundError,
    GeocodingRateLimitError,
    MapboxGeocoder,
)
from app.services.task_jobs.common import _run, logger

_geocoder: MapboxGeocoder | None = (
    MapboxGeocoder(token=settings.MAPBOX_SECRET_TOKEN)
    if settings.MAPBOX_SECRET_TOKEN
    else None
)


async def _do_geocode(
    session: AsyncSession,
    contact_id: str,
    geocoder: MapboxGeocoder,
) -> None:
    """Geocode a single contact, updating its lat/lng/geocoded_* fields.

    Idempotent: no-op if geocoded_location already matches the current location.
    """
    contact = (
        await session.execute(
            select(Contact).where(Contact.id == uuid.UUID(contact_id))
        )
    ).scalar_one_or_none()
    if contact is None:
        logger.info("geocode_contact: contact gone", extra={"contact_id": contact_id})
        return
    if contact.geocoded_location == contact.location:
        return
    now = datetime.now(UTC)
    if not contact.location:
        contact.latitude = None
        contact.longitude = None
        contact.geocoded_location = None
        contact.geocoded_at = now
        await session.commit()
        return
    try:
        result = await geocoder.geocode(contact.location)
    except GeocodingNotFoundError:
        logger.info(
            "geocode returned no match",
            extra={
                "provider": "mapbox",
                "contact_id": contact_id,
                "location": contact.location,
            },
        )
        contact.latitude = None
        contact.longitude = None
        contact.geocoded_location = contact.location
        contact.geocoded_at = now
        await session.commit()
        return
    contact.latitude = result.latitude
    contact.longitude = result.longitude
    contact.geocoded_location = contact.location
    contact.geocoded_at = now
    await session.commit()


@shared_task(
    name="app.services.tasks.geocode_contact",
    autoretry_for=(GeocodingRateLimitError, GeocodingError),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
    rate_limit="500/m",
)
def geocode_contact(contact_id: str) -> None:
    """Celery entry point — geocode a single contact by id."""
    if _geocoder is None:
        logger.info(
            "Mapbox token not configured, skipping geocode",
            extra={"contact_id": contact_id},
        )
        return

    async def _runner() -> None:
        async with task_session() as session:
            await _do_geocode(session, contact_id, _geocoder)

    _run(_runner())
