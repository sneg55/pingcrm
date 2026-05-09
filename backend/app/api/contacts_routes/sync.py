from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter

from app.api.contacts_routes.shared import (
    Contact,
    Depends,
    Envelope,
    HTTPException,
    Query,
    AsyncSession,
    User,
    envelope,
    get_current_user,
    get_db,
    select,
    status,
)
from app.schemas.responses import AvatarRefreshData, BioRefreshData, SyncStartedData
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])

_AVATAR_CHECK_TTL = 86400  # 24 hours
_EMAIL_SYNC_TTL = 3600  # 1 hour
_TELEGRAM_SYNC_TTL = 3600  # 1 hour
_TWITTER_SYNC_TTL = 3600  # 1 hour


@router.post("/sync/google", response_model=Envelope[SyncStartedData])
async def sync_google_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
    """Dispatch a background Google Contacts sync.

    Returns immediately. A notification is created when sync completes.
    """
    from app.models.google_account import GoogleAccount

    ga_result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    has_accounts = ga_result.scalars().first() is not None
    if not has_accounts and not current_user.google_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Google account connected. Complete Google OAuth first.",
        )

    from app.services.tasks import sync_google_contacts_for_user
    sync_google_contacts_for_user.delay(str(current_user.id))

    return envelope({"status": "started"})


@router.post("/sync/google-calendar", response_model=Envelope[SyncStartedData])
async def sync_google_calendar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
    """Dispatch a background Google Calendar sync.

    Returns immediately. A notification is created when sync completes.
    """
    from app.models.google_account import GoogleAccount

    ga_result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    has_accounts = ga_result.scalars().first() is not None
    if not has_accounts and not current_user.google_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Google account connected. Complete Google OAuth first.",
        )

    from app.services.tasks import sync_google_calendar_for_user
    sync_google_calendar_for_user.delay(str(current_user.id))

    return envelope({"status": "started"})


@router.post("/sync/gmail", response_model=Envelope[SyncStartedData])
async def sync_gmail(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
    """Dispatch a background Gmail thread sync.

    Returns immediately. A notification is created when sync completes.
    """
    if not current_user.google_refresh_token:
        from app.models.google_account import GoogleAccount
        ga_result = await db.execute(
            select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
        )
        if not ga_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No Google account connected. Complete Google OAuth first.",
            )

    from app.services.tasks import sync_gmail_for_user
    sync_gmail_for_user.delay(str(current_user.id))

    return envelope({"status": "started"})


@router.post("/sync/twitter", response_model=Envelope[SyncStartedData])
async def sync_twitter(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[SyncStartedData]:
    """Dispatch a background Twitter sync (DMs + mentions + bios).

    Returns immediately. A notification is created when sync completes.
    """
    if not current_user.twitter_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Twitter account not connected. Complete Twitter OAuth first.",
        )

    from app.services.tasks import sync_twitter_dms_for_user
    sync_twitter_dms_for_user.delay(str(current_user.id))

    return envelope({"status": "started"})


