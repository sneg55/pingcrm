"""Request correlation context for structured logging.

Provides a contextvars-based request_id that is:
- Generated per HTTP request (FastAPI middleware)
- Propagated to Celery tasks via task headers
- Injected into every log record via a logging Filter
"""
import logging
import uuid
from contextvars import ContextVar

# Context variables for correlation
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
task_id_var: ContextVar[str] = ContextVar("task_id", default="")


class CorrelationFilter(logging.Filter):
    """Inject request_id and task_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")  # type: ignore[attr-defined]
        record.task_id = task_id_var.get("")  # type: ignore[attr-defined]
        return True
