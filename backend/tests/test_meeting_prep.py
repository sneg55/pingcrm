"""Tests for meeting-prep email sending via Gmail API."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Gmail send service tests
# ---------------------------------------------------------------------------


class _FakeGoogleAccount:
    """Minimal stand-in for a Google account object."""

    def __init__(self, refresh_token: str = "refresh_tok", email: str = "user@example.com"):
        self.refresh_token = refresh_token
        self.email = email


@patch("app.integrations.gmail_send.build")
@patch("app.integrations.gmail_send.Credentials")
def test_send_email_calls_gmail_api(mock_creds_cls, mock_build):
    """send_email builds credentials, sends message, and returns True."""
    from app.integrations.gmail_send import send_email

    mock_service = MagicMock()
    mock_build.return_value = mock_service

    account = _FakeGoogleAccount()
    result = send_email(account, "Subject", "<p>Hello</p>")

    assert result is True
    mock_creds_cls.assert_called_once()
    mock_build.assert_called_once()
    mock_service.users.return_value.messages.return_value.send.assert_called_once()


@patch("app.integrations.gmail_send.build")
@patch("app.integrations.gmail_send.Credentials")
def test_send_email_returns_false_on_network_failure(mock_creds_cls, mock_build):
    """send_email returns False when the API execute() raises a generic exception."""
    from app.integrations.gmail_send import send_email

    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.users.return_value.messages.return_value.send.return_value.execute.side_effect = (
        Exception("network timeout")
    )

    account = _FakeGoogleAccount()
    result = send_email(account, "Subject", "<p>Hello</p>")

    assert result is False


@patch("app.integrations.gmail_send.build")
@patch("app.integrations.gmail_send.Credentials")
def test_send_email_returns_auth_error_on_refresh_failure(mock_creds_cls, mock_build):
    """send_email returns 'auth_error' when credential refresh fails."""
    from google.auth.exceptions import RefreshError

    from app.integrations.gmail_send import send_email

    mock_build.side_effect = RefreshError("token revoked")

    account = _FakeGoogleAccount()
    result = send_email(account, "Subject", "<p>Hello</p>")

    assert result == "auth_error"


# ---------------------------------------------------------------------------
# Meeting-prep composer tests
# ---------------------------------------------------------------------------


class _FakeInteraction:
    """Minimal stand-in for an Interaction ORM model."""

    def __init__(
        self,
        *,
        contact_id: uuid.UUID,
        user_id: uuid.UUID,
        platform: str = "meeting",
        direction: str = "inbound",
        content_preview: str | None = None,
        raw_reference_id: str | None = None,
        occurred_at: datetime | None = None,
    ):
        self.id = uuid.uuid4()
        self.contact_id = contact_id
        self.user_id = user_id
        self.platform = platform
        self.direction = direction
        self.content_preview = content_preview
        self.raw_reference_id = raw_reference_id
        self.occurred_at = occurred_at or datetime.now(UTC)
        self.created_at = datetime.now(UTC)
        self.is_read_by_recipient = None


class _FakeContact:
    """Minimal stand-in for a Contact ORM model."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        full_name: str = "Alice Smith",
        title: str | None = "CTO",
        company: str | None = "Acme Corp",
        relationship_score: int = 8,
        interaction_count: int = 12,
        last_interaction_at: datetime | None = None,
        avatar_url: str | None = None,
        twitter_bio: str | None = "Building cool things",
        linkedin_headline: str | None = "CTO at Acme",
        linkedin_bio: str | None = None,
        telegram_bio: str | None = None,
    ):
        self.id = id or uuid.uuid4()
        self.user_id = user_id or uuid.uuid4()
        self.full_name = full_name
        self.title = title
        self.company = company
        self.relationship_score = relationship_score
        self.interaction_count = interaction_count
        self.last_interaction_at = last_interaction_at or datetime.now(UTC)
        self.avatar_url = avatar_url
        self.twitter_bio = twitter_bio
        self.linkedin_headline = linkedin_headline
        self.linkedin_bio = linkedin_bio
        self.telegram_bio = telegram_bio


