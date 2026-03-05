import csv
import io
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.integrations.google_auth import refresh_access_token
from app.integrations.google_contacts import fetch_google_contacts
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import (
    ContactCreate,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
    PaginationMeta,
)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


def envelope(data: Any, error: str | None = None, meta: dict | None = None) -> dict:
    return {"data": data, "error": error, "meta": meta}


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    tag: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactListResponse:
    base_query = select(Contact).where(Contact.user_id == current_user.id)

    if search:
        # Escape SQL LIKE wildcards to prevent wildcard injection
        safe_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base_query = base_query.where(
            or_(
                Contact.full_name.ilike(f"%{safe_search}%"),
                Contact.company.ilike(f"%{safe_search}%"),
            )
        )

    if tag:
        base_query = base_query.where(Contact.tags.any(tag))

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        base_query.order_by(Contact.created_at.desc()).offset(offset).limit(page_size)
    )
    contacts = result.scalars().all()

    return ContactListResponse(
        data=[ContactResponse.model_validate(c) for c in contacts],
        error=None,
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total > 0 else 1,
        ),
    )


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_in: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    contact = Contact(**contact_in.model_dump(), user_id=current_user.id)
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.get("/{contact_id}", response_model=dict)
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.put("/{contact_id}", response_model=dict)
async def update_contact(
    contact_id: uuid.UUID,
    contact_in: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    for field, value in contact_in.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)

    await db.flush()
    await db.refresh(contact)
    return envelope(ContactResponse.model_validate(contact).model_dump())


@router.delete("/{contact_id}", response_model=dict)
async def delete_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    await db.delete(contact)
    return envelope({"id": str(contact_id), "deleted": True})


@router.post("/import/csv", response_model=dict)
async def import_contacts_csv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    created: list[dict] = []
    errors: list[str] = []

    for i, row in enumerate(reader):
        try:
            contact = Contact(
                user_id=current_user.id,
                full_name=row.get("full_name") or row.get("name"),
                given_name=row.get("given_name") or row.get("first_name"),
                family_name=row.get("family_name") or row.get("last_name"),
                emails=[e.strip() for e in row.get("emails", "").split(";") if e.strip()],
                phones=[p.strip() for p in row.get("phones", "").split(";") if p.strip()],
                company=row.get("company") or row.get("organization"),
                title=row.get("title") or row.get("job_title"),
                twitter_handle=row.get("twitter_handle") or row.get("twitter") or row.get("x_handle"),
                telegram_username=row.get("telegram_username") or row.get("telegram"),
                notes=row.get("notes") or row.get("note"),
                tags=[t.strip() for t in row.get("tags", "").split(";") if t.strip()] or None,
                source="csv",
            )
            db.add(contact)
            await db.flush()
            created.append({"id": str(contact.id), "full_name": contact.full_name})
        except Exception as exc:
            errors.append(f"Row {i + 1}: {exc!s}")

    return envelope({"created": created, "errors": errors})


@router.post("/sync/google", response_model=dict)
async def sync_google_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Trigger a one-way sync from the authenticated user's Google Contacts.

    Returns counts of created and updated contacts, plus any per-contact errors.
    """
    if not current_user.google_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account not connected. Complete Google OAuth first.",
        )

    try:
        access_token = refresh_access_token(current_user.google_refresh_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to refresh Google access token: {exc}",
        )

    try:
        google_contacts = fetch_google_contacts(access_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch Google contacts: {exc}",
        )

    created_count = 0
    updated_count = 0
    errors: list[str] = []

    for fields in google_contacts:
        try:
            primary_emails: list[str] = fields.get("emails") or []

            # Try to match an existing contact by any of the Google emails.
            existing: Contact | None = None
            for email in primary_emails:
                result = await db.execute(
                    select(Contact).where(
                        Contact.user_id == current_user.id,
                        Contact.emails.any(email),  # type: ignore[arg-type]
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    break

            if existing:
                for key, value in fields.items():
                    if value is not None:
                        setattr(existing, key, value)
                await db.flush()
                updated_count += 1
            else:
                contact = Contact(user_id=current_user.id, **fields)
                db.add(contact)
                await db.flush()
                created_count += 1

        except Exception as exc:
            name = fields.get("full_name") or str(fields.get("emails"))
            errors.append(f"{name}: {exc!s}")

    return envelope({"created": created_count, "updated": updated_count, "errors": errors})
