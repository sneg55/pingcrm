import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_current_user, hash_password, verify_password
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import client_ip, enforce_rate_limit
from app.models.user import User
from app.schemas.responses import (
    Envelope,
    TokenData,
    UserWithAccountsData,
)
from app.schemas.user import Token, UserCreate, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=Envelope[UserResponse], status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> Envelope[UserResponse]:
    if not settings.ALLOW_REGISTRATION:
        logger.warning(
            "registration attempt while registration is disabled",
            extra={"operation": "register", "client_ip": client_ip(request)},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled",
        )

    await enforce_rate_limit(
        request,
        bucket="register",
        limit=settings.REGISTER_RATE_LIMIT_ATTEMPTS,
        window_seconds=settings.REGISTER_RATE_LIMIT_WINDOW_SECONDS,
    )

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


REMEMBER_ME_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days


@router.post("/login", response_model=Envelope[TokenData])
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TokenData]:
    await enforce_rate_limit(
        request,
        bucket="login",
        limit=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
        window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )

    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check remember_me from form body (sent as extra form field)
    body = await request.form()
    remember_me = body.get("remember_me") == "true"
    expire_minutes = REMEMBER_ME_EXPIRE_MINUTES if remember_me else settings.ACCESS_TOKEN_EXPIRE_MINUTES

    access_token = create_access_token(
        data={"sub": str(user.id), "tv": user.token_version},
        expires_delta=timedelta(minutes=expire_minutes),
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


# ---------------------------------------------------------------------------
# Account management
# ---------------------------------------------------------------------------


from pydantic import Field as _Field


class ProfileUpdate(BaseModel):
    full_name: str | None = _Field(default=None, max_length=200)


@router.put("/me", response_model=Envelope[dict])
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


@router.post("/change-password", response_model=Envelope[dict])
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
    # Invalidate every token minted before this change. Without it a stolen
    # token stays valid for up to REMEMBER_ME_EXPIRE_MINUTES (30 days) and the
    # user has no way to evict an attacker by changing their password.
    current_user.token_version = (current_user.token_version or 0) + 1
    await db.flush()

    # Issue a replacement so the caller is not logged out by their own change.
    access_token = create_access_token(
        data={"sub": str(current_user.id), "tv": current_user.token_version},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "data": {"updated": True, "access_token": access_token, "token_type": "bearer"},
        "error": None,
    }


@router.delete("/me", response_model=Envelope[dict])
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete the authenticated user's account and all data."""
    await db.delete(current_user)
    await db.flush()
    return {"data": {"deleted": True}, "error": None}
