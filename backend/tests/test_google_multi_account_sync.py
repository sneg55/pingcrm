from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.gmail import sync_gmail_for_user
from app.integrations.google_calendar import sync_calendar_events
from app.models.contact import Contact
from app.models.google_account import GoogleAccount
from app.models.interaction import Interaction
from app.models.user import User


def _thread(thread_id: str, from_addr: str, to_addr: str, rfc_id: str | None = None) -> dict:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    extra_headers = [{"name": "Message-ID", "value": rfc_id}] if rfc_id else []
    return {
        "id": thread_id,
        "messages": [
            {
                "id": f"{thread_id}_m1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": from_addr},
                        {"name": "To", "value": to_addr},
                        {"name": "Subject", "value": "Hello"},
                        *extra_headers,
                    ],
                },
                "internalDate": str(now_ms),
                "snippet": f"body of {thread_id}",
            }
        ],
    }


def _gmail_service(threads: list[dict]) -> MagicMock:
    service = MagicMock()
    api = service.users.return_value.threads.return_value
    api.list.return_value.execute.return_value = {"threads": [{"id": t["id"]} for t in threads]}
    by_id = {t["id"]: t for t in threads}

    def get_thread(**kwargs):
        call = MagicMock()
        call.execute.return_value = by_id[kwargs["id"]]
        return call

    api.get.side_effect = get_thread
    return service


async def _make_user(db: AsyncSession, user: User, linked: list[tuple[str, str]], legacy_token: str | None) -> User:
    user.email = "a@example.com"
    user.google_refresh_token = legacy_token
    db.add(user)
    for email, token in linked:
        db.add(GoogleAccount(user_id=user.id, email=email, refresh_token=token))
    await db.commit()
    await db.refresh(user)
    return user


async def _contact(db: AsyncSession, user: User, email: str, name: str) -> Contact:
    contact = Contact(user_id=user.id, full_name=name, emails=[email])
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@pytest.mark.asyncio
async def test_gmail_outbound_from_linked_account_is_outbound_to_counterpart(db: AsyncSession, test_user: User):
    user = await _make_user(db, test_user, [("g@gmail.com", "tok-g")], "tok-g")
    bob = await _contact(db, user, "bob@x.com", "Bob")
    own_gmail = await _contact(db, user, "g@gmail.com", "Self Gmail")
    own_primary = await _contact(db, user, "a@example.com", "Self Primary")
    service = _gmail_service([_thread("t1", "g@gmail.com", "bob@x.com")])

    with patch("app.integrations.gmail._build_gmail_service", return_value=service):
        count = await sync_gmail_for_user(user, db)

    assert count == 1
    rows = (await db.execute(select(Interaction))).scalars().all()
    assert [(r.contact_id, r.direction) for r in rows] == [(bob.id, "outbound")]
    assert own_gmail.id not in {r.contact_id for r in rows}
    assert own_primary.id not in {r.contact_id for r in rows}
    contacts = (await db.execute(select(Contact))).scalars().all()
    assert {e for c in contacts for e in (c.emails or [])} == {"bob@x.com", "g@gmail.com", "a@example.com"}


@pytest.mark.asyncio
async def test_gmail_mail_between_own_mailboxes_matches_no_contact(db: AsyncSession, test_user: User):
    user = await _make_user(
        db, test_user, [("g@gmail.com", "tok-g"), ("h@gmail.com", "tok-h")], "tok-h"
    )
    await _contact(db, user, "g@gmail.com", "Self G")
    await _contact(db, user, "h@gmail.com", "Self H")
    service = _gmail_service([_thread("t1", "g@gmail.com", "h@gmail.com")])

    with patch("app.integrations.gmail._build_gmail_service", return_value=service):
        count = await sync_gmail_for_user(user, db)

    assert count == 0
    assert (await db.execute(select(Interaction))).scalars().all() == []


@pytest.mark.asyncio
async def test_gmail_syncs_every_linked_account(db: AsyncSession, test_user: User):
    user = await _make_user(
        db, test_user, [("g@gmail.com", "tok-g"), ("h@gmail.com", "tok-h")], "tok-h"
    )
    await _contact(db, user, "bob@x.com", "Bob")
    await _contact(db, user, "carol@x.com", "Carol")
    services = {
        "tok-g": _gmail_service([_thread("tg", "g@gmail.com", "bob@x.com")]),
        "tok-h": _gmail_service([_thread("th", "carol@x.com", "h@gmail.com")]),
    }

    with patch("app.integrations.gmail._build_gmail_service", side_effect=lambda tok: services[tok]) as build:
        count = await sync_gmail_for_user(user, db)

    assert sorted(c.args[0] for c in build.call_args_list) == ["tok-g", "tok-h"]
    assert count == 2