class _FakeScalarsResult:
    """Mocks the result of db.execute(...).scalars().all()."""

    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    """Mocks the result of db.execute(...)."""

    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalarsResult(self._items)


# ---------------------------------------------------------------------------
# Task 3: get_upcoming_meetings
# ---------------------------------------------------------------------------


class TestGetUpcomingMeetings:
    @pytest.mark.asyncio
    async def test_returns_meetings_in_window(self):
        """Two interactions with the same event_id collapse into 1 meeting with 2 contact_ids."""
        from app.services.meeting_prep import get_upcoming_meetings

        user_id = uuid.uuid4()
        c1 = uuid.uuid4()
        c2 = uuid.uuid4()
        event_time = datetime(2026, 4, 1, 14, 0, tzinfo=UTC)

        interactions = [
            _FakeInteraction(
                contact_id=c1,
                user_id=user_id,
                platform="meeting",
                content_preview="Strategy sync",
                raw_reference_id=f"gcal:evt123:{c1}",
                occurred_at=event_time,
            ),
            _FakeInteraction(
                contact_id=c2,
                user_id=user_id,
                platform="meeting",
                content_preview="Strategy sync",
                raw_reference_id=f"gcal:evt123:{c2}",
                occurred_at=event_time,
            ),
        ]

        db = AsyncMock()
        db.execute.return_value = _FakeResult(interactions)

        window_start = datetime(2026, 4, 1, 13, 0, tzinfo=UTC)
        window_end = datetime(2026, 4, 1, 15, 0, tzinfo=UTC)

        meetings = await get_upcoming_meetings(user_id, window_start, window_end, db)

        assert len(meetings) == 1
        m = meetings[0]
        assert m["event_id"] == "evt123"
        assert m["title"] == "Strategy sync"
        assert m["occurred_at"] == event_time
        assert set(m["contact_ids"]) == {c1, c2}

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_meetings(self):
        """No matching interactions → empty list."""
        from app.services.meeting_prep import get_upcoming_meetings

        db = AsyncMock()
        db.execute.return_value = _FakeResult([])

        meetings = await get_upcoming_meetings(
            uuid.uuid4(),
            datetime(2026, 4, 1, 13, 0, tzinfo=UTC),
            datetime(2026, 4, 1, 15, 0, tzinfo=UTC),
            db,
        )

        assert meetings == []


# ---------------------------------------------------------------------------
# Task 4: build_prep_brief
# ---------------------------------------------------------------------------


class TestBuildPrepBrief:
    @pytest.mark.asyncio
    async def test_builds_brief_for_known_contacts(self):
        """A contact with 1 interaction produces a complete brief dict."""
        from app.services.meeting_prep import build_prep_brief

        contact = _FakeContact()
        interaction = _FakeInteraction(
            contact_id=contact.id,
            user_id=contact.user_id,
            platform="email",
            direction="outbound",
            content_preview="Checking in about the project",
            occurred_at=datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
        )

        # db.execute is called twice: once for contacts, once for interactions
        db = AsyncMock()
        db.execute.side_effect = [
            _FakeResult([contact]),       # contacts query
            _FakeResult([interaction]),    # interactions query
        ]

        briefs = await build_prep_brief([contact.id], db)

        assert len(briefs) == 1
        b = briefs[0]
        assert b["contact_id"] == contact.id
        assert b["name"] == "Alice Smith"
        assert b["title"] == "CTO"
        assert b["company"] == "Acme Corp"
        assert b["score"] == 8
        assert b["score_label"] == "Strong"
        assert b["interaction_count"] == 12
        assert b["twitter_bio"] == "Building cool things"
        assert b["linkedin_headline"] == "CTO at Acme"
        assert len(b["recent_interactions"]) == 1
        assert b["recent_interactions"][0]["platform"] == "email"
        assert b["recent_interactions"][0]["preview"] == "Checking in about the project"

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_contact_ids(self):
        """No matching contacts → empty list."""
        from app.services.meeting_prep import build_prep_brief

        db = AsyncMock()
        db.execute.side_effect = [
            _FakeResult([]),  # contacts query returns nothing
            _FakeResult([]),  # interactions query returns nothing
        ]

        briefs = await build_prep_brief([uuid.uuid4()], db)

        assert briefs == []


