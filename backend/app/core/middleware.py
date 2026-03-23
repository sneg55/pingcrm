"""FastAPI middleware for request correlation and lifecycle logging."""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import request_id_var

logger = logging.getLogger("app.request")


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Generate a request_id per request and log request lifecycle."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        rid = str(uuid.uuid4())
        token = request_id_var.set(rid)

        start = time.monotonic()
        method = request.method
        path = request.url.path

        logger.info(
            "request_start %s %s",
            method,
            path,
            extra={"http_method": method, "http_path": path},
        )

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.exception(
                "request_error %s %s (%dms)",
                method,
                path,
                duration_ms,
                extra={
                    "http_method": method,
                    "http_path": path,
                    "duration_ms": duration_ms,
                    "http_status": 500,
                },
            )
            raise
        else:
            duration_ms = round((time.monotonic() - start) * 1000)
            status_code = response.status_code
            log_level = logging.WARNING if status_code >= 400 else logging.INFO
            logger.log(
                log_level,
                "request_end %s %s %d (%dms)",
                method,
                path,
                status_code,
                duration_ms,
                extra={
                    "http_method": method,
                    "http_path": path,
                    "http_status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_var.reset(token)