@pytest.mark.asyncio
async def test_gmail_one_failing_account_does_not_stop_the_next(db: AsyncSession, test_user: User):
    user = await _make_user(
        db, test_user, [("g@gmail.com", "tok-g"), ("h@gmail.com", "tok-h")], "tok-h"
    )
    await _contact(db, user, "carol@x.com", "Carol")
    good = _gmail_service([_thread("th", "carol@x.com", "h@gmail.com")])

    def build(token):
        if token == "tok-g":
            raise RuntimeError("revoked")
        return good

    with patch("app.integrations.gmail._build_gmail_service", side_effect=build):
        count = await sync_gmail_for_user(user, db)

    assert count == 1


@pytest.mark.asyncio
async def test_gmail_legacy_token_without_linked_accounts_uses_user_email(db: AsyncSession, test_user: User):
    user = await _make_user(db, test_user, [], "tok-legacy")
    bob = await _contact(db, user, "bob@x.com", "Bob")
    service = _gmail_service([_thread("t1", "a@example.com", "bob@x.com")])

    with patch("app.integrations.gmail._build_gmail_service", return_value=service) as build:
        count = await sync_gmail_for_user(user, db)

    build.assert_called_once_with("tok-legacy")
    assert count == 1
    rows = (await db.execute(select(Interaction))).scalars().all()
    assert [(r.contact_id, r.direction) for r in rows] == [(bob.id, "outbound")]


def _calendar_service(events: list[dict]) -> MagicMock:
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": events}
    return service


def _event(attendees: list[str]) -> dict:
    start = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    return {
        "id": "evt1",
        "summary": "Catch up",
        "status": "confirmed",
        "start": {"dateTime": start},
        "end": {"dateTime": start},
        "attendees": [{"email": e} for e in attendees],
    }


@pytest.mark.asyncio
async def test_calendar_excludes_linked_account_address_from_attendees(db: AsyncSession, test_user: User):
    user = await _make_user(db, test_user, [("g@gmail.com", "tok-g")], "tok-g")
    service = _calendar_service([_event(["g@gmail.com", "bob@x.com"])])

    with patch("app.integrations.google_calendar._build_calendar_service", return_value=service):
        result = await sync_calendar_events(user, db)

    assert result["new_contacts"] == 1
    contacts = (await db.execute(select(Contact))).scalars().all()
    assert {e for c in contacts for e in (c.emails or [])} == {"bob@x.com"}


@pytest.mark.asyncio
async def test_calendar_syncs_every_linked_account_and_sums_results(db: AsyncSession, test_user: User):
    user = await _make_user(
        db, test_user, [("g@gmail.com", "tok-g"), ("h@gmail.com", "tok-h")], "tok-h"
    )
    services = {
        "tok-g": _calendar_service([_event(["g@gmail.com", "bob@x.com"])]),
        "tok-h": _calendar_service(
            [{**_event(["h@gmail.com", "carol@x.com"]), "id": "evt2"}]
        ),
    }

    with patch(
        "app.integrations.google_calendar._build_calendar_service",
        side_effect=lambda tok: services[tok],
    ) as build:
        result = await sync_calendar_events(user, db)

    assert sorted(c.args[0] for c in build.call_args_list) == ["tok-g", "tok-h"]
    assert result == {"new_contacts": 2, "new_interactions": 2, "events_processed": 2}


@pytest.mark.asyncio
async def test_calendar_legacy_token_without_linked_accounts_uses_user_email(db: AsyncSession, test_user: User):
    user = await _make_user(db, test_user, [], "tok-legacy")
    service = _calendar_service([_event(["a@example.com", "bob@x.com"])])

    with patch("app.integrations.google_calendar._build_calendar_service", return_value=service) as build:
        result = await sync_calendar_events(user, db)

    build.assert_called_once_with("tok-legacy")
    assert result["new_contacts"] == 1


@pytest.mark.asyncio
async def test_gmail_bcc_to_login_email_address_is_recognized_from_other_mailbox(db: AsyncSession, test_user: User):
    user = await _make_user(db, test_user, [("g@gmail.com", "tok-g")], "tok-g")
    contact = await _contact(db, user, "bob@x.com", "Bob")
    contact.bcc_hash = "abc1234"
    await db.commit()
    service = _gmail_service([_thread("t1", "g@gmail.com", "a+abc1234@example.com")])

    with patch("app.integrations.gmail._build_gmail_service", return_value=service):
        count = await sync_gmail_for_user(user, db)

    assert count == 1
    rows = (await db.execute(select(Interaction))).scalars().all()
    assert [r.contact_id for r in rows] == [contact.id]