# ---------------------------------------------------------------------------
# Task 5: generate_talking_points
# ---------------------------------------------------------------------------


class TestGenerateTalkingPoints:
    @pytest.mark.asyncio
    @patch("app.services.meeting_prep._call_anthropic_with_retry")
    @patch("app.services.meeting_prep.settings")
    async def test_returns_talking_points(self, mock_settings, mock_api_call):
        """Successful API call returns the AI-generated text."""
        from app.services.meeting_prep import generate_talking_points

        mock_settings.ANTHROPIC_API_KEY = "test-key"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="- Discuss product roadmap\n- Ask about Series B")]
        mock_api_call.return_value = mock_response

        briefs = [
            {
                "name": "Alice Smith",
                "title": "CTO",
                "company": "Acme Corp",
                "score_label": "Strong",
                "twitter_bio": "Building cool things",
                "linkedin_headline": "CTO at Acme",
                "linkedin_bio": None,
                "telegram_bio": None,
                "recent_interactions": [
                    {"platform": "email", "preview": "Checking in about the project"},
                ],
            }
        ]

        result = await generate_talking_points(briefs, "Strategy sync")

        assert "Discuss product roadmap" in result
        assert "Series B" in result
        mock_api_call.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.meeting_prep._call_anthropic_with_retry")
    @patch("app.services.meeting_prep.settings")
    async def test_returns_empty_on_api_failure(self, mock_settings, mock_api_call):
        """API exception → graceful degradation, returns empty string."""
        from app.services.meeting_prep import generate_talking_points

        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_api_call.side_effect = Exception("API unreachable")

        briefs = [{"name": "Alice", "score_label": "Warm"}]

        result = await generate_talking_points(briefs, "Catch up")

        assert result == ""


# ---------------------------------------------------------------------------
# Task 6: compose_prep_email
# ---------------------------------------------------------------------------


class TestComposePrepEmail:
    def test_renders_html_with_known_contacts(self):
        """HTML output includes attendee details, score, bio, and talking points."""
        from app.services.meeting_prep import compose_prep_email

        meeting = {
            "event_id": "evt123",
            "title": "Strategy sync",
            "occurred_at": datetime(2026, 4, 1, 14, 0, tzinfo=UTC),
            "contact_ids": [uuid.uuid4()],
        }
        briefs = [
            {
                "contact_id": uuid.uuid4(),
                "name": "Alice Smith",
                "title": "CTO",
                "company": "Acme Corp",
                "score": 8,
                "score_label": "Strong",
                "interaction_count": 12,
                "last_interaction_at": datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
                "avatar_url": None,
                "twitter_bio": "Building cool things",
                "linkedin_headline": "CTO at Acme",
                "linkedin_bio": None,
                "telegram_bio": None,
                "recent_interactions": [
                    {
                        "date": datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
                        "preview": "Checking in about the project",
                        "platform": "email",
                    },
                ],
            }
        ]
        talking_points = "- Discuss product roadmap\n- Ask about Series B"

        subject, html = compose_prep_email(meeting, briefs, talking_points)

        assert "Strategy sync" in subject
        assert "in 30 minutes" in subject
        assert "Alice Smith" in html
        assert "CTO" in html
        assert "Acme Corp" in html
        assert "Strong" in html
        assert "Building cool things" in html
        assert "Suggested Talking Points" in html
        assert "Discuss product roadmap" in html

    def test_renders_html_without_talking_points(self):
        """Empty talking points → 'Suggested Talking Points' section not present."""
        from app.services.meeting_prep import compose_prep_email

        meeting = {
            "event_id": "evt456",
            "title": "Quick check-in",
            "occurred_at": datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
            "contact_ids": [],
        }

        subject, html = compose_prep_email(meeting, [], "")

        assert "Quick check-in" in subject
        assert "Suggested Talking Points" not in html
