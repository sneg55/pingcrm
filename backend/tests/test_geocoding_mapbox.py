from __future__ import annotations

import httpx
import pytest
import respx

from app.services.geocoding import (
    GeocodingNotFoundError,
    GeocodingRateLimitError,
    GeocodingError,
    MapboxGeocoder,
)


@pytest.mark.asyncio
async def test_geocode_returns_lat_lng_on_success():
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.mapbox.com/search/geocode/v6/forward").respond(
            200,
            json={
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
                        "properties": {"name": "San Francisco"},
                    }
                ]
            },
        )
        geocoder = MapboxGeocoder(token="test-token")
        result = await geocoder.geocode("San Francisco, CA")
        assert result.latitude == 37.7749
        assert result.longitude == -122.4194
