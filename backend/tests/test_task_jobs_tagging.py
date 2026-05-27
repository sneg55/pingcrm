"""Unit tests for app.services.task_jobs.tagging.

These tests exercise the lifted ``_apply_tags_to_contacts`` coroutine against
a real Postgres test database (via the conftest ``db`` fixture). External
integration boundaries (``assign_tags``, ``_get_anthropic_client``,
``app_settings.ANTHROPIC_API_KEY``) are mocked at the
``task_jobs.tagging`` module level so we cover the orchestration logic —
taxonomy lookup, eligibility filtering, chunk/batch processing, error paths,
and the final notification — without hitting Anthropic.

The Celery entrypoint wrapper is tested separately by invoking it via
``.apply()`` so retries surface as ``celery.exceptions.Retry`` exceptions
instead of dispatching to a broker.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from celery.exceptions import Retry, SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.notification import Notification
from app.models.tag_taxonomy import TagTaxonomy
from app.models.user import User
from app.services.task_jobs.tagging import (
    _apply_tags_to_contacts,
    apply_tags_to_contacts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _add_approved_taxonomy(
    db: AsyncSession,
    user_id: uuid.UUID,
    categories: dict[str, list[str]] | None = None,
) -> TagTaxonomy:
    tax = TagTaxonomy(
        user_id=user_id,
        categories=categories or {
            "Role/Expertise": ["UX Designer", "Solidity Dev"],
            "Industry": ["Crypto", "AI/ML"],
        },
        status="approved",
    )
    db.add(tax)
    await db.commit()
    await db.refresh(tax)
    return tax


async def _make_contact(db: AsyncSession, user_id: uuid.UUID, **overrides) -> Contact:
    defaults = dict(
        user_id=user_id,
        full_name="Some Contact",
        emails=[f"c_{uuid.uuid4().hex[:6]}@example.com"],
        source="manual",
        priority_level="medium",
    )
    defaults.update(overrides)
    c = Contact(**defaults)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _notifications_for(db: AsyncSession, user_id: uuid.UUID) -> list[Notification]:
    r = await db.execute(select(Notification).where(Notification.user_id == user_id))
    return list(r.scalars().all())


# ---------------------------------------------------------------------------
# _apply_tags_to_contacts — early exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_taxonomy_returns_sentinel(db: AsyncSession, test_user: User):
    result = await _apply_tags_to_contacts(db, test_user.id)
    assert result == {"status": "no_taxonomy", "tagged_count": 0}
    # No taxonomy → no notification fired
    assert await _notifications_for(db, test_user.id) == []


@pytest.mark.asyncio
async def test_draft_taxonomy_ignored(db: AsyncSession, test_user: User):
    """A non-approved taxonomy must be treated as if absent."""
    db.add(TagTaxonomy(
        user_id=test_user.id,
        categories={"Role/Expertise": ["UX Designer"]},
        status="draft",
    ))
    await db.commit()

    result = await _apply_tags_to_contacts(db, test_user.id)
    assert result == {"status": "no_taxonomy", "tagged_count": 0}


@pytest.mark.asyncio
async def test_missing_api_key_creates_notification_and_returns(
    db: AsyncSession, test_user: User
):
    await _add_approved_taxonomy(db, test_user.id)
    await _make_contact(db, test_user.id)

    with patch("app.services.task_jobs.tagging.app_settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = ""
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result == {"status": "no_api_key", "tagged_count": 0}
    notifs = await _notifications_for(db, test_user.id)
    assert len(notifs) == 1
    assert notifs[0].title == "Auto-tagging failed"
    assert "ANTHROPIC_API_KEY" in notifs[0].body


# ---------------------------------------------------------------------------
# _apply_tags_to_contacts — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tags_single_contact_end_to_end(
    db: AsyncSession, test_user: User
):
    await _add_approved_taxonomy(db, test_user.id)
    contact = await _make_contact(db, test_user.id, full_name="Alice Example")

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch(
            "app.services.task_jobs.tagging._get_anthropic_client",
            return_value=object(),
        ) as mock_client,
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(return_value=["UX Designer", "Crypto"]),
        ) as mock_assign,
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result == {"status": "ok", "tagged_count": 1}
    mock_client.assert_called_once()
    assert mock_assign.await_count == 1

    await db.refresh(contact)
    assert sorted(contact.tags) == ["Crypto", "UX Designer"]

    notifs = await _notifications_for(db, test_user.id)
    assert len(notifs) == 1
    assert notifs[0].title == "Auto-tagging completed"
    assert "Tagged 1 of 1 contacts" in notifs[0].body


@pytest.mark.asyncio
async def test_skips_already_tagged_contacts(
    db: AsyncSession, test_user: User
):
    """A contact already bearing a taxonomy tag (case-insensitive) is skipped
    and counted under the 'already tagged' bucket — assign_tags is never called
    for it."""
    await _add_approved_taxonomy(db, test_user.id)
    # already_tagged matches "UX Designer" case-insensitively
    already_tagged = await _make_contact(
        db, test_user.id, full_name="Old", tags=["ux designer"],
    )
    fresh = await _make_contact(db, test_user.id, full_name="New", tags=None)

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(return_value=["Crypto"]),
        ) as mock_assign,
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result == {"status": "ok", "tagged_count": 1}
    # assign_tags only called once — for `fresh`
    assert mock_assign.await_count == 1

    await db.refresh(already_tagged)
    await db.refresh(fresh)
    # already_tagged untouched
    assert already_tagged.tags == ["ux designer"]
    assert "Crypto" in fresh.tags

    notif = (await _notifications_for(db, test_user.id))[0]
    assert "Tagged 1 of 1 contacts" in notif.body
    assert "(1 already tagged)" in notif.body


@pytest.mark.asyncio
async def test_no_eligible_contacts_with_all_already_tagged(
    db: AsyncSession, test_user: User
):
    """If every contact is already tagged, the early-empty branch fires the
    'All N contacts already have taxonomy tags.' notification."""
    await _add_approved_taxonomy(db, test_user.id)
    await _make_contact(db, test_user.id, tags=["UX Designer"])
    await _make_contact(db, test_user.id, tags=["Crypto"])

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch("app.services.task_jobs.tagging.assign_tags", new=AsyncMock(return_value=[])),
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result == {"status": "ok", "tagged_count": 0}
    notif = (await _notifications_for(db, test_user.id))[0]
    assert notif.title == "Auto-tagging finished"
    assert "All 2 contacts already have taxonomy tags." == notif.body


@pytest.mark.asyncio
async def test_no_eligible_contacts_with_zero_contacts(
    db: AsyncSession, test_user: User
):
    """No contacts at all → 'No eligible contacts to tag.' notification."""
    await _add_approved_taxonomy(db, test_user.id)

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch("app.services.task_jobs.tagging.assign_tags", new=AsyncMock(return_value=[])),
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result == {"status": "ok", "tagged_count": 0}
    notif = (await _notifications_for(db, test_user.id))[0]
    assert notif.body == "No eligible contacts to tag."


@pytest.mark.asyncio
async def test_archived_contacts_excluded_when_no_explicit_ids(
    db: AsyncSession, test_user: User
):
    await _add_approved_taxonomy(db, test_user.id)
    active = await _make_contact(db, test_user.id, full_name="Active", tags=None)
    await _make_contact(
        db, test_user.id, full_name="Gone", priority_level="archived", tags=None,
    )

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(return_value=["Crypto"]),
        ) as mock_assign,
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result["tagged_count"] == 1
    # Only the active contact was passed to assign_tags
    assert mock_assign.await_count == 1
    await db.refresh(active)
    assert active.tags == ["Crypto"]


@pytest.mark.asyncio
async def test_second_tier_contacts_excluded_when_no_explicit_ids(
    db: AsyncSession, test_user: User
):
    """The default branch filters out contacts already tagged '2nd tier'."""
    await _add_approved_taxonomy(db, test_user.id)
    keep = await _make_contact(db, test_user.id, tags=None)
    await _make_contact(db, test_user.id, tags=["2nd tier"])

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(return_value=["Crypto"]),
        ) as mock_assign,
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        await _apply_tags_to_contacts(db, test_user.id)

    # Only `keep` was tagged
    assert mock_assign.await_count == 1
    await db.refresh(keep)
    assert keep.tags == ["Crypto"]


@pytest.mark.asyncio
async def test_explicit_contact_ids_includes_archived(
    db: AsyncSession, test_user: User
):
    """When contact_ids is explicitly passed, archived/2nd-tier filters do NOT
    apply — only the user_id + id-in-list scope."""
    await _add_approved_taxonomy(db, test_user.id)
    archived = await _make_contact(
        db, test_user.id, priority_level="archived", tags=None,
    )

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(return_value=["Crypto"]),
        ),
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(
            db, test_user.id, contact_ids=[str(archived.id)],
        )

    assert result["tagged_count"] == 1
    await db.refresh(archived)
    assert archived.tags == ["Crypto"]


@pytest.mark.asyncio
async def test_other_users_contacts_not_tagged(
    db: AsyncSession, test_user: User, user_factory
):
    """Cross-user isolation: another user's contacts must never be tagged."""
    other = await user_factory()
    await _add_approved_taxonomy(db, test_user.id)
    mine = await _make_contact(db, test_user.id, tags=None)
    theirs = await _make_contact(db, other.id, tags=None)

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(return_value=["Crypto"]),
        ) as mock_assign,
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result["tagged_count"] == 1
    assert mock_assign.await_count == 1
    await db.refresh(mine)
    await db.refresh(theirs)
    assert mine.tags == ["Crypto"]
    assert not theirs.tags  # untouched (None or [])