@pytest.mark.asyncio
async def test_gmail_bcc_to_mailbox_address_is_recognized(db: AsyncSession, test_user: User):
    user = await _make_user(db, test_user, [("g@gmail.com", "tok-g")], "tok-g")
    contact = await _contact(db, user, "bob@x.com", "Bob")
    contact.bcc_hash = "abc1234"
    await db.commit()
    service = _gmail_service([_thread("t1", "g@gmail.com", "g+abc1234@gmail.com")])

    with patch("app.integrations.gmail._build_gmail_service", return_value=service):
        count = await sync_gmail_for_user(user, db)

    assert count == 1


@pytest.mark.asyncio
async def test_gmail_same_rfc_message_id_in_two_mailboxes_creates_one_interaction(db: AsyncSession, test_user: User):
    user = await _make_user(
        db, test_user, [("g@gmail.com", "tok-g"), ("h@gmail.com", "tok-h")], "tok-h"
    )
    await _contact(db, user, "bob@x.com", "Bob")
    services = {
        "tok-g": _gmail_service([_thread("tg", "bob@x.com", "g@gmail.com, h@gmail.com", rfc_id="<abc@x.com>")]),
        "tok-h": _gmail_service([_thread("th", "bob@x.com", "g@gmail.com, h@gmail.com", rfc_id="<abc@x.com>")]),
    }

    with patch("app.integrations.gmail._build_gmail_service", side_effect=lambda tok: services[tok]):
        count = await sync_gmail_for_user(user, db)

    assert count == 1
    rows = (await db.execute(select(Interaction))).scalars().all()
    assert len(rows) == 1
    assert rows[0].extra_data["rfc_message_id"] == "<abc@x.com>"


@pytest.mark.asyncio
async def test_gmail_rfc_message_id_dedups_against_previously_flushed_interaction(db: AsyncSession, test_user: User):
    user = await _make_user(db, test_user, [("g@gmail.com", "tok-g")], "tok-g")
    await _contact(db, user, "bob@x.com", "Bob")
    first = _gmail_service([_thread("t1", "bob@x.com", "g@gmail.com", rfc_id="<abc@x.com>")])
    second = _gmail_service([_thread("t2", "bob@x.com", "g@gmail.com", rfc_id="<abc@x.com>")])

    with patch("app.integrations.gmail._build_gmail_service", return_value=first):
        assert await sync_gmail_for_user(user, db) == 1
    await db.commit()
    with patch("app.integrations.gmail._build_gmail_service", return_value=second):
        assert await sync_gmail_for_user(user, db) == 0


@pytest.mark.asyncio
async def test_gmail_message_without_rfc_header_still_syncs(db: AsyncSession, test_user: User):
    user = await _make_user(db, test_user, [("g@gmail.com", "tok-g")], "tok-g")
    await _contact(db, user, "bob@x.com", "Bob")
    service = _gmail_service([_thread("t1", "bob@x.com", "g@gmail.com")])

    with patch("app.integrations.gmail._build_gmail_service", return_value=service):
        count = await sync_gmail_for_user(user, db)

    assert count == 1
    rows = (await db.execute(select(Interaction))).scalars().all()
    assert not (rows[0].extra_data or {}).get("rfc_message_id")


@pytest.mark.parametrize("login_mailbox_first", [True, False])
@pytest.mark.asyncio
async def test_gmail_backfills_rfc_id_on_existing_interaction_and_dedups_second_mailbox(
    db: AsyncSession, test_user: User, login_mailbox_first: bool
):
    linked = [("a@example.com", "tok-a"), ("g@gmail.com", "tok-g")]
    if not login_mailbox_first:
        linked.reverse()
    user = await _make_user(db, test_user, linked, "tok-a")
    bob = await _contact(db, user, "bob@x.com", "Bob")
    db.add(Interaction(
        user_id=user.id,
        contact_id=bob.id,
        platform="email",
        direction="inbound",
        content_preview="old copy",
        raw_reference_id="gmail:x1_m1",
        occurred_at=datetime.now(UTC) - timedelta(days=1),
    ))
    await db.commit()
    services = {
        "tok-a": _gmail_service([_thread("x1", "bob@x.com", "a@example.com", rfc_id="<r@x.com>")]),
        "tok-g": _gmail_service([_thread("x2", "bob@x.com", "a@example.com", rfc_id="<r@x.com>")]),
    }

    with patch("app.integrations.gmail._build_gmail_service", side_effect=lambda tok: services[tok]):
        await sync_gmail_for_user(user, db)

    rows = (await db.execute(select(Interaction))).scalars().all()
    assert len(rows) == 1
    assert rows[0].extra_data["rfc_message_id"] == "<r@x.com>"
