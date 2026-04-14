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


@pytest.mark.asyncio
async def test_geocode_raises_not_found_on_empty_features():
    with respx.mock() as mock:
        mock.get("https://api.mapbox.com/search/geocode/v6/forward").respond(200, json={"features": []})
        geocoder = MapboxGeocoder(token="test-token")
        with pytest.raises(GeocodingNotFoundError):
            await geocoder.geocode("nowhere")


@pytest.mark.asyncio
async def test_geocode_raises_not_found_on_4xx():
    with respx.mock() as mock:
        mock.get("https://api.mapbox.com/search/geocode/v6/forward").respond(400, json={})
        geocoder = MapboxGeocoder(token="test-token")
        with pytest.raises(GeocodingNotFoundError):
            await geocoder.geocode("bad query")


@pytest.mark.asyncio
async def test_geocode_raises_rate_limit_on_429():
    with respx.mock() as mock:
        mock.get("https://api.mapbox.com/search/geocode/v6/forward").respond(429, json={})
        geocoder = MapboxGeocoder(token="test-token")
        with pytest.raises(GeocodingRateLimitError):
            await geocoder.geocode("anywhere")


@pytest.mark.asyncio
async def test_geocode_retries_on_5xx_then_succeeds():
    with respx.mock() as mock:
        route = mock.get("https://api.mapbox.com/search/geocode/v6/forward")
        route.mock(
            side_effect=[
                httpx.Response(502, json={}),
                httpx.Response(
                    200,
                    json={
                        "features": [
                            {"geometry": {"coordinates": [10.0, 20.0], "type": "Point"}, "properties": {}}
                        ]
                    },
                ),
            ]
        )
        geocoder = MapboxGeocoder(token="test-token")
        result = await geocoder.geocode("Berlin")
        assert result.latitude == 20.0
        assert result.longitude == 10.0
