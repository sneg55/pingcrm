class GeocodingError(Exception):
    """Base class for geocoding failures."""


class GeocodingRateLimitError(GeocodingError):
    """Retryable: provider rate-limited the request."""


class GeocodingNotFoundError(GeocodingError):
    """Terminal: provider returned no match for the input."""
