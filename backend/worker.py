"""
Celery worker entry point for PingCRM.

Run the worker (with Beat scheduler) using:

    celery -A worker.celery_app worker --beat --loglevel=info

For separate beat scheduler process:

    celery -A worker.celery_app beat --loglevel=info
    celery -A worker.celery_app worker --loglevel=info
"""
from app.core.logging_config import setup_logging

setup_logging()

import app.core.celery_signals  # noqa: F401, E402 — register signal handlers
from app.core.celery_app import celery_app  # noqa: F401, E402

__all__ = ["celery_app"]
