"""Google Contacts and Calendar sync Celery tasks."""
from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.database import task_session
from app.models.contact import Contact
from app.models.user import User
from app.services.task_jobs.common import _run, logger, notify_sync_failure


@shared_task(name="app.services.tasks.sync_google_contacts_for_user", bind=True, max_retries=3)
def sync_google_contacts_for_user(self, user_id: str) -> dict:
    """Sync Google Contacts for a single user in background."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.google_auth import refresh_access_token
        from app.integrations.google_contacts import fetch_google_contacts
        from app.models.google_account import GoogleAccount
        from app.models.notification import Notification

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            ga_result = await db.execute(
                select(GoogleAccount).where(GoogleAccount.user_id == uid)
            )
            refresh_tokens = [(ga.email, ga.refresh_token) for ga in ga_result.scalars().all()]
            if not refresh_tokens and user.google_refresh_token:
                refresh_tokens = [(user.email, user.google_refresh_token)]
            if not refresh_tokens:
                return {"status": "not_connected"}

            created_count = 0
            updated_count = 0
            archived_count = 0
            errors: list[str] = []
            seen_resource_names: set[str] = set()

            for account_email, token in refresh_tokens:
                try:
                    access_token = refresh_access_token(token)
                    google_contacts = fetch_google_contacts(access_token)
                except Exception as exc:
                    logger.warning("sync_google_contacts: failed to fetch contacts for %s", account_email, exc_info=True)
                    errors.append(f"{account_email}: {exc}")
                    continue

                for fields in google_contacts:
                    try:
                        resource_name = fields.get("resource_name")
                        if resource_name:
                            seen_resource_names.add(resource_name)

                        raw_name = fields.get("full_name")
                        # Parse "Name | Company" patterns
                        if raw_name and not fields.get("company"):
                            import re as _re
                            _name_org_re = _re.compile(r"^(.+?)\s*(?:\||@|/|—|–|-\s)\s*(.+)$")
                            m = _name_org_re.match(raw_name)
                            if m:
                                fields["full_name"] = m.group(1).strip()
                                fields["company"] = m.group(2).strip()

                        emails = fields.get("emails") or []
                        existing = None

                        # Match by google_resource_name first
                        if resource_name:
                            r = await db.execute(
                                select(Contact).where(
                                    Contact.user_id == uid,
                                    Contact.google_resource_name == resource_name,
                                ).limit(1)
                            )
                            existing = r.scalar_one_or_none()

                        # Fall back to email matching
                        if not existing and emails:
                            for email in emails:
                                r = await db.execute(
                                    select(Contact).where(
                                        Contact.user_id == uid,
                                        Contact.emails.any(email),
                                    ).limit(1)
                                )
                                existing = r.scalar_one_or_none()
                                if existing:
                                    break

                        if existing:
                            if raw_name and not existing.full_name:
                                existing.full_name = raw_name
                            if fields.get("given_name") and not existing.given_name:
                                existing.given_name = fields["given_name"]
                            if fields.get("family_name") and not existing.family_name:
                                existing.family_name = fields["family_name"]
                            if fields.get("company") and not existing.company:
                                existing.company = fields["company"]
                            if fields.get("title") and not existing.title:
                                existing.title = fields["title"]
                            new_phones = [p for p in fields.get("phones", []) if p not in (existing.phones or [])]
                            if new_phones:
                                existing.phones = list(existing.phones or []) + new_phones
                            # Stamp resource_name on existing contacts
                            if resource_name and not existing.google_resource_name:
                                existing.google_resource_name = resource_name
                            updated_count += 1
                        else:
                            contact = Contact(
                                user_id=uid,
                                full_name=raw_name,
                                given_name=fields.get("given_name"),
                                family_name=fields.get("family_name"),
                                emails=emails,
                                phones=fields.get("phones", []),
                                company=fields.get("company"),
                                title=fields.get("title"),
                                source="google",
                                google_resource_name=resource_name,
                            )
                            db.add(contact)
                            created_count += 1
                    except Exception as exc:
                        name_hint = fields.get("full_name") or ", ".join(fields.get("emails", [])[:1]) or "unknown"
                        logger.warning("sync_google_contacts: failed to upsert contact %r for user %s", name_hint, uid, exc_info=True)
                        errors.append(f"{name_hint}: {exc}")

            # Archive contacts deleted from Google
            if seen_resource_names:
                stale_result = await db.execute(
                    select(Contact).where(
                        Contact.user_id == uid,
                        Contact.google_resource_name.isnot(None),
                        Contact.google_resource_name.notin_(seen_resource_names),
                        Contact.priority_level != "archived",
                    )
                )
                for stale in stale_result.scalars().all():
                    stale.priority_level = "archived"
                    archived_count += 1
                if archived_count:
                    logger.info(
                        "sync_google_contacts: archived %d contact(s) deleted from Google for user %s",
                        archived_count, uid,
                    )

            # Rescore contacts that have interactions
            if created_count or updated_count:
                from app.services.scoring import calculate_score

                score_result = await db.execute(
                    select(Contact.id).where(
                        Contact.user_id == uid,
                        Contact.last_interaction_at.isnot(None),
                    )
                )
                for (cid,) in score_result.all():
                    try:
                        await calculate_score(cid, db)
                    except Exception:
                        logger.warning("google_contacts: score recalc failed for contact %s", cid, exc_info=True)

            parts = []
            if created_count:
                parts.append(f"{created_count} new")
            if updated_count:
                parts.append(f"{updated_count} updated")
            if archived_count:
                parts.append(f"{archived_count} archived")
            if errors:
                parts.append(f"{len(errors)} errors")
            body = ", ".join(parts) if parts else "No changes"
            if errors:
                body += "\n\nErrors:\n" + "\n".join(f"- {e}" for e in errors[:20])
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Google Contacts sync completed",
                body=body,
                link="/contacts?sort=recent",
            ))
            await db.commit()

        return {"status": "ok", "created": created_count, "updated": updated_count}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_google_contacts_for_user failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Google Contacts", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_google_calendar_for_user", bind=True, max_retries=3)
def sync_google_calendar_for_user(self, user_id: str) -> dict:
    """Sync Google Calendar events for a single user in background."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.google_calendar import sync_calendar_events
        from app.models.google_account import GoogleAccount
        from app.models.notification import Notification

        async with task_session() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            ga_result = await db.execute(
                select(GoogleAccount).where(GoogleAccount.user_id == uid)
            )
            accounts = list(ga_result.scalars().all())

            if not accounts and not user.google_refresh_token:
                return {"status": "not_connected"}

            cal_result = {"new_contacts": 0, "new_interactions": 0, "events_processed": 0}
            if not accounts and user.google_refresh_token:
                cal_result = await sync_calendar_events(user, db)
            else:
                for ga in accounts:
                    original_token = user.google_refresh_token
                    user.google_refresh_token = ga.refresh_token
                    try:
                        r = await sync_calendar_events(user, db)
                        cal_result["new_contacts"] += r.get("new_contacts", 0)
                        cal_result["new_interactions"] += r.get("new_interactions", 0)
                        cal_result["events_processed"] += r.get("events_processed", 0)
                    except Exception as exc:
                        logger.warning("Calendar sync failed for %s: %s", ga.email, exc)
                    finally:
                        user.google_refresh_token = original_token

            # Rescore contacts that have interactions
            if cal_result.get("new_interactions") or cal_result.get("new_contacts"):
                from app.services.scoring import calculate_score

                score_result = await db.execute(
                    select(Contact.id).where(
                        Contact.user_id == uid,
                        Contact.last_interaction_at.isnot(None),
                    )
                )
                for (cid,) in score_result.all():
                    try:
                        await calculate_score(cid, db)
                    except Exception:
                        logger.warning("google_calendar: score recalc failed for contact %s", cid, exc_info=True)

            parts = []
            if cal_result.get("new_contacts"):
                parts.append(f"{cal_result['new_contacts']} new contacts")
            if cal_result.get("new_interactions"):
                parts.append(f"{cal_result['new_interactions']} meetings")
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Google Calendar sync completed",
                body=", ".join(parts) if parts else "No new events",
                link="/contacts?sort=recent",
            ))
            await db.commit()

        return {"status": "ok", **cal_result}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_google_calendar_for_user failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            notify_sync_failure.delay(str(uid), "Google Calendar", str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_google_calendar_all")
def sync_google_calendar_all() -> dict:
    """Beat-scheduled task: enqueue a ``sync_google_calendar_for_user`` task for every
    user that has a google_refresh_token set.

    Returns:
        A dict with ``queued`` count.
    """
    async def _get_user_ids() -> list[str]:
        async with task_session() as db:
            result = await db.execute(
                select(User.id).where(User.google_refresh_token.isnot(None))
            )
            return [str(row) for row in result.scalars().all()]

    user_ids = _run(_get_user_ids())
    for uid in user_ids:
        sync_google_calendar_for_user.delay(uid)

    logger.info("sync_google_calendar_all: queued %d user(s).", len(user_ids))
    return {"queued": len(user_ids)}
