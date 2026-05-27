"""Unit tests for app.services.task_jobs.google.

These tests exercise the lifted ``_sync_google_contacts`` /
``_sync_google_calendar`` coroutines against a real Postgres test database
(via the conftest ``db`` fixture). The external integration boundary
(``refresh_access_token`` / ``fetch_google_contacts`` / ``sync_calendar_events``)
is mocked at the ``task_jobs.google`` module level so we cover the
orchestration logic — credential lookup, contact upsert, archival, scoring,
notifications, error paths — without hitting Google.

The Celery entrypoint wrappers are tested separately by invoking them via
``.apply()`` so retries surface as ``celery.exceptions.Retry`` exceptions
instead of dispatching to a broker.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from celery.exceptions import Retry
from google.auth.exceptions import RefreshError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.google_account import GoogleAccount
from app.models.notification import Notification
from app.models.user import User
from app.services.task_jobs.google import (
    _collect_google_calendar_user_ids,
    _sync_google_calendar,
    _sync_google_contacts,
    sync_google_calendar_all,
    sync_google_calendar_for_user,
    sync_google_contacts_for_user,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gc_fields(**overrides) -> dict:
    """Build a payload shaped like one item returned by fetch_google_contacts."""
    defaults = {
        "resource_name": f"people/{uuid.uuid4().hex[:12]}",
        "full_name": "Alice Example",
        "given_name": "Alice",
        "family_name": "Example",
        "emails": ["alice@example.com"],
        "phones": [],
        "company": None,
        "title": None,
    }
    defaults.update(overrides)
    return defaults


async def _notifications_for(db: AsyncSession, user_id: uuid.UUID) -> list[Notification]:
    r = await db.execute(select(Notification).where(Notification.user_id == user_id))
    return list(r.scalars().all())


# ---------------------------------------------------------------------------
# _sync_google_contacts — early exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_google_contacts_user_not_found(db: AsyncSession):
    result = await _sync_google_contacts(db, uuid.uuid4())
    assert result == {"status": "user_not_found"}


@pytest.mark.asyncio
async def test_sync_google_contacts_not_connected(db: AsyncSession, test_user: User):
    result = await _sync_google_contacts(db, test_user.id)
    assert result == {"status": "not_connected"}
    # No tokens means we never even reached the notification block
    assert await _notifications_for(db, test_user.id) == []


# ---------------------------------------------------------------------------
# _sync_google_contacts — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creates_new_contact_via_legacy_user_token(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "legacy-refresh"
    await db.commit()

    payload = _gc_fields(full_name="Carol Smith", emails=["carol@example.com"])
    with (
        patch(
            "app.services.task_jobs.google.refresh_access_token",
            return_value="access-token",
        ) as mock_refresh,
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[payload],
        ) as mock_fetch,
    ):
        result = await _sync_google_contacts(db, test_user.id)

    assert result["status"] == "ok"
    assert result["created"] == 1
    assert result["updated"] == 0
    assert result["errors"] == 0
    mock_refresh.assert_called_once_with("legacy-refresh")
    mock_fetch.assert_called_once_with("access-token")

    r = await db.execute(select(Contact).where(Contact.user_id == test_user.id))
    contacts = list(r.scalars().all())
    assert len(contacts) == 1
    assert contacts[0].full_name == "Carol Smith"
    assert contacts[0].emails == ["carol@example.com"]
    assert contacts[0].source == "google"
    assert contacts[0].google_resource_name == payload["resource_name"]

    notifs = await _notifications_for(db, test_user.id)
    assert len(notifs) == 1
    assert notifs[0].notification_type == "sync"
    assert "1 new" in notifs[0].body


@pytest.mark.asyncio
async def test_uses_google_account_rows_when_present(
    db: AsyncSession, test_user: User
):
    # When a GoogleAccount row exists, the legacy user.google_refresh_token is
    # ignored — only the per-account refresh tokens are used.
    test_user.google_refresh_token = "should-not-be-used"
    db.add(GoogleAccount(
        user_id=test_user.id,
        email="primary@example.com",
        refresh_token="ga-refresh-token",
    ))
    await db.commit()

    with (
        patch(
            "app.services.task_jobs.google.refresh_access_token",
            return_value="tok",
        ) as mock_refresh,
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[_gc_fields()],
        ),
    ):
        await _sync_google_contacts(db, test_user.id)

    mock_refresh.assert_called_once_with("ga-refresh-token")


@pytest.mark.asyncio
async def test_merges_existing_contact_by_resource_name(
    db: AsyncSession, test_user: User
):
    """An existing contact with the same google_resource_name must be updated
    in place, never duplicated."""
    test_user.google_refresh_token = "tok"
    resource_name = "people/abc123"
    existing = Contact(
        user_id=test_user.id,
        full_name=None,  # missing → should be filled
        given_name=None,
        family_name=None,
        emails=["old@example.com"],
        phones=["+15551111"],
        google_resource_name=resource_name,
        source="google",
    )
    db.add(existing)
    await db.commit()

    payload = _gc_fields(
        resource_name=resource_name,
        full_name="Real Name",
        given_name="Real",
        family_name="Name",
        emails=["new@example.com"],
        phones=["+15552222", "+15551111"],  # second is dup → not re-added
        company="Acme",
        title="VP",
    )
    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[payload],
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    assert result["created"] == 0
    assert result["updated"] == 1

    await db.refresh(existing)
    assert existing.full_name == "Real Name"
    assert existing.given_name == "Real"
    assert existing.family_name == "Name"
    assert existing.company == "Acme"
    assert existing.title == "VP"
    assert existing.phones == ["+15551111", "+15552222"]


@pytest.mark.asyncio
async def test_does_not_overwrite_populated_fields_on_merge(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    resource_name = "people/keep-mine"
    existing = Contact(
        user_id=test_user.id,
        full_name="Kept Name",
        given_name="Kept",
        family_name="Name",
        emails=["x@example.com"],
        company="Existing Co",
        title="Existing Title",
        google_resource_name=resource_name,
        source="google",
    )
    db.add(existing)
    await db.commit()

    payload = _gc_fields(
        resource_name=resource_name,
        full_name="Other Name",
        given_name="Other",
        family_name="Surname",
        company="Other Co",
        title="Other Title",
    )
    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[payload],
        ),
    ):
        await _sync_google_contacts(db, test_user.id)

    await db.refresh(existing)
    assert existing.full_name == "Kept Name"
    assert existing.company == "Existing Co"
    assert existing.title == "Existing Title"


@pytest.mark.asyncio
async def test_merges_existing_contact_by_email_when_no_resource_match(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    existing = Contact(
        user_id=test_user.id,
        full_name="Match By Email",
        emails=["Match.By@example.com"],  # case differs from payload
        google_resource_name=None,
        source="manual",
    )
    db.add(existing)
    await db.commit()

    payload = _gc_fields(
        resource_name="people/new-resource",
        full_name="Other",  # already-populated full_name → not changed
        emails=["match.by@example.com"],
    )
    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[payload],
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    assert result["created"] == 0
    assert result["updated"] == 1
    await db.refresh(existing)
    # resource_name must be stamped onto the previously un-stamped contact
    assert existing.google_resource_name == "people/new-resource"
    # And no duplicate contact was created
    r = await db.execute(select(Contact).where(Contact.user_id == test_user.id))
    assert len(list(r.scalars().all())) == 1


@pytest.mark.asyncio
async def test_archives_contacts_missing_from_google(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    still_present = Contact(
        user_id=test_user.id,
        full_name="Active",
        google_resource_name="people/still-here",
        source="google",
        priority_level="medium",
    )
    deleted_in_google = Contact(
        user_id=test_user.id,
        full_name="Gone",
        google_resource_name="people/deleted-upstream",
        source="google",
        priority_level="medium",
    )
    db.add_all([still_present, deleted_in_google])
    await db.commit()

    payload = _gc_fields(resource_name="people/still-here", emails=[])
    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[payload],
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    assert result["archived"] == 1
    await db.refresh(deleted_in_google)
    await db.refresh(still_present)
    assert deleted_in_google.priority_level == "archived"
    assert still_present.priority_level == "medium"


@pytest.mark.asyncio
async def test_no_archival_when_fetch_returns_nothing(
    db: AsyncSession, test_user: User
):
    """An empty Google response must NOT mass-archive everything — that'd be a
    data-loss event if Google times out mid-sync."""
    test_user.google_refresh_token = "tok"
    db.add(Contact(
        user_id=test_user.id,
        full_name="Existing",
        google_resource_name="people/x",
        source="google",
        priority_level="medium",
    ))
    await db.commit()

    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[],
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    assert result["archived"] == 0
    r = await db.execute(select(Contact).where(Contact.user_id == test_user.id))
    survivors = list(r.scalars().all())
    assert survivors[0].priority_level == "medium"


@pytest.mark.asyncio
async def test_name_org_pipe_pattern_splits_company(
    db: AsyncSession, test_user: User
):
    """"Name | Company" gets parsed into a separate company field; existing
    behavior leaves the raw combined string in full_name on new inserts."""
    test_user.google_refresh_token = "tok"
    payload = _gc_fields(
        full_name="Dana Brown | Brownworks",
        given_name=None,
        family_name=None,
        company=None,
        emails=["dana@brownworks.co"],
    )
    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[payload],
        ),
    ):
        await _sync_google_contacts(db, test_user.id)

    r = await db.execute(select(Contact).where(Contact.user_id == test_user.id))
    contact = r.scalar_one()
    # Existing behavior: raw_name (pre-split) flows into full_name on insert.
    # Codifying it so future refactors don't silently change this.
    assert contact.full_name == "Dana Brown | Brownworks"
    assert contact.company == "Brownworks"


# ---------------------------------------------------------------------------
# _sync_google_contacts — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_error_creates_reauth_notification_and_continues(
    db: AsyncSession, test_user: User
):
    """One account dies with RefreshError, the next account still syncs."""
    test_user.google_refresh_token = None  # force per-account path
    db.add_all([
        GoogleAccount(user_id=test_user.id, email="dead@example.com", refresh_token="dead"),
        GoogleAccount(user_id=test_user.id, email="alive@example.com", refresh_token="alive"),
    ])
    await db.commit()

    def fake_refresh(token: str) -> str:
        if token == "dead":
            raise RefreshError("invalid_grant")
        return "fresh-token"

    with (
        patch("app.services.task_jobs.google.refresh_access_token", side_effect=fake_refresh),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[_gc_fields(emails=["alive@example.com"])],
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    assert result["created"] == 1
    assert result["errors"] == 1

    notifs = await _notifications_for(db, test_user.id)
    # 1 error notification for "dead", 1 sync-summary at the end
    titles = sorted(n.title for n in notifs)
    assert "Google Contacts sync completed" in titles
    assert any("re-authentication needed" in t for t in titles)


@pytest.mark.asyncio
async def test_generic_fetch_error_recorded_but_no_reauth_notification(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    await db.commit()

    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            side_effect=RuntimeError("rate limited"),
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    assert result["errors"] == 1
    assert result["created"] == 0
    notifs = await _notifications_for(db, test_user.id)
    # Only the end-of-sync summary; no re-auth notification for generic errors
    assert len(notifs) == 1
    assert notifs[0].notification_type == "sync"
    assert "1 errors" in notifs[0].body


@pytest.mark.asyncio
async def test_score_recalc_invoked_when_changes_occur(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    # A contact with last_interaction_at set → eligible for rescore
    db.add(Contact(
        user_id=test_user.id,
        full_name="Score Me",
        emails=["score@example.com"],
        last_interaction_at=datetime.now(UTC) - timedelta(days=3),
        source="manual",
    ))
    await db.commit()

    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[_gc_fields()],
        ),
        patch(
            "app.services.task_jobs.google.calculate_score",
            new=AsyncMock(return_value=42),
        ) as mock_score,
    ):
        await _sync_google_contacts(db, test_user.id)

    assert mock_score.await_count >= 1


@pytest.mark.asyncio
async def test_blank_emails_are_skipped_during_fallback_lookup(
    db: AsyncSession, test_user: User
):
    """A payload email that normalize_email() rejects (e.g., empty string)
    must be skipped without aborting the fallback loop."""
    test_user.google_refresh_token = "tok"
    db.add(Contact(
        user_id=test_user.id,
        full_name="Existing",
        emails=["match@example.com"],
        google_resource_name=None,
        source="manual",
    ))
    await db.commit()

    payload = _gc_fields(
        resource_name="people/blanks",
        emails=["", "   ", "match@example.com"],
    )
    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[payload],
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    # Blank emails skipped; the real email still matched the existing contact
    assert result["created"] == 0
    assert result["updated"] == 1


@pytest.mark.asyncio
async def test_per_contact_upsert_exception_recorded_in_errors(
    db: AsyncSession, test_user: User
):
    """If a single contact blows up mid-loop, the loop continues and the error
    is recorded with a name/email hint rather than crashing the whole sync."""
    test_user.google_refresh_token = "tok"
    await db.commit()

    good = _gc_fields(full_name="Good One", emails=["good@example.com"])
    bad = _gc_fields(full_name="Bad One", emails=["bad@example.com"])

    real_normalize = __import__(
        "app.services.task_jobs.google", fromlist=["normalize_email"]
    ).normalize_email

    def boom_for_bad(email):
        if email == "bad@example.com":
            raise RuntimeError("normalize blew up")
        return real_normalize(email)

    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[good, bad],
        ),
        patch(
            "app.services.task_jobs.google.normalize_email",
            side_effect=boom_for_bad,
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    assert result["created"] == 1
    assert result["errors"] == 1


@pytest.mark.asyncio
async def test_score_recalc_failure_is_logged_not_fatal(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    db.add(Contact(
        user_id=test_user.id,
        full_name="Scored",
        emails=["s@example.com"],
        last_interaction_at=datetime.now(UTC) - timedelta(days=1),
        source="manual",
    ))
    await db.commit()

    with (
        patch("app.services.task_jobs.google.refresh_access_token", return_value="a"),
        patch(
            "app.services.task_jobs.google.fetch_google_contacts",
            return_value=[_gc_fields()],
        ),
        patch(
            "app.services.task_jobs.google.calculate_score",
            new=AsyncMock(side_effect=RuntimeError("scoring broke")),
        ),
    ):
        result = await _sync_google_contacts(db, test_user.id)

    # Sync completes despite scoring failure
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# _sync_google_calendar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_user_not_found(db: AsyncSession):
    assert await _sync_google_calendar(db, uuid.uuid4()) == {"status": "user_not_found"}


@pytest.mark.asyncio
async def test_calendar_not_connected(db: AsyncSession, test_user: User):
    assert await _sync_google_calendar(db, test_user.id) == {"status": "not_connected"}


@pytest.mark.asyncio
async def test_calendar_uses_legacy_user_token_when_no_accounts(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "user-tok"
    await db.commit()

    fake_result = {"new_contacts": 2, "new_interactions": 5, "events_processed": 9}
    with patch(
        "app.services.task_jobs.google.sync_calendar_events",
        new=AsyncMock(return_value=fake_result),
    ) as mock_sync:
        result = await _sync_google_calendar(db, test_user.id)

    assert result == {"status": "ok", **fake_result}
    mock_sync.assert_awaited_once()
    notifs = await _notifications_for(db, test_user.id)
    assert len(notifs) == 1
    assert "2 new contacts" in notifs[0].body
    assert "5 meetings" in notifs[0].body


@pytest.mark.asyncio
async def test_calendar_iterates_multiple_accounts_and_sums_counts(
    db: AsyncSession, test_user: User
):
    db.add_all([
        GoogleAccount(user_id=test_user.id, email="a@x.com", refresh_token="a"),
        GoogleAccount(user_id=test_user.id, email="b@x.com", refresh_token="b"),
    ])
    await db.commit()

    seen_tokens: list[str] = []

    async def fake_sync(user, db):  # noqa: ARG001
        seen_tokens.append(user.google_refresh_token)
        return {"new_contacts": 1, "new_interactions": 2, "events_processed": 3}

    with patch(
        "app.services.task_jobs.google.sync_calendar_events",
        new=AsyncMock(side_effect=fake_sync),
    ):
        result = await _sync_google_calendar(db, test_user.id)

    assert sorted(seen_tokens) == ["a", "b"]
    assert result["new_contacts"] == 2
    assert result["new_interactions"] == 4
    assert result["events_processed"] == 6


@pytest.mark.asyncio
async def test_calendar_refresh_error_per_account_writes_reauth_notification(
    db: AsyncSession, test_user: User
):
    db.add(GoogleAccount(
        user_id=test_user.id, email="dead@example.com", refresh_token="dead",
    ))
    await db.commit()

    async def fake_sync(user, db):  # noqa: ARG001
        raise RefreshError("invalid_grant")

    with patch(
        "app.services.task_jobs.google.sync_calendar_events",
        new=AsyncMock(side_effect=fake_sync),
    ):
        await _sync_google_calendar(db, test_user.id)

    notifs = await _notifications_for(db, test_user.id)
    titles = [n.title for n in notifs]
    assert any("re-authentication needed" in t for t in titles)


@pytest.mark.asyncio
async def test_calendar_unexpected_exception_swallowed_per_account(
    db: AsyncSession, test_user: User
):
    """A generic exception in one account must not abort the whole sync.
    Other accounts (none here) would still proceed; the final summary
    notification must still post."""
    db.add(GoogleAccount(
        user_id=test_user.id, email="boom@x.com", refresh_token="boom",
    ))
    await db.commit()

    async def fake_sync(user, db):  # noqa: ARG001
        raise RuntimeError("calendar API exploded")

    with patch(
        "app.services.task_jobs.google.sync_calendar_events",
        new=AsyncMock(side_effect=fake_sync),
    ):
        result = await _sync_google_calendar(db, test_user.id)

    assert result["status"] == "ok"
    assert result["events_processed"] == 0
    notifs = await _notifications_for(db, test_user.id)
    # Summary fires; no reauth notification for non-RefreshError
    assert len(notifs) == 1
    assert notifs[0].title == "Google Calendar sync completed"


@pytest.mark.asyncio
async def test_calendar_no_events_summary_message(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    await db.commit()

    with patch(
        "app.services.task_jobs.google.sync_calendar_events",
        new=AsyncMock(return_value={"new_contacts": 0, "new_interactions": 0, "events_processed": 0}),
    ):
        await _sync_google_calendar(db, test_user.id)

    notif = (await _notifications_for(db, test_user.id))[0]
    assert notif.body == "No new events"


@pytest.mark.asyncio
async def test_calendar_score_recalc_failure_is_logged_not_fatal(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    db.add(Contact(
        user_id=test_user.id,
        full_name="Scored",
        emails=["s@example.com"],
        last_interaction_at=datetime.now(UTC) - timedelta(days=1),
        source="manual",
    ))
    await db.commit()

    with (
        patch(
            "app.services.task_jobs.google.sync_calendar_events",
            new=AsyncMock(return_value={"new_contacts": 1, "new_interactions": 2, "events_processed": 3}),
        ),
        patch(
            "app.services.task_jobs.google.calculate_score",
            new=AsyncMock(side_effect=RuntimeError("scoring broke")),
        ),
    ):
        result = await _sync_google_calendar(db, test_user.id)

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_calendar_legacy_token_refresh_error_writes_notification(
    db: AsyncSession, test_user: User
):
    test_user.google_refresh_token = "tok"
    await db.commit()

    with patch(
        "app.services.task_jobs.google.sync_calendar_events",
        new=AsyncMock(side_effect=RefreshError("expired")),
    ):
        await _sync_google_calendar(db, test_user.id)

    titles = [n.title for n in await _notifications_for(db, test_user.id)]
    assert any("re-authentication needed" in t for t in titles)


# ---------------------------------------------------------------------------
# _collect_google_calendar_user_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_user_ids_returns_only_users_with_refresh_token(
    db: AsyncSession, test_user: User, user_factory
):
    with_token = await user_factory(google_refresh_token="tok")
    await user_factory(google_refresh_token=None)
    # test_user also has no token by default

    ids = await _collect_google_calendar_user_ids(db)
    assert str(with_token.id) in ids
    assert str(test_user.id) not in ids


# ---------------------------------------------------------------------------
# Celery wrappers — argument validation + retry plumbing
# ---------------------------------------------------------------------------


def test_contacts_for_user_returns_sentinel_on_invalid_uuid():
    result = sync_google_contacts_for_user.apply(args=["not-a-uuid"]).get()
    assert result == {"status": "invalid_user_id"}


def test_calendar_for_user_returns_sentinel_on_invalid_uuid():
    result = sync_google_calendar_for_user.apply(args=["not-a-uuid"]).get()
    assert result == {"status": "invalid_user_id"}


def test_contacts_for_user_retries_on_failure_and_notifies_when_exhausted():
    """When the impl raises, the wrapper logs, calls self.retry(), and once
    retries are exhausted dispatches notify_sync_failure exactly once."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.google._sync_google_contacts",
            new=AsyncMock(side_effect=RuntimeError("nope")),
        ),
        patch(
            "app.services.task_jobs.google.task_session",
        ) as mock_session,
        patch(
            "app.services.task_jobs.google.notify_sync_failure",
        ) as mock_notify,
    ):
        # task_session() is an async context manager — replace it with one that
        # yields a dummy object; the inner impl is fully mocked anyway.
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        with pytest.raises(Retry):
            sync_google_contacts_for_user.apply(args=[uid], throw=True).get()

    # On the first retry attempt, notify shouldn't fire yet
    assert mock_notify.delay.call_count == 0


