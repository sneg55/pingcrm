"""Celery tasks for Ping CRM background processing."""
from __future__ import annotations

import asyncio
import logging
import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.celery_app import celery_app  # noqa: F401 — registers the app
from app.core.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.user import User

logger = logging.getLogger(__name__)


def _run(coro):
    """Run an async coroutine synchronously inside a Celery task."""
    return asyncio.run(coro)


async def _notify_sync_failure(user_id: uuid.UUID, platform: str, error: str) -> None:
    """Create a notification when a background sync exhausts retries."""
    from app.models.notification import Notification

    async with AsyncSessionLocal() as db:
        db.add(Notification(
            user_id=user_id,
            notification_type="sync",
            title=f"{platform} sync failed",
            body=f"Sync failed after multiple retries: {error[:200]}",
            link="/settings",
        ))
        await db.commit()


# ---------------------------------------------------------------------------
# Gmail sync tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.sync_gmail_for_user", bind=True, max_retries=3)
def sync_gmail_for_user(self, user_id: str) -> dict:
    """
    Sync Gmail threads for a single user.

    Args:
        user_id: String representation of the user's UUID.

    Returns:
        A dict with ``new_interactions`` count and ``status``.
    """
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.gmail import sync_gmail_for_user as _gmail_sync

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("sync_gmail_for_user: user %s not found.", uid)
                return {"status": "user_not_found", "new_interactions": 0}

            new_count = await _gmail_sync(user, db)
            await db.commit()

        return {"status": "ok", "new_interactions": new_count}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("sync_gmail_for_user: invalid user_id %r", user_id)
        return {"status": "invalid_user_id", "new_interactions": 0}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_gmail_for_user failed for %s, retrying.", user_id)
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_gmail_all")
def sync_gmail_all() -> dict:
    """
    Beat-scheduled task: enqueue a ``sync_gmail_for_user`` task for every user
    that has a google_refresh_token set.

    Returns:
        A dict with ``queued`` count.
    """
    async def _get_user_ids() -> list[str]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User.id).where(User.google_refresh_token.isnot(None))
            )
            return [str(row) for row in result.scalars().all()]

    user_ids = _run(_get_user_ids())
    for uid in user_ids:
        sync_gmail_for_user.delay(uid)

    logger.info("sync_gmail_all: queued %d user(s).", len(user_ids))
    return {"queued": len(user_ids)}


# ---------------------------------------------------------------------------
# Telegram sync tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.sync_telegram_for_user", bind=True, max_retries=3)
def sync_telegram_for_user(self, user_id: str) -> dict:
    """
    Full Telegram sync for a single user: chats + group members + bios + scores.

    Creates a notification on completion.
    """
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.telegram import (
            sync_telegram_chats,
            sync_telegram_group_members,
            sync_telegram_bios,
        )
        from app.models.notification import Notification
        from app.services.scoring import calculate_score

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("sync_telegram_for_user: user %s not found.", uid)
                return {"status": "user_not_found"}

            # 1. Sync DM chats
            chat_result = await sync_telegram_chats(user, db)
            chat_info = chat_result if isinstance(chat_result, dict) else {"new_interactions": chat_result, "new_contacts": 0, "affected_contact_ids": []}

            # 2. Sync group members
            group_result = {"new_contacts": 0, "updated_contacts": 0, "groups_scanned": 0}
            try:
                group_result = await sync_telegram_group_members(user, db)
            except Exception:
                logger.warning("sync_telegram_for_user: group member sync failed for %s", uid)

            # 3. Sync bios
            try:
                await sync_telegram_bios(user, db)
            except Exception:
                logger.warning("sync_telegram_for_user: bio sync failed for %s", uid)

            # 4. Recalculate scores
            try:
                affected = set(chat_info.get("affected_contact_ids", []))
                affected |= set(group_result.get("affected_contact_ids", []))
                for cid in affected:
                    await calculate_score(cid, db)
            except Exception:
                logger.warning("sync_telegram_for_user: score recalc failed for %s", uid)

            # 5. Notification
            parts = []
            if chat_info.get("new_interactions"):
                parts.append(f"{chat_info['new_interactions']} messages")
            if chat_info.get("new_contacts"):
                parts.append(f"{chat_info['new_contacts']} new contacts from DMs")
            if group_result.get("new_contacts"):
                parts.append(f"{group_result['new_contacts']} new contacts from groups")
            if group_result.get("groups_scanned"):
                parts.append(f"{group_result['groups_scanned']} groups scanned")
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Telegram sync completed",
                body=", ".join(parts) if parts else "No new activity",
                link="/contacts",
            ))
            await db.commit()

        return {
            "status": "ok",
            "new_interactions": chat_info.get("new_interactions", 0),
            "new_contacts": chat_info.get("new_contacts", 0),
            "group_members": group_result,
        }

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("sync_telegram_for_user: invalid user_id %r", user_id)
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_telegram_for_user failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            _run(_notify_sync_failure(uid, "Telegram", str(exc)))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_telegram_all")
def sync_telegram_all() -> dict:
    """
    Beat-scheduled task: enqueue a ``sync_telegram_for_user`` task for every
    user that has a telegram_session set.

    Returns:
        A dict with ``queued`` count.
    """
    async def _get_user_ids() -> list[str]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User.id).where(User.telegram_session.isnot(None))
            )
            return [str(row) for row in result.scalars().all()]

    user_ids = _run(_get_user_ids())
    for uid in user_ids:
        sync_telegram_for_user.delay(uid)

    logger.info("sync_telegram_all: queued %d user(s).", len(user_ids))
    return {"queued": len(user_ids)}


