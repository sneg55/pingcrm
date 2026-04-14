"""SQLAlchemy event listeners for side-effects on model changes."""
from __future__ import annotations

import logging

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.services.task_jobs.geocoding import geocode_contact

_log = logging.getLogger(__name__)


@event.listens_for(Session, "after_flush")
def _enqueue_geocode(session: Session, flush_context) -> None:
    targets: list[Contact] = []
    for obj in session.new:
        if isinstance(obj, Contact) and obj.location:
            targets.append(obj)
    for obj in session.dirty:
        if not isinstance(obj, Contact):
            continue
        state = inspect(obj)
        hist = state.attrs.location.history
        if hist.has_changes():
            targets.append(obj)

    if not targets:
        return

    def _fire(_session):
        for c in targets:
            try:
                geocode_contact.delay(str(c.id))
            except Exception:
                _log.warning(
                    "geocode_contact enqueue failed",
                    extra={"provider": "celery", "contact_id": str(c.id)},
                    exc_info=True,
                )

    event.listen(session, "after_commit", _fire, once=True)