def test_contacts_for_user_notifies_when_retries_exhausted():
    """On the final retry attempt, notify_sync_failure.delay fires exactly once
    with the 'Google Contacts' label so the user sees the failure in-app."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.google._sync_google_contacts",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("app.services.task_jobs.google.task_session") as mock_session,
        patch("app.services.task_jobs.google.notify_sync_failure") as mock_notify,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        sync_google_contacts_for_user.apply(
            args=[uid],
            retries=sync_google_contacts_for_user.max_retries,
        )

    mock_notify.delay.assert_called_once()
    label = mock_notify.delay.call_args.args[1]
    assert label == "Google Contacts"


def test_calendar_for_user_runs_wrapper_and_returns_impl_result():
    """Cover the calendar Celery wrapper's _runner + _run path, not just the
    invalid-UUID early exit."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.google._sync_google_calendar",
            new=AsyncMock(return_value={"status": "ok", "new_contacts": 1, "new_interactions": 2, "events_processed": 3}),
        ),
        patch("app.services.task_jobs.google.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = sync_google_calendar_for_user.apply(args=[uid]).get()

    assert result["status"] == "ok"
    assert result["new_contacts"] == 1


def test_calendar_for_user_notifies_when_retries_exhausted():
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.google._sync_google_calendar",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("app.services.task_jobs.google.task_session") as mock_session,
        patch("app.services.task_jobs.google.notify_sync_failure") as mock_notify,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        sync_google_calendar_for_user.apply(
            args=[uid],
            retries=sync_google_calendar_for_user.max_retries,
        )

    mock_notify.delay.assert_called_once()
    assert mock_notify.delay.call_args.args[1] == "Google Calendar"


def test_calendar_all_enqueues_one_task_per_user_id():
    fake_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    with (
        patch(
            "app.services.task_jobs.google._collect_google_calendar_user_ids",
            new=AsyncMock(return_value=fake_ids),
        ),
        patch(
            "app.services.task_jobs.google.task_session",
        ) as mock_session,
        patch(
            "app.services.task_jobs.google.sync_google_calendar_for_user.delay",
        ) as mock_delay,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = sync_google_calendar_all()

    assert result == {"queued": 2}
    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(fake_ids[0])
    mock_delay.assert_any_call(fake_ids[1])