@pytest.mark.asyncio
async def test_interaction_topics_passed_to_assign_tags(
    db: AsyncSession, test_user: User
):
    """Interaction topics for each contact are loaded, capped at 10 per contact,
    truncated to 100 chars each, and forwarded to assign_tags()."""
    await _add_approved_taxonomy(db, test_user.id)
    contact = await _make_contact(db, test_user.id, tags=None)

    base = datetime.now(UTC) - timedelta(days=1)
    # 12 interactions — only the 10 most recent (by occurred_at desc) should reach assign_tags
    for i in range(12):
        db.add(Interaction(
            contact_id=contact.id,
            user_id=test_user.id,
            platform="email",
            direction="inbound",
            content_preview="x" * 150 + f" #{i}",  # >100 chars → must be truncated
            occurred_at=base - timedelta(minutes=i),
        ))
    await db.commit()

    captured_topics: list[list[str]] = []

    async def fake_assign(contact_data, taxonomy_cats, *, client):  # noqa: ARG001
        captured_topics.append(list(contact_data["interaction_topics"]))
        return ["Crypto"]

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(side_effect=fake_assign),
        ),
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        await _apply_tags_to_contacts(db, test_user.id)

    assert len(captured_topics) == 1
    topics = captured_topics[0]
    assert len(topics) == 10  # capped
    # Each topic was truncated to 100 chars
    assert all(len(t) == 100 for t in topics)


