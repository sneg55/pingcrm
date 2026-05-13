"""Auto-tagging Celery tasks."""
from __future__ import annotations

import asyncio
import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.database import task_session
from app.models.contact import Contact
from app.models.user import User
from app.services.task_jobs.common import _run, logger, notify_tagging_failure


@shared_task(
    name="app.services.tasks.apply_tags_to_contacts",
    bind=True,
    max_retries=2,
    soft_time_limit=3600,  # 60 minutes for large contact lists (5k+)
    time_limit=3900,       # 65 minutes hard limit
)
def apply_tags_to_contacts(self, user_id: str, contact_ids: list[str] | None = None) -> dict:
    """Apply approved taxonomy tags to contacts in bulk.

    Args:
        user_id: String representation of the user's UUID.
        contact_ids: Optional list of contact ID strings. If None, tags all non-archived contacts.

    Returns:
        A dict with ``tagged_count`` and ``status``.
    """
    async def _apply(uid: uuid.UUID) -> dict:
        from app.models.interaction import Interaction
        from app.models.notification import Notification
        from app.models.tag_taxonomy import TagTaxonomy
        from app.services.auto_tagger import assign_tags, merge_tags

        async with task_session() as db:
            # Load taxonomy
            tax_result = await db.execute(
                select(TagTaxonomy).where(
                    TagTaxonomy.user_id == uid,
                    TagTaxonomy.status == "approved",
                )
            )
            taxonomy = tax_result.scalar_one_or_none()
            if not taxonomy:
                return {"status": "no_taxonomy", "tagged_count": 0}

            from app.core.config import settings as app_settings

            if not app_settings.ANTHROPIC_API_KEY:
                db.add(Notification(
                    user_id=uid,
                    notification_type="tagging",
                    title="Auto-tagging failed",
                    body="ANTHROPIC_API_KEY is not configured. Set it in your .env file.",
                    link="/settings?tab=tags",
                ))
                await db.commit()
                return {"status": "no_api_key", "tagged_count": 0}

            # Build set of all taxonomy tags for skip-detection
            all_taxonomy_tags = set()
            for tag_list in taxonomy.categories.values():
                all_taxonomy_tags.update(t.lower() for t in tag_list)

            # Load contacts — skip those that already have taxonomy tags
            if contact_ids:
                cid_uuids = [uuid.UUID(c) for c in contact_ids]
                result = await db.execute(
                    select(Contact).where(
                        Contact.id.in_(cid_uuids),
                        Contact.user_id == uid,
                    )
                )
            else:
                from sqlalchemy import or_
                result = await db.execute(
                    select(Contact).where(
                        Contact.user_id == uid,
                        Contact.priority_level != "archived",
                        or_(Contact.tags.is_(None), ~Contact.tags.contains(["2nd tier"])),
                    )
                )
            all_contacts = list(result.scalars().all())

            # Filter out contacts that already have at least one taxonomy tag
            contacts = []
            skipped = 0
            for c in all_contacts:
                if c.tags:
                    existing_lower = {t.lower() for t in c.tags}
                    if existing_lower & all_taxonomy_tags:
                        skipped += 1
                        continue
                contacts.append(c)

            total_eligible = len(contacts)
            logger.info(
                "apply_tags_to_contacts: %d eligible, %d already tagged, %d total for user %s",
                total_eligible, skipped, len(all_contacts), uid,
            )

            if not contacts:
                db.add(Notification(
                    user_id=uid,
                    notification_type="tagging",
                    title="Auto-tagging finished",
                    body=f"All {skipped} contacts already have taxonomy tags." if skipped else "No eligible contacts to tag.",
                    link="/settings?tab=tags",
                ))
                await db.commit()
                return {"status": "ok", "tagged_count": 0}

            # Create ONE shared Anthropic client to avoid connection pool leaks
            from app.services.auto_tagger import _get_anthropic_client
            anthropic_client = _get_anthropic_client()

            tagged = 0
            errors = 0
            BATCH_SIZE = 5  # concurrent API calls per batch
            DB_CHUNK = 200  # load interaction topics in chunks to avoid huge IN clause

            async def _tag_one(contact, topics):
                """Tag a single contact — returns (contact, new_tags) or (contact, None) on error."""
                try:
                    contact_data = {
                        "full_name": contact.full_name,
                        "title": contact.title,
                        "company": contact.company,
                        "twitter_bio": contact.twitter_bio,
                        "telegram_bio": contact.telegram_bio,
                        "notes": contact.notes,
                        "tags": contact.tags,
                        "location": contact.location,
                        "interaction_topics": topics,
                    }
                    new_tags = await assign_tags(
                        contact_data, taxonomy.categories, client=anthropic_client,
                    )
                    return (contact, new_tags)
                except Exception:
                    logger.warning(
                        "apply_tags_to_contacts: failed for contact %s", contact.id,
                        exc_info=True,
                    )
                    return (contact, None)

            # Process contacts in DB-level chunks
            for chunk_start in range(0, len(contacts), DB_CHUNK):
                chunk = contacts[chunk_start:chunk_start + DB_CHUNK]
                chunk_ids = [c.id for c in chunk]

                # Load interaction topics for this chunk only
                int_result = await db.execute(
                    select(Interaction.contact_id, Interaction.content_preview).where(
                        Interaction.contact_id.in_(chunk_ids),
                        Interaction.content_preview.isnot(None),
                    ).order_by(Interaction.occurred_at.desc())
                )
                topics_by_contact: dict[uuid.UUID, list[str]] = {}
                for row in int_result.all():
                    lst = topics_by_contact.setdefault(row[0], [])
                    if len(lst) < 10:
                        lst.append(row[1][:100])

                # Process in concurrent API batches
                for i in range(0, len(chunk), BATCH_SIZE):
                    batch = chunk[i:i + BATCH_SIZE]
                    results = await asyncio.gather(*[
                        _tag_one(c, topics_by_contact.get(c.id, []))
                        for c in batch
                    ])

                    for contact, new_tags in results:
                        if new_tags is None:
                            errors += 1
                        elif new_tags:
                            contact.tags = merge_tags(contact.tags, new_tags)
                            tagged += 1

                # Commit after each DB chunk to save progress
                await db.commit()
                logger.info(
                    "apply_tags_to_contacts: chunk %d-%d done, tagged=%d errors=%d for user %s",
                    chunk_start, chunk_start + len(chunk), tagged, errors, uid,
                )

            # Notification
            body = f"Tagged {tagged} of {total_eligible} contacts"
            if skipped:
                body += f" ({skipped} already tagged)"
            if errors:
                body += f" ({errors} errors — check worker logs)"
            db.add(Notification(
                user_id=uid,
                notification_type="tagging",
                title="Auto-tagging completed" if tagged > 0 else "Auto-tagging finished with issues",
                body=body,
                link="/settings?tab=tags",
            ))
            await db.commit()

        return {"status": "ok", "tagged_count": tagged}

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return {"status": "invalid_user_id", "tagged_count": 0}

    try:
        return _run(_apply(uid))
    except Exception as exc:
        logger.exception("apply_tags_to_contacts raised for %s", user_id)
        # Don't retry on soft time limit — partial results already committed
        from celery.exceptions import SoftTimeLimitExceeded  # noqa: E402
        if isinstance(exc, SoftTimeLimitExceeded):
            logger.warning("apply_tags_to_contacts: soft time limit hit for %s", user_id)
            # Notify user — partial progress was saved via periodic commits
            notify_tagging_failure.delay(str(uid), "Tagging timed out. Partial progress was saved. Try again to tag remaining contacts.")
            return {"status": "timeout", "tagged_count": 0}
        if self.request.retries >= self.max_retries:
            notify_tagging_failure.delay(str(uid), f"Tagging failed after retries: {str(exc)[:200]}")
        raise self.retry(exc=exc, countdown=30) from exc
