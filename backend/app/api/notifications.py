import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=dict)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    link: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    base_query = select(Notification).where(Notification.user_id == current_user.id)
    if link:
        base_query = base_query.where(Notification.link == link)

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        base_query.order_by(Notification.created_at.desc()).offset(offset).limit(page_size)
    )
    notifications = result.scalars().all()

    return {
        "data": [
            {
                "id": str(n.id),
                "notification_type": n.notification_type,
                "title": n.title,
                "body": n.body,
                "read": n.read,
                "link": n.link,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "error": None,
        "meta": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size) if total > 0 else 1,
        },
    }


@router.get("/unread-count", response_model=dict)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(func.count()).where(
            Notification.user_id == current_user.id,
            Notification.read == False,  # noqa: E712
        )
    )
    count = result.scalar_one()
    return {"data": {"count": count}, "error": None}


@router.put("/read-all", response_model=dict)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read == False)  # noqa: E712
        .values(read=True)
    )
    return {"data": {"marked": True}, "error": None}


@router.put("/{notification_id}/read", response_model=dict)
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notif.read = True
    await db.flush()
    return {"data": {"id": str(notif.id), "read": True}, "error": None}