# ---------------------------------------------------------------------------
# _apply_tags_to_contacts — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_contact_assign_failure_recorded_in_errors(
    db: AsyncSession, test_user: User
):
    """If assign_tags raises for one contact, that contact is counted as an
    error but the loop continues with the others."""
    await _add_approved_taxonomy(db, test_user.id)
    good = await _make_contact(db, test_user.id, full_name="Good", tags=None)
    bad = await _make_contact(db, test_user.id, full_name="Bad", tags=None)

    async def fake_assign(contact_data, *args, **kwargs):
        if contact_data["full_name"] == "Bad":
            raise RuntimeError("LLM exploded")
        return ["Crypto"]

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(side_effect=fake_assign),
        ),
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result == {"status": "ok", "tagged_count": 1}
    await db.refresh(good)
    await db.refresh(bad)
    assert good.tags == ["Crypto"]
    assert not bad.tags  # untouched (None or [])

    notif = (await _notifications_for(db, test_user.id))[0]
    assert "Tagged 1 of 2 contacts" in notif.body
    assert "(1 errors — check worker logs)" in notif.body


@pytest.mark.asyncio
async def test_zero_tagged_uses_finished_with_issues_title(
    db: AsyncSession, test_user: User
):
    """When every assign_tags call returns [] (nothing matched), the final
    notification title flips to 'Auto-tagging finished with issues'."""
    await _add_approved_taxonomy(db, test_user.id)
    await _make_contact(db, test_user.id, tags=None)

    with (
        patch("app.services.task_jobs.tagging.app_settings") as mock_settings,
        patch("app.services.task_jobs.tagging._get_anthropic_client", return_value=object()),
        patch(
            "app.services.task_jobs.tagging.assign_tags",
            new=AsyncMock(return_value=[]),
        ),
    ):
        mock_settings.ANTHROPIC_API_KEY = "sk-test"
        result = await _apply_tags_to_contacts(db, test_user.id)

    assert result == {"status": "ok", "tagged_count": 0}
    notif = (await _notifications_for(db, test_user.id))[0]
    assert notif.title == "Auto-tagging finished with issues"
    assert "Tagged 0 of 1 contacts" in notif.body


