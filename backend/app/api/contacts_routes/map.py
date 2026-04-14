"""GET /api/v1/contacts/map — pins within a bounding box."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactMapPin
from app.schemas.responses import Envelope

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])

_HARD_LIMIT = 500


@router.get("/map", response_model=Envelope[list[ContactMapPin]])
async def contacts_map(
    bbox: str = Query(..., description="minLng,minLat,maxLng,maxLat"),
    limit: int = Query(500, ge=1, le=2000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[list[ContactMapPin]]:
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minLng,minLat,maxLng,maxLat")
    try:
        min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be minLng,minLat,maxLng,maxLat")

    effective_limit = min(limit, _HARD_LIMIT)

    where = [
        Contact.user_id == user.id,
        Contact.latitude.is_not(None),
        Contact.longitude.is_not(None),
        Contact.latitude >= min_lat,
        Contact.latitude <= max_lat,
        Contact.longitude >= min_lng,
        Contact.longitude <= max_lng,
    ]
    total = (
        await db.execute(select(func.count()).select_from(Contact).where(*where))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Contact)
            .where(*where)
            .order_by(Contact.relationship_score.desc())
            .limit(effective_limit)
        )
    ).scalars().all()
    return Envelope(
        data=[ContactMapPin.model_validate(c) for c in rows],
        meta={"total_in_bounds": total},
    )
