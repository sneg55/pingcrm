import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def create_notification(
    user_id: uuid.UUID,
    notification_type: str,
    title: str,
    body: str,
    link: str | None,
    db: AsyncSession,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        link=link,
    )
    db.add(notif)
    await db.flush()
    await db.refresh(notif)
    return notif


async def notify_new_suggestions(
    user_id: uuid.UUID, count: int, db: AsyncSession
) -> Notification:
    return await create_notification(
        user_id=user_id,
        notification_type="suggestion",
        title=f"{count} new follow-up suggestions",
        body=f"You have {count} new people to reach out to this week.",
        link="/suggestions",
        db=db,
    )


async def notify_detected_event(
    user_id: uuid.UUID,
    event_summary: str,
    contact_name: str,
    contact_id: uuid.UUID,
    db: AsyncSession,
) -> Notification:
    return await create_notification(
        user_id=user_id,
        notification_type="event",
        title=f"New activity from {contact_name}",
        body=event_summary,
        link=f"/contacts/{contact_id}",
        db=db,
    )
