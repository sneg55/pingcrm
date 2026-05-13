"""Enrichment and promotion endpoints for individual contacts."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter

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
from app.schemas.responses import EnrichData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


@router.post("/{contact_id}/enrich", response_model=Envelope[EnrichData])
async def enrich_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[EnrichData]:
    """Enrich a contact using the Apollo People Enrichment API.

    Only fills in fields that are currently empty/null on the contact.
    """
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.emails and not contact.linkedin_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact has no email or LinkedIn URL. At least one is required for enrichment.",
        )

    from app.integrations.apollo import ApolloError, enrich_person

    try:
        enriched = await enrich_person(
            email=contact.emails[0] if contact.emails else None,
            linkedin_url=contact.linkedin_url if not contact.emails else None,
        )
    except ApolloError as exc:
        logger.warning(
            "enrich_contact: Apollo failed for contact %s: %s",
            contact_id,
            exc,
            extra={"provider": "apollo", "contact_id": str(contact_id)},
        )
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    if not enriched:
        return envelope({"fields_updated": [], "source": "apollo"})

    fields_updated: list[str] = []
    scalar_fields = [
        "given_name", "family_name", "full_name", "title", "company",
        "location", "linkedin_url", "twitter_handle", "avatar_url",
    ]
    for field in scalar_fields:
        if field in enriched and not getattr(contact, field, None):
            setattr(contact, field, enriched[field])
            fields_updated.append(field)

    if "phones" in enriched:
        existing_phones = set(contact.phones or [])
        new_phones = [p for p in enriched["phones"] if p not in existing_phones]
        if new_phones:
            contact.phones = list(existing_phones | set(new_phones))
            fields_updated.append("phones")

    if "emails" in enriched:
        existing_emails = set(contact.emails or [])
        new_emails = [e for e in enriched["emails"] if e not in existing_emails]
        if new_emails:
            contact.emails = list(existing_emails | set(new_emails))
            fields_updated.append("emails")

    if fields_updated:
        await db.flush()
        await db.refresh(contact)

    return envelope({"fields_updated": fields_updated, "source": "apollo"})


@router.post("/{contact_id}/extract-bio", response_model=Envelope[EnrichData])
async def extract_bio(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[EnrichData]:
    """Extract structured data from contact bios using AI."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    has_bios = any([
        contact.twitter_bio, contact.telegram_bio,
        contact.linkedin_bio, contact.linkedin_headline,
    ])
    if not has_bios and not contact.full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact has no bios or name to extract from.",
        )

    from app.services.bio_extractor import extract_from_bios

    extracted = await extract_from_bios(
        full_name=contact.full_name,
        given_name=contact.given_name,
        family_name=contact.family_name,
        title=contact.title,
        company=contact.company,
        twitter_bio=contact.twitter_bio,
        telegram_bio=contact.telegram_bio,
        linkedin_bio=contact.linkedin_bio,
        linkedin_headline=contact.linkedin_headline,
    )

    if not extracted:
        return envelope({"fields_updated": [], "source": "ai_bio"})

    fields_updated: list[str] = []
    contact_fields = ["given_name", "family_name", "title", "company"]
    for field in contact_fields:
        new_val = extracted.get(field)
        if not new_val:
            continue
        old_val = getattr(contact, field, None) or ""
        if field in ("given_name", "family_name") or not old_val:
            if new_val != old_val:
                setattr(contact, field, new_val)
                fields_updated.append(field)

    if "given_name" in fields_updated or "family_name" in fields_updated:
        new_full = " ".join(
            filter(None, [contact.given_name, contact.family_name])
        ) or contact.full_name
        if new_full != contact.full_name:
            contact.full_name = new_full
            if "full_name" not in fields_updated:
                fields_updated.append("full_name")

    if extracted.get("company"):
        from app.services.organization_service import auto_create_organization

        org = await auto_create_organization(contact, current_user.id, db)
        if org:
            org_updated = False
            if extracted.get("company_website") and not org.website:
                org.website = extracted["company_website"]
                org_updated = True
                fields_updated.append("company_website")
            if extracted.get("company_industry") and not org.industry:
                org.industry = extracted["company_industry"]
                org_updated = True
                fields_updated.append("company_industry")
            if extracted.get("company_location") and not org.location:
                org.location = extracted["company_location"]
                org_updated = True
                fields_updated.append("company_location")
            if org_updated and org.website and not org.logo_url:
                from app.services.organization_service import download_org_logo
                logo_url = await download_org_logo(org.website, org.id)
                if logo_url:
                    org.logo_url = logo_url

    if fields_updated:
        await db.flush()
        await db.refresh(contact)

    return envelope({"fields_updated": fields_updated, "source": "ai_bio"})


@router.post("/{contact_id}/promote", response_model=Envelope[dict])
async def promote_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Remove '2nd Tier' tag from a contact, promoting it to 1st Tier."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    tags = list(contact.tags or [])
    new_tags = [t for t in tags if t.lower() != "2nd tier"]
    if len(new_tags) == len(tags):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact is not a 2nd Tier contact",
        )

    contact.tags = new_tags
    await db.flush()
    return envelope({"promoted": True, "id": str(contact_id)})
