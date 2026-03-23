"""Celery signal handlers for task lifecycle logging and correlation.

Logs task start/success/failure with structured context and propagates
request_id from the API call that dispatched the task.
"""
import logging
import time

from celery.signals import before_task_publish, task_prerun, task_postrun, task_failure

from app.core.request_context import request_id_var, task_id_var

logger = logging.getLogger("app.celery")

# Track task start times for duration calculation
_task_start_times: dict[str, float] = {}


@before_task_publish.connect
def propagate_request_id(headers: dict | None = None, **kwargs) -> None:  # type: ignore[no-untyped-def]
    """Pass the current request_id to the Celery task headers."""
    if headers is None:
        return
    rid = request_id_var.get("")
    if rid:
        headers["request_id"] = rid


@task_prerun.connect
def on_task_prerun(task_id: str | None = None, task: object | None = None, **kwargs) -> None:  # type: ignore[no-untyped-def]
    """Set correlation context and log task start."""
    if task_id:
        task_id_var.set(task_id)
        _task_start_times[task_id] = time.monotonic()

    # Restore request_id from task headers if available
    request = getattr(task, "request", None)
    if request:
        rid = (getattr(request, "headers", None) or {}).get("request_id", "")
        if rid:
            request_id_var.set(rid)

    task_name = getattr(task, "name", "unknown")
    logger.info(
        "task_start %s",
        task_name,
        extra={"task_name": task_name, "celery_task_id": task_id},
    )


@task_postrun.connect
def on_task_postrun(task_id: str | None = None, task: object | None = None, state: str | None = None, **kwargs) -> None:  # type: ignore[no-untyped-def]
    """Log task completion with duration."""
    task_name = getattr(task, "name", "unknown")
    duration_ms = 0
    if task_id and task_id in _task_start_times:
        duration_ms = round((time.monotonic() - _task_start_times.pop(task_id)) * 1000)

    logger.info(
        "task_end %s state=%s (%dms)",
        task_name,
        state,
        duration_ms,
        extra={
            "task_name": task_name,
            "celery_task_id": task_id,
            "task_state": state,
            "duration_ms": duration_ms,
        },
    )
    # Clean up context
    task_id_var.set("")


@task_failure.connect
def on_task_failure(  # type: ignore[no-untyped-def]
    task_id: str | None = None,
    exception: BaseException | None = None,
    traceback: object | None = None,
    sender: object | None = None,
    **kwargs,
) -> None:
    """Log task failure with exception details."""
    task_name = getattr(sender, "name", "unknown")
    duration_ms = 0
    if task_id and task_id in _task_start_times:
        duration_ms = round((time.monotonic() - _task_start_times.pop(task_id)) * 1000)

    retries = 0
    request = getattr(sender, "request", None)
    if request:
        retries = getattr(request, "retries", 0)

    logger.error(
        "task_failure %s: %s (%dms, retries=%d)",
        task_name,
        exception,
        duration_ms,
        retries,
        extra={
            "task_name": task_name,
            "celery_task_id": task_id,
            "duration_ms": duration_ms,
            "retries": retries,
            "exception_type": type(exception).__name__ if exception else None,
            "exception_message": str(exception) if exception else None,
        },
        exc_info=exception,
    )
