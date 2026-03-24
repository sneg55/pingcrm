import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_current_user, get_current_user_optional, hash_password, verify_password
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.integrations.google_auth import build_oauth_url, exchange_code
from app.models.user import User
from app.schemas.responses import (
    DeletedData,
    Envelope,
    GoogleAccountData,
    OAuthUrlData,
    TokenData,
    UserWithAccountsData,
)
from app.schemas.user import Token, UserCreate, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_GOOGLE_STATE_TTL_SECONDS = 600  # 10 minutes


async def _store_google_state(state: str, user_id: str | None) -> None:
    r = get_redis()
    await r.setex(f"oauth_state:{state}", _GOOGLE_STATE_TTL_SECONDS, user_id or "__anonymous__")


async def _pop_google_state(state: str) -> str | None:
    r = get_redis()
    val = await r.getdel(f"oauth_state:{state}")
    return val  # None if not found/expired


@router.post("/register", response_model=Envelope[UserResponse], status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> Envelope[UserResponse]:
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return {"data": UserResponse.model_validate(user).model_dump(), "error": None}


@router.post("/login", response_model=Envelope[TokenData])
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TokenData]:
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Envelope(data=TokenData(access_token=access_token, token_type="bearer"))


@router.get("/me", response_model=Envelope[UserWithAccountsData])
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[UserWithAccountsData]:
    from app.models.google_account import GoogleAccount

    result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    google_accounts = [
        {"id": str(ga.id), "email": ga.email}
        for ga in result.scalars().all()
    ]

    # Self-heal: if linkedin_extension_paired_at is null but a claimed
    # pairing record exists, the timestamp was lost — restore it.
    if current_user.linkedin_extension_paired_at is None:
        from app.models.extension_pairing import ExtensionPairing
        pairing_result = await db.execute(
            select(ExtensionPairing.claimed_at).where(
                ExtensionPairing.user_id == current_user.id,
                ExtensionPairing.claimed_at.is_not(None),
            ).order_by(ExtensionPairing.claimed_at.desc()).limit(1)
        )
        claimed_at = pairing_result.scalar_one_or_none()
        if claimed_at:
            current_user.linkedin_extension_paired_at = claimed_at
            await db.flush()

    user_data = UserResponse.from_user(current_user).model_dump()
    user_data["google_accounts"] = google_accounts
    return {"data": user_data, "error": None}


@router.get("/google/accounts", response_model=Envelope[list[GoogleAccountData]])
async def list_google_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[list[GoogleAccountData]]:
    from app.models.google_account import GoogleAccount

    result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    accounts = [
        {"id": str(ga.id), "email": ga.email, "created_at": ga.created_at.isoformat()}
        for ga in result.scalars().all()
    ]
    return {"data": accounts, "error": None}


