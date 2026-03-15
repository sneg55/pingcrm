from __future__ import annotations

from fastapi import APIRouter, UploadFile

from app.api.contacts_routes.shared import (
    Contact,
    Depends,
    Envelope,
    HTTPException,
    AsyncSession,
    User,
    envelope,
    get_current_user,
    get_db,
    select,
    status,
)
from app.schemas.responses import (
    CsvImportResult,
    LinkedInImportResult,
    LinkedInMessagesImportResult,
    ScoresRecalculatedData,
)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


@router.post("/import/csv", response_model=Envelope[CsvImportResult])
async def import_contacts_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[CsvImportResult]:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    from app.services.contact_import import import_csv

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    result = await import_csv(content, current_user.id, db)
    return envelope(result)


@router.post("/import/linkedin", response_model=Envelope[LinkedInImportResult])
async def import_linkedin_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[LinkedInImportResult]:
    """Import contacts from LinkedIn Connections.csv export."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    from app.services.contact_import import import_linkedin_connections

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    result = await import_linkedin_connections(content, current_user.id, db)
    return envelope(result)


@router.post("/import/linkedin-messages", response_model=Envelope[LinkedInMessagesImportResult])
async def import_linkedin_messages(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[LinkedInMessagesImportResult]:
    """Import LinkedIn messages.csv and create interactions matched to existing contacts."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    from app.services.contact_import import import_linkedin_messages as _import_messages

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    user_name = (current_user.full_name or current_user.email or "").lower()
    result = await _import_messages(content, current_user.id, user_name, db)
    return envelope(result)


@router.post("/scores/recalculate", response_model=Envelope[ScoresRecalculatedData])
async def recalculate_scores(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ScoresRecalculatedData]:
    """Recalculate relationship scores for all contacts of the authenticated user."""
    from app.services.scoring import calculate_score

    contacts_result = await db.execute(
        select(Contact.id).where(Contact.user_id == current_user.id)
    )
    updated = 0
    for (contact_id,) in contacts_result.all():
        await calculate_score(contact_id, db)
        updated += 1

    await db.flush()
    return envelope({"updated": updated})
