from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.google_account import GoogleAccount
from app.models.user import User


@dataclass(frozen=True)
class GoogleMailboxes:
    accounts: list[tuple[str, str]]
    own_emails: frozenset[str]


async def load_google_mailboxes(user: User, db: AsyncSession) -> GoogleMailboxes:
    result = await db.execute(
        select(GoogleAccount).where(GoogleAccount.user_id == user.id)
    )
    accounts = [(ga.email.lower(), ga.refresh_token) for ga in result.scalars().all()]
    if not accounts and user.google_refresh_token:
        accounts = [(user.email.lower(), user.google_refresh_token)]
    own_emails = frozenset({user.email.lower(), *(email for email, _ in accounts)})
    return GoogleMailboxes(accounts=accounts, own_emails=own_emails)