# ---------------------------------------------------------------------------
# Follow-up suggestion tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.generate_weekly_suggestions", bind=True, max_retries=3)
def generate_weekly_suggestions(self, user_id: str) -> dict:
    """Generate follow-up suggestions for a single user.

    Args:
        user_id: String representation of the user's UUID.

    Returns:
        A dict with ``generated`` count and ``status``.
    """
    async def _generate(uid: uuid.UUID) -> dict:
        from app.services.followup_engine import generate_suggestions
        from app.services.notifications import notify_new_suggestions

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("generate_weekly_suggestions: user %s not found.", uid)
                return {"status": "user_not_found", "generated": 0}

            suggestions = await generate_suggestions(uid, db)
            if suggestions:
                await notify_new_suggestions(uid, len(suggestions), db)
            await db.commit()

        return {"status": "ok", "generated": len(suggestions)}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("generate_weekly_suggestions: invalid user_id %r", user_id)
        return {"status": "invalid_user_id", "generated": 0}

    try:
        return _run(_generate(uid))
    except Exception as exc:
        logger.exception("generate_weekly_suggestions failed for %s, retrying.", user_id)
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.send_weekly_digests")
def send_weekly_digests() -> dict:
    """Beat-scheduled task: send weekly digest emails to all users (Mondays 09:00 UTC).

    Returns:
        A dict with ``sent`` and ``errors`` counts.
    """
    async def _send_all() -> dict:
        from app.services.digest_email import send_weekly_digest

        sent = 0
        errors = 0

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User.id))
            user_ids = result.scalars().all()

            for uid in user_ids:
                try:
                    await send_weekly_digest(uid, db)
                    sent += 1
                except Exception:
                    logger.exception("send_weekly_digests: failed for user %s.", uid)
                    errors += 1

        return {"sent": sent, "errors": errors}

    result = _run(_send_all())
    logger.info(
        "send_weekly_digests: sent=%d errors=%d", result["sent"], result["errors"]
    )
    return result


# ---------------------------------------------------------------------------
# Relationship scoring task
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.update_relationship_scores")
def update_relationship_scores() -> dict:
    """
    Beat-scheduled task: recalculate relationship scores for all contacts.

    Returns:
        A dict with ``updated`` count and ``errors`` count.
    """
    async def _update_all() -> dict:
        from app.services.scoring import calculate_score

        updated = 0
        errors = 0

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Contact.id))
            contact_ids = result.scalars().all()

            for contact_id in contact_ids:
                try:
                    await calculate_score(contact_id, db)
                    updated += 1
                except Exception:
                    logger.exception(
                        "update_relationship_scores: failed for contact %s.", contact_id
                    )
                    errors += 1

            await db.commit()

        return {"updated": updated, "errors": errors}

    result = _run(_update_all())
    logger.info(
        "update_relationship_scores: updated=%d errors=%d",
        result["updated"],
        result["errors"],
    )
    return result