# ---------------------------------------------------------------------------
# Celery wrapper — argument validation + retry plumbing
# ---------------------------------------------------------------------------


def test_apply_tags_returns_sentinel_on_invalid_uuid():
    result = apply_tags_to_contacts.apply(args=["not-a-uuid"]).get()
    assert result == {"status": "invalid_user_id", "tagged_count": 0}


def test_apply_tags_returns_sentinel_on_invalid_uuid_with_contact_ids():
    """Even when contact_ids is passed, the UUID-validation early-exit still
    fires with the same sentinel."""
    result = apply_tags_to_contacts.apply(
        args=["not-a-uuid", [str(uuid.uuid4())]],
    ).get()
    assert result == {"status": "invalid_user_id", "tagged_count": 0}


def test_apply_tags_retries_and_does_not_notify_before_exhausted():
    """First failure → Retry raised, notify_tagging_failure not yet fired."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.tagging._apply_tags_to_contacts",
            new=AsyncMock(side_effect=RuntimeError("nope")),
        ),
        patch("app.services.task_jobs.tagging.task_session") as mock_session,
        patch("app.services.task_jobs.tagging.notify_tagging_failure") as mock_notify,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        with pytest.raises(Retry):
            apply_tags_to_contacts.apply(args=[uid], throw=True).get()

    assert mock_notify.delay.call_count == 0


def test_apply_tags_notifies_when_retries_exhausted():
    """On the final retry attempt, notify_tagging_failure.delay fires exactly
    once with the truncated error message."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.tagging._apply_tags_to_contacts",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("app.services.task_jobs.tagging.task_session") as mock_session,
        patch("app.services.task_jobs.tagging.notify_tagging_failure") as mock_notify,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        apply_tags_to_contacts.apply(
            args=[uid],
            retries=apply_tags_to_contacts.max_retries,
        )

    mock_notify.delay.assert_called_once()
    args = mock_notify.delay.call_args.args
    assert args[0] == uid
    assert "Tagging failed after retries" in args[1]
    assert "boom" in args[1]


def test_apply_tags_soft_time_limit_returns_timeout_sentinel():
    """SoftTimeLimitExceeded does NOT trigger a retry; it returns
    {'status': 'timeout', 'tagged_count': 0} after firing a notification."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.tagging._apply_tags_to_contacts",
            new=AsyncMock(side_effect=SoftTimeLimitExceeded()),
        ),
        patch("app.services.task_jobs.tagging.task_session") as mock_session,
        patch("app.services.task_jobs.tagging.notify_tagging_failure") as mock_notify,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = apply_tags_to_contacts.apply(args=[uid]).get()

    assert result == {"status": "timeout", "tagged_count": 0}
    mock_notify.delay.assert_called_once()
    msg = mock_notify.delay.call_args.args[1]
    assert "Tagging timed out" in msg


def test_apply_tags_runs_wrapper_and_returns_impl_result():
    """Cover the _runner + _run path with a successful impl call."""
    uid = str(uuid.uuid4())
    with (
        patch(
            "app.services.task_jobs.tagging._apply_tags_to_contacts",
            new=AsyncMock(return_value={"status": "ok", "tagged_count": 7}),
        ),
        patch("app.services.task_jobs.tagging.task_session") as mock_session,
    ):
        cm = AsyncMock()
        cm.__aenter__.return_value = object()
        cm.__aexit__.return_value = None
        mock_session.return_value = cm

        result = apply_tags_to_contacts.apply(args=[uid]).get()

    assert result == {"status": "ok", "tagged_count": 7}
