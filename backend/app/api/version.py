"""Version-check endpoint for self-hosters."""
from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.responses import Envelope
from app.schemas.version import VersionData
from app.services.tasks import check_for_updates
from app.services.version_checker import (
    get_cached_status,
    has_recent_failure,
    is_disabled,
)

router = APIRouter(prefix="/api/v1", tags=["version"])


@router.get("/version", response_model=Envelope[VersionData])
async def get_version(
    current_user: User = Depends(get_current_user),
) -> Envelope[VersionData]:
    """Return current app version and latest available release, if known."""
    status = await get_cached_status()
    if (
        not is_disabled()
        and status.latest is None
        and not await has_recent_failure()
    ):
        check_for_updates.delay()
    return {"data": status, "error": None}
