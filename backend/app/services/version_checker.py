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
    except ValueError:
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