@router.delete("/google/accounts/{account_id}", response_model=Envelope[DeletedData])
async def remove_google_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[DeletedData]:
    import uuid as _uuid
    from app.models.google_account import GoogleAccount

    try:
        aid = _uuid.UUID(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account ID")

    result = await db.execute(
        select(GoogleAccount).where(
            GoogleAccount.id == aid,
            GoogleAccount.user_id == current_user.id,
        )
    )
    ga = result.scalar_one_or_none()
    if not ga:
        raise HTTPException(status_code=404, detail="Google account not found")

    await db.delete(ga)
    return {"data": {"id": account_id, "deleted": True}, "error": None}


@router.get("/google/url", response_model=Envelope[OAuthUrlData])
async def google_oauth_url(
    current_user: User = Depends(get_current_user),
) -> Envelope[OAuthUrlData]:
    """Return the Google OAuth consent screen URL."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env",
        )
    url, state = build_oauth_url(redirect_uri=settings.GOOGLE_REDIRECT_URI)
    await _store_google_state(state, str(current_user.id))
    return {"data": {"url": url, "state": state}, "error": None}


class GoogleCallbackRequest(BaseModel):
    code: str
    state: str | None = None


@router.post("/google/callback", response_model=Envelope[TokenData])
async def google_callback(
    payload: GoogleCallbackRequest,
    db: AsyncSession = Depends(get_db),
    caller: User | None = Depends(get_current_user_optional),
) -> Envelope[TokenData]:
    """Exchange a Google authorization code for a JWT access token.

    - Validates the ``state`` parameter against the server-side nonce store
      to prevent CSRF attacks.
    - If the state was created by an authenticated user (connect-account flow),
      verifies that the current authenticated user matches the stored user_id.
    - If a user with the returned email already exists, update their refresh token.
    - Otherwise create a new account from the Google profile information.
    """
    if not payload.state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state parameter",
        )
    popped = await _pop_google_state(payload.state)
    if popped is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state parameter",
        )

    # Task 8.1: Enforce state ownership for "connect account" flows.
    # When a logged-in user initiated the OAuth flow via GET /google/url,
    # the state was bound to their user_id. If the callback arrives with a
    # different (or absent) authenticated user, reject the request to prevent
    # account-binding hijack via a leaked state token.
    if popped != "__anonymous__":
        if caller is None or str(caller.id) != popped:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user does not match the OAuth state",
            )

    try:
        tokens = exchange_code(payload.code)
    except Exception as exc:
        logger.error("Google code exchange failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange Google authorization code",
        )

    # Verify the id_token and extract the user profile.
    try:
        id_info = google_id_token.verify_oauth2_token(
            tokens["id_token"],
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        logger.error("Google ID token verification failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Google ID token",
        )

    email: str = id_info.get("email", "")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account does not provide an email address",
        )

    from app.models.google_account import GoogleAccount

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        import secrets

        full_name: str | None = id_info.get("name")
        user = User(
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            full_name=full_name,
            google_refresh_token=tokens.get("refresh_token"),
        )
        db.add(user)
        await db.flush()
    else:
        if tokens.get("refresh_token"):
            user.google_refresh_token = tokens["refresh_token"]

    # Upsert GoogleAccount entry for this email
    google_email: str = id_info.get("email", email)
    if tokens.get("refresh_token"):
        ga_result = await db.execute(
            select(GoogleAccount).where(
                GoogleAccount.user_id == user.id,
                GoogleAccount.email == google_email,
            )
        )
        ga = ga_result.scalar_one_or_none()
        if ga:
            ga.refresh_token = tokens["refresh_token"]
        else:
            db.add(GoogleAccount(
                user_id=user.id,
                email=google_email,
                refresh_token=tokens["refresh_token"],
            ))

    from app.models.notification import Notification

    db.add(Notification(
        user_id=user.id,
        notification_type="sync",
        title="Google account connected",
        body=f"Connected {google_email}",
        link="/settings",
    ))

    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"data": {"access_token": access_token, "token_type": "bearer"}, "error": None}


# ---------------------------------------------------------------------------
# Account management
# ---------------------------------------------------------------------------


from pydantic import Field as _Field


class ProfileUpdate(BaseModel):
    full_name: str | None = _Field(default=None, max_length=200)


@router.put("/me")
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update the authenticated user's profile."""
    if body.full_name is not None:
        current_user.full_name = body.full_name
    await db.flush()
    return {"data": {"updated": True}, "error": None}


class PasswordChange(BaseModel):
    current_password: str = _Field(max_length=128)
    new_password: str = _Field(max_length=128)


@router.post("/change-password")
async def change_password(
    body: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change the authenticated user's password."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters")
    current_user.hashed_password = hash_password(body.new_password)
    await db.flush()
    return {"data": {"updated": True}, "error": None}


@router.delete("/me")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete the authenticated user's account and all data."""
    await db.delete(current_user)
    await db.flush()
    return {"data": {"deleted": True}, "error": None}
