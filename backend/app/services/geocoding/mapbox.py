from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.services.geocoding.exceptions import (
    GeocodingError,
    GeocodingNotFoundError,
    GeocodingRateLimitError,
)

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.mapbox.com/search/geocode/v6/forward"
_TIMEOUT = httpx.Timeout(10.0)
_MAX_RETRIES = 3


@dataclass(frozen=True)
class GeocodeResult:
    latitude: float
    longitude: float


class MapboxGeocoder:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        if not token:
            raise GeocodingError("Mapbox token is not configured")
        self._token = token
        self._client = client

    async def geocode(self, query: str) -> GeocodeResult:
        params = {"q": query, "access_token": self._token, "limit": 1}
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with self._session() as client:
                    resp = await client.get(_ENDPOINT, params=params, timeout=_TIMEOUT)
                if resp.status_code == 429:
                    raise GeocodingRateLimitError("Mapbox rate limit")
                if 500 <= resp.status_code < 600:
                    last_exc = GeocodingError(f"Mapbox 5xx: {resp.status_code}")
                    continue
                if resp.status_code >= 400:
                    logger.warning(
                        "Mapbox 4xx",
                        extra={"provider": "mapbox", "status": resp.status_code, "query": query},
                    )
                    raise GeocodingNotFoundError(f"Mapbox client error: {resp.status_code}")
                data = resp.json()
                features = data.get("features") or []
                if not features:
                    raise GeocodingNotFoundError("No results")
                lng, lat = features[0]["geometry"]["coordinates"]
                return GeocodeResult(latitude=float(lat), longitude=float(lng))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                continue
            except GeocodingRateLimitError:
                raise
            except GeocodingNotFoundError:
                raise
        logger.warning(
            "Mapbox exhausted retries",
            extra={"provider": "mapbox", "query": query},
            exc_info=last_exc,
        )
        raise GeocodingError(f"Mapbox failed after {_MAX_RETRIES} attempts: {last_exc}")

    def _session(self):
        if self._client is not None:
            return _NoopCM(self._client)
        return httpx.AsyncClient()


class _NoopCM:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._c = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._c

    async def __aexit__(self, *args: object) -> None:
        return None
