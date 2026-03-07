from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_current_user, hash_password, verify_password
from app.core.config import settings
from app.core.database import get_db
from app.integrations.google_auth import build_oauth_url, exchange_code
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
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


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
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
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=dict)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.models.google_account import GoogleAccount

    result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    google_accounts = [
        {"id": str(ga.id), "email": ga.email}
        for ga in result.scalars().all()
    ]
    user_data = UserResponse.from_user(current_user).model_dump()
    user_data["google_accounts"] = google_accounts
    return {"data": user_data, "error": None}


@router.get("/google/accounts", response_model=dict)
async def list_google_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.models.google_account import GoogleAccount

    result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == current_user.id)
    )
    accounts = [
        {"id": str(ga.id), "email": ga.email, "created_at": ga.created_at.isoformat()}
        for ga in result.scalars().all()
    ]
    return {"data": accounts, "error": None}


@router.delete("/google/accounts/{account_id}", response_model=dict)
async def remove_google_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
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
    return {"data": {"deleted": True}, "error": None}


@router.get("/google/url", response_model=dict)
async def google_oauth_url(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the Google OAuth consent screen URL."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env",
        )
    url, state = build_oauth_url(redirect_uri=settings.GOOGLE_REDIRECT_URI)
    return {"data": {"url": url, "state": state}, "error": None}


class GoogleCallbackRequest(BaseModel):
    code: str


@router.post("/google/callback", response_model=dict)
async def google_callback(
    payload: GoogleCallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Exchange a Google authorization code for a JWT access token.

    - If a user with the returned email already exists, update their refresh token.
    - Otherwise create a new account from the Google profile information.
    """
    try:
        tokens = exchange_code(payload.code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange Google authorization code: {exc}",
        )

    # Verify the id_token and extract the user profile.
    try:
        id_info = google_id_token.verify_oauth2_token(
            tokens["id_token"],
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Google ID token: {exc}",
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