# ---------------------------------------------------------------------------
# Twitter activity polling tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.poll_twitter_activity", bind=True, max_retries=3)
def poll_twitter_activity(self, user_id: str) -> dict:
    """Poll Twitter activity for all contacts of a single user.

    Fetches recent tweets and bio changes, then runs LLM classification to
    detect noteworthy events (job changes, fundraising, etc.).

    Args:
        user_id: String representation of the user's UUID.

    Returns:
        A dict with ``contacts_processed`` and ``events_created`` counts.
    """
    async def _poll(uid: uuid.UUID) -> dict:
        import uuid as _uuid_mod

        from app.integrations.twitter import poll_contacts_activity
        from app.services.event_classifier import process_contact_activity
        from app.services.notifications import notify_detected_event

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("poll_twitter_activity: user %s not found.", uid)
                return {"status": "user_not_found", "contacts_processed": 0, "events_created": 0}

            activity_records = await poll_contacts_activity(user, db)

            total_events = 0
            for record in activity_records:
                contact_name = record.get("twitter_handle", "Unknown")
                bio_change_payload = None
                if record.get("bio_changed"):
                    bio_change_payload = {
                        "old_bio": record.get("previous_bio", ""),
                        "new_bio": record.get("current_bio", ""),
                        "contact_name": contact_name,
                    }

                contact_uuid = _uuid_mod.UUID(record["contact_id"])
                events = await process_contact_activity(
                    contact_id=contact_uuid,
                    tweets=record.get("tweets", []),
                    bio_change=bio_change_payload,
                    db=db,
                )
                total_events += len(events)

                # Create notifications for detected events
                for event in events:
                    await notify_detected_event(
                        user_id=uid,
                        event_summary=event.summary,
                        contact_name=contact_name,
                        contact_id=contact_uuid,
                        db=db,
                    )

            await db.commit()

        return {
            "status": "ok",
            "contacts_processed": len(activity_records),
            "events_created": total_events,
        }

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("poll_twitter_activity: invalid user_id %r", user_id)
        return {"status": "invalid_user_id", "contacts_processed": 0, "events_created": 0}

    try:
        return _run(_poll(uid))
    except Exception as exc:
        logger.exception("poll_twitter_activity failed for %s, retrying.", user_id)
        raise self.retry(exc=exc, countdown=120) from exc