@router.post("/{contact_id}/refresh-bios", response_model=Envelope[BioRefreshData])
async def refresh_contact_bios(
    contact_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 24h rate limit (for manual refresh)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[BioRefreshData]:
    """Check for bio updates on Twitter and Telegram for a single contact.

    Rate-limited to once per 24 hours per contact (unless force=true).
    """
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    r = get_redis()
    cache_key = f"bio_check:{contact_id}"
    if not force and await r.exists(cache_key):
        return envelope({"skipped": True, "reason": "checked_recently"})

    from app.services.bio_refresh import refresh_contact_bios as _refresh_bios, _BIO_CHECK_TTL

    changes = await _refresh_bios(contact, current_user, db)

    await r.setex(cache_key, _BIO_CHECK_TTL, "1")
    return envelope(changes)


@router.post("/{contact_id}/refresh-avatar", response_model=Envelope[AvatarRefreshData])
async def refresh_contact_avatar(
    contact_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 24h rate limit (for manual refresh)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[AvatarRefreshData]:
    """Refresh a contact's avatar from Telegram or Twitter. Rate-limited to once per 24h."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    r = get_redis()
    cache_key = f"avatar_check:{contact_id}"
    if not force and await r.exists(cache_key):
        return envelope({"avatar_url": contact.avatar_url, "skipped": True, "reason": "checked_recently"})

    old_avatar = contact.avatar_url
    new_avatar = None

    # Try Telegram first
    if contact.telegram_username and current_user.telegram_session:
        try:
            from app.integrations.telegram import _make_client, _ensure_connected, _download_avatar
            client = _make_client(current_user.telegram_session)
            await _ensure_connected(client)
            try:
                username = (contact.telegram_username or "").lstrip("@").strip()
                if username:
                    entity = await client.get_input_entity(username)
                    avatar_path = await _download_avatar(client, entity, contact.id)
                    if avatar_path:
                        new_avatar = avatar_path
            finally:
                await client.disconnect()
        except Exception:
            logger.debug("Avatar refresh: Telegram failed for contact %s", contact_id)

    # Try Twitter if still no avatar
    if not new_avatar and contact.twitter_handle:
        try:
            from app.integrations.bird import fetch_user_profile_bird
            from app.integrations.twitter import download_twitter_avatar
            from app.services.bird_session import get_cookies
            handle = (contact.twitter_handle or "").lstrip("@").strip()
            if handle:
                cookies = get_cookies(current_user)
                if cookies is not None:
                    auth_token, ct0 = cookies
                    profile, _err = await fetch_user_profile_bird(
                        handle, auth_token=auth_token, ct0=ct0,
                    )
                    image_url = profile.get("profileImageUrl") or profile.get("profile_image_url")
                    if image_url:
                        avatar_path = await download_twitter_avatar(image_url, contact.id)
                        if avatar_path:
                            new_avatar = avatar_path
        except Exception:
            logger.debug("Avatar refresh: Twitter failed for contact %s", contact_id)

    changed = False
    if new_avatar and new_avatar != old_avatar:
        contact.avatar_url = new_avatar
        changed = True
        await db.flush()

    await r.setex(cache_key, _AVATAR_CHECK_TTL, "1")
    return envelope({"avatar_url": contact.avatar_url, "changed": changed})


@router.post("/{contact_id}/sync-emails", response_model=Envelope[dict])
async def sync_contact_emails(
    contact_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 1h rate limit (for manual refresh)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Search Gmail for threads involving this contact's emails and save as interactions.

    Rate-limited to once per hour per contact (unless force=true).
    """
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.emails:
        return envelope({"new_interactions": 0, "skipped": True, "reason": "no_emails"})

    if not current_user.google_refresh_token:
        return envelope({"new_interactions": 0, "skipped": True, "reason": "google_not_connected"})

    r = get_redis()
    cache_key = f"email_sync:{contact_id}"
    if not force and await r.exists(cache_key):
        return envelope({"new_interactions": 0, "skipped": True, "reason": "synced_recently"})

    from app.integrations.gmail import sync_contact_emails as _sync_emails

    new_count = await _sync_emails(current_user, contact, db)

    if new_count > 0:
        from app.services.follow_up_dismissal import dismiss_outdated_pending_suggestions
        await dismiss_outdated_pending_suggestions(db, [contact_id])
        await db.flush()

    await r.setex(cache_key, _EMAIL_SYNC_TTL, "1")
    return envelope({"new_interactions": new_count})


@router.post("/{contact_id}/sync-telegram", response_model=Envelope[dict])
async def sync_contact_telegram(
    contact_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 1h rate limit (for manual refresh)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Sync Telegram DMs for a single contact. Rate-limited to once per hour."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.telegram_username and not contact.telegram_user_id:
        return envelope({"new_interactions": 0, "skipped": True, "reason": "no_telegram"})

    if not current_user.telegram_session:
        return envelope({"new_interactions": 0, "skipped": True, "reason": "telegram_not_connected"})

    r = get_redis()
    cache_key = f"tg_msg_sync:{contact_id}"
    if not force and await r.exists(cache_key):
        return envelope({"new_interactions": 0, "skipped": True, "reason": "synced_recently"})

    from app.integrations.telegram import sync_telegram_contact_messages

    try:
        changes = await sync_telegram_contact_messages(current_user, contact, db)
    except ValueError as exc:
        # Telethon can't resolve entity for users we haven't DMed (2nd tier contacts)
        logger.warning("sync_contact_telegram: entity resolution failed for contact %s: %s", contact_id, exc)
        return envelope({"new_interactions": 0, "skipped": True, "reason": "entity_not_resolved"})

    # Auto-dismiss only when the contact's last_interaction_at is on/after
    # the suggestion's created_at — backfilled old messages must not kill
    # fresh suggestions.
    if changes.get("new_interactions", 0) > 0:
        from app.services.follow_up_dismissal import dismiss_outdated_pending_suggestions
        await dismiss_outdated_pending_suggestions(db, [contact_id])
        await db.flush()

    await r.setex(cache_key, _TELEGRAM_SYNC_TTL, "1")
    return envelope(changes)


@router.post("/{contact_id}/sync-twitter", response_model=Envelope[dict])
async def sync_contact_twitter(
    contact_id: uuid.UUID,
    force: bool = Query(False, description="Bypass 1h rate limit (for manual refresh)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[dict]:
    """Sync Twitter DMs for a single contact. Rate-limited to once per hour."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if not contact.twitter_handle and not contact.twitter_user_id:
        return envelope({"new_interactions": 0, "skipped": True, "reason": "no_twitter"})

    if not current_user.twitter_access_token:
        return envelope({"new_interactions": 0, "skipped": True, "reason": "twitter_not_connected"})

    r = get_redis()
    cache_key = f"tw_dm_sync:{contact_id}"
    if not force and await r.exists(cache_key):
        return envelope({"new_interactions": 0, "skipped": True, "reason": "synced_recently"})

    from app.integrations.twitter import sync_twitter_contact_dms

    changes = await sync_twitter_contact_dms(current_user, contact, db)

    if changes.get("new_interactions", 0) > 0:
        from app.services.follow_up_dismissal import dismiss_outdated_pending_suggestions
        await dismiss_outdated_pending_suggestions(db, [contact_id])
        await db.flush()

    await r.setex(cache_key, _TWITTER_SYNC_TTL, "1")
    return envelope(changes)


@router.post("/reconcile-last-interaction", response_model=Envelope)
async def reconcile_last_interaction(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope:
    """Reconcile last_interaction_at for all contacts from actual interaction data.

    Fixes stale values caused by sync bugs where last_interaction_at wasn't
    updated when interactions were created or skipped as duplicates.
    """
    from app.models.interaction import Interaction
    from sqlalchemy import func

    # Find the true max(occurred_at) per contact
    max_occurred = (
        select(
            Interaction.contact_id,
            func.max(Interaction.occurred_at).label("max_occurred"),
        )
        .where(Interaction.user_id == current_user.id)
        .group_by(Interaction.contact_id)
        .subquery()
    )

    # Get contacts where last_interaction_at is stale or null but interactions exist
    result = await db.execute(
        select(Contact, max_occurred.c.max_occurred)
        .join(max_occurred, Contact.id == max_occurred.c.contact_id)
        .where(
            Contact.user_id == current_user.id,
            (
                (Contact.last_interaction_at.is_(None))
                | (Contact.last_interaction_at < max_occurred.c.max_occurred)
            ),
        )
    )

    updated = 0
    for contact, max_occurred_at in result.all():
        contact.last_interaction_at = max_occurred_at
        updated += 1

    await db.flush()
    logger.info("Reconciled last_interaction_at for %d contacts (user %s)", updated, current_user.id)
    return envelope({"updated_count": updated})
