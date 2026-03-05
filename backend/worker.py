"""
Celery worker entry point for Ping CRM.

Run the worker (with Beat scheduler) using:

    celery -A worker.celery_app worker --beat --loglevel=info

For separate beat scheduler process:

    celery -A worker.celery_app beat --loglevel=info
    celery -A worker.celery_app worker --loglevel=info
"""
from app.core.celery_app import celery_app  # noqa: F401

__all__ = ["celery_app"]