@shared_task(name="app.services.tasks.sync_twitter_dms_for_user", bind=True, max_retries=3)
def sync_twitter_dms_for_user(self, user_id: str) -> dict:
    """Full Twitter sync: DMs + mentions + bios + scores + notification."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.twitter import (
            sync_twitter_dms,
            sync_twitter_mentions,
            sync_twitter_bios,
            _user_bearer_headers,
            _build_twitter_id_to_contact_map,
        )
        from app.models.notification import Notification
        from app.services.scoring import calculate_score

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user is None:
                return {"status": "user_not_found"}

            headers = await _user_bearer_headers(user, db)
            id_map = await _build_twitter_id_to_contact_map(user, db, headers) if headers else None

            dm_result = await sync_twitter_dms(user, db, _id_map=id_map, _headers=headers)
            mentions = await sync_twitter_mentions(user, db, _id_map=id_map, _headers=headers)

            dm_interactions = dm_result["new_interactions"] if isinstance(dm_result, dict) else dm_result
            new_contacts = dm_result.get("new_contacts", 0) if isinstance(dm_result, dict) else 0

            # Sync bios
            bio_result = {"bios_updated": 0, "bio_changes": 0}
            try:
                bio_result = await sync_twitter_bios(user, db)
            except Exception:
                logger.warning("sync_twitter: bio sync failed for %s", uid)

            # Recalculate scores
            try:
                contacts_result = await db.execute(
                    select(Contact.id).where(Contact.user_id == uid)
                )
                for (cid,) in contacts_result.all():
                    await calculate_score(cid, db)
            except Exception:
                logger.warning("sync_twitter: score recalc failed for %s", uid)

            # Notification
            parts = []
            if dm_interactions:
                parts.append(f"{dm_interactions} DMs")
            if mentions:
                parts.append(f"{mentions} mentions")
            if new_contacts:
                parts.append(f"{new_contacts} new contacts")
            if bio_result.get("bio_changes"):
                parts.append(f"{bio_result['bio_changes']} bio changes")
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Twitter sync completed",
                body=", ".join(parts) if parts else "No new activity",
                link="/contacts",
            ))
            await db.commit()

        return {"status": "ok", "dms": dm_interactions, "mentions": mentions, "new_contacts": new_contacts}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id"}

    try:
        return _run(_sync(uid))
    except Exception as exc:
        logger.exception("sync_twitter_dms_for_user failed for %s, retrying.", user_id)
        if self.request.retries >= self.max_retries:
            _run(_notify_sync_failure(uid, "Twitter", str(exc)))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.poll_twitter_all")
def poll_twitter_all() -> dict:
    """Beat-scheduled task: enqueue poll_twitter_activity + DM sync for every user.

    Returns:
        A dict with ``queued`` count.
    """
    async def _get_user_ids() -> list[str]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User.id))
            return [str(row) for row in result.scalars().all()]

    user_ids = _run(_get_user_ids())
    for uid in user_ids:
        poll_twitter_activity.delay(uid)
        sync_twitter_dms_for_user.delay(uid)

    logger.info("poll_twitter_all: queued %d user(s) for activity + DMs.", len(user_ids))
    return {"queued": len(user_ids)}


# ---------------------------------------------------------------------------
# Google sync tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.sync_google_contacts_for_user", bind=True, max_retries=3)
def sync_google_contacts_for_user(self, user_id: str) -> dict:
    """Sync Google Contacts for a single user in background."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.google_auth import refresh_access_token
        from app.integrations.google_contacts import fetch_google_contacts
        from app.models.google_account import GoogleAccount
        from app.models.notification import Notification

        async with AsyncSessionLocal() as db:
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
            errors: list[str] = []

            for account_email, token in refresh_tokens:
                try:
                    access_token = refresh_access_token(token)
                    google_contacts = fetch_google_contacts(access_token)
                except Exception as exc:
                    errors.append(f"{account_email}: {exc}")
                    continue

                for fields in google_contacts:
                    try:
                        raw_name = fields.get("full_name")
                        # Parse "Name | Company" patterns
                        if raw_name and not fields.get("company"):
                            import re as _re
                            _name_org_re = _re.compile(r"^(.+?)\s*(?:\||@|/|—|–|-\s)\s*(.+)$")
                            m = _name_org_re.match(raw_name)
                            if m:
                                fields["full_name"] = m.group(1).strip()
                                fields["company"] = m.group(2).strip()

                        emails = fields.get("emails", [])
                        existing = None
                        if emails:
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
                            if fields.get("company") and not existing.company:
                                existing.company = fields["company"]
                            if fields.get("title") and not existing.title:
                                existing.title = fields["title"]
                            new_phones = [p for p in fields.get("phones", []) if p not in (existing.phones or [])]
                            if new_phones:
                                existing.phones = list(existing.phones or []) + new_phones
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
                            )
                            db.add(contact)
                            created_count += 1
                    except Exception as exc:
                        errors.append(f"Contact error: {exc}")

            parts = []
            if created_count:
                parts.append(f"{created_count} new")
            if updated_count:
                parts.append(f"{updated_count} updated")
            if errors:
                parts.append(f"{len(errors)} errors")
            db.add(Notification(
                user_id=uid,
                notification_type="sync",
                title="Google Contacts sync completed",
                body=", ".join(parts) if parts else "No changes",
                link="/contacts",
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
            _run(_notify_sync_failure(uid, "Google Contacts", str(exc)))
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(name="app.services.tasks.sync_google_calendar_for_user", bind=True, max_retries=3)
def sync_google_calendar_for_user(self, user_id: str) -> dict:
    """Sync Google Calendar events for a single user in background."""
    async def _sync(uid: uuid.UUID) -> dict:
        from app.integrations.google_calendar import sync_calendar_events
        from app.models.google_account import GoogleAccount
        from app.models.notification import Notification

        async with AsyncSessionLocal() as db:
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
                link="/contacts",
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
            _run(_notify_sync_failure(uid, "Google Calendar", str(exc)))
        raise self.retry(exc=exc, countdown=60) from exc


# ---------------------------------------------------------------------------
# Snooze reactivation task
# ---------------------------------------------------------------------------


@shared_task(name="app.services.tasks.reactivate_snoozed_suggestions")
def reactivate_snoozed_suggestions() -> dict:
    """Hourly task: set snoozed suggestions back to pending when their scheduled_for has passed."""
    async def _reactivate() -> int:
        from datetime import UTC, datetime

        from app.models.follow_up import FollowUpSuggestion
        from sqlalchemy import update

        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)
            result = await db.execute(
                update(FollowUpSuggestion)
                .where(
                    FollowUpSuggestion.status == "snoozed",
                    FollowUpSuggestion.scheduled_for <= now,
                )
                .values(status="pending")
                .returning(FollowUpSuggestion.id)
            )
            reactivated = len(result.all())
            await db.commit()
            return reactivated

    count = _run(_reactivate())
    logger.info("reactivate_snoozed_suggestions: reactivated %d suggestion(s).", count)
    return {"reactivated": count}
