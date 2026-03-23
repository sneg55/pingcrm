"""Structured JSON logging configuration for PingCRM.

Provides:
- JSON-formatted log output for machine-parseable logs (AI-friendly)
- Rotating file handler (10MB, 5 backups) to logs/pingcrm.log
- Environment-based log level control via LOG_LEVEL env var
- Per-module overrides via LOG_LEVEL_SQL, LOG_LEVEL_CELERY env vars
"""
import logging
import logging.config
import os
from pathlib import Path


def setup_logging() -> None:
    """Configure structured JSON logging for the application."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level_sql = os.getenv("LOG_LEVEL_SQL", "WARNING").upper()
    log_level_celery = os.getenv("LOG_LEVEL_CELERY", log_level).upper()

    # Ensure logs directory exists
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = str(log_dir / "pingcrm.log")

    json_format = "%(asctime)s %(levelname)s %(name)s %(message)s"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": json_format,
                "rename_fields": {
                    "levelname": "level",
                    "asctime": "timestamp",
                },
                "timestamp": True,
            },
            "simple": {
                "format": "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json",
                "filename": log_file,
                "maxBytes": 10_485_760,  # 10 MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            # Quiet SQLAlchemy engine logs (very noisy at INFO)
            "sqlalchemy.engine": {
                "level": log_level_sql,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            # Celery loggers
            "celery": {
                "level": log_level_celery,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "celery.task": {
                "level": log_level_celery,
                "handlers": ["console", "file"],
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
            "handlers": ["console", "file"],
        },
    }

    logging.config.dictConfig(config)

    # Add correlation filter to all handlers so request_id/task_id appear in logs
    from app.core.request_context import CorrelationFilter
    correlation_filter = CorrelationFilter()
    for handler in logging.root.handlers:
        handler.addFilter(correlation_filter)
