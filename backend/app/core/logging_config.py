"""Structured JSON logging configuration for PingCRM.

Provides:
- JSON-formatted log output for machine-parseable logs (AI-friendly)
- Rotating file handler (10MB, 5 backups) to logs/pingcrm.log when writable
- Console-only fallback when file logging is unavailable
- Environment-based log level control via LOG_LEVEL env var
- Per-module overrides via LOG_LEVEL_SQL, LOG_LEVEL_CELERY env vars
"""

import logging
import logging.config
import logging.handlers
import os
from pathlib import Path
from typing import Any

_file_logging_error: str | None = None


def _has_json_logger() -> bool:
    try:
        import pythonjsonlogger.jsonlogger  # noqa: F401

        return True
    except ImportError:
        return False


def _create_file_handler(**kwargs: Any) -> logging.Handler:
    """Create a rotating file handler, or a no-op handler if the file is unwritable."""
    global _file_logging_error

    try:
        return logging.handlers.RotatingFileHandler(**kwargs)
    except OSError as exc:
        _file_logging_error = str(exc)
        return logging.NullHandler()


def setup_logging() -> None:
    """Configure structured JSON logging for the application.

    Falls back to simple text formatting if python-json-logger is not installed
    (e.g. in test environments), and falls back to console-only logging when
    the log file cannot be created or opened.
    """
    global _file_logging_error
    _file_logging_error = None

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level_sql = os.getenv("LOG_LEVEL_SQL", "WARNING").upper()
    log_level_celery = os.getenv("LOG_LEVEL_CELERY", log_level).upper()
    use_json = _has_json_logger()

    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_file = log_dir / "pingcrm.log"

    formatters: dict = {
        "simple": {
            "format": "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }
    if use_json:
        formatters["json"] = {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            "rename_fields": {
                "levelname": "level",
                "asctime": "timestamp",
            },
            "timestamp": True,
        }

    fmt_name = "json" if use_json else "simple"
    active_handlers = ["console", "file"]

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": fmt_name,
                "stream": "ext://sys.stdout",
            },
            "file": {
                "()": _create_file_handler,
                "formatter": fmt_name,
                "filename": str(log_file),
                "maxBytes": 10_485_760,  # 10 MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            # Quiet SQLAlchemy engine logs (very noisy at INFO)
            "sqlalchemy.engine": {
                "level": log_level_sql,
                "handlers": active_handlers,
                "propagate": False,
            },
            # Celery loggers
            "celery": {
                "level": log_level_celery,
                "handlers": active_handlers,
                "propagate": False,
            },
            "celery.task": {
                "level": log_level_celery,
                "handlers": active_handlers,
                "propagate": False,
            },
            # Quiet noisy third-party libs
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "hpack": {"level": "WARNING"},
            "telethon": {"level": "WARNING"},
        },
        "root": {
            "level": log_level,
            "handlers": active_handlers,
        },
    }

    logging.config.dictConfig(config)

    if _file_logging_error is not None:
        logging.getLogger(__name__).warning(
            "File logging disabled; using console logging only",
            extra={"log_file": str(log_file), "reason": _file_logging_error},
        )

    # Add correlation filter to all handlers so request_id/task_id appear in logs
    from app.core.request_context import CorrelationFilter

    correlation_filter = CorrelationFilter()
    for handler in logging.root.handlers:
        handler.addFilter(correlation_filter)
