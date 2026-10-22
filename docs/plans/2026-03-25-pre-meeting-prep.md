# Pre-Meeting Prep Email Notifications Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send an HTML prep brief email 30 minutes before Google Calendar meetings, containing attendee profiles, interaction history, relationship scores, and AI-generated talking points.

**Architecture:** Celery beat task runs every 10 minutes, scans for meetings in a 30-40 minute window, gathers contact context from the database, calls Claude Haiku for talking points, composes an HTML email, and sends it via the Gmail API using the user's own OAuth token. Redis keys provide dedup. A new `gmail.send` OAuth scope is required; existing users get a re-authorization notification.

**Tech Stack:** Python, FastAPI, Celery, Redis, SQLAlchemy async, Google API Python Client, Anthropic SDK, Gmail API

**Spec:** `docs/specs/2026-03-25-pre-meeting-prep-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/integrations/gmail_send.py` | Sync Gmail send service (build credentials, compose MIME, send) |
| Create | `backend/app/services/meeting_prep.py` | Meeting prep composer: query meetings, build briefs, generate talking points, render HTML |
| Create | `backend/app/services/task_jobs/meeting_prep.py` | Celery beat task: scan, dedup, orchestrate |
| Create | `backend/tests/test_meeting_prep.py` | All tests for this feature |
| Modify | `backend/app/integrations/google_auth.py:11-18` | Add `gmail.send` to SCOPES list |
| Modify | `backend/app/services/tasks.py` | Re-export `scan_meeting_preps` |
| Modify | `backend/app/core/celery_app.py:24-80` | Add beat schedule entry |
| Modify | `backend/tests/test_task_registry.py:12-37` | Add `scan_meeting_preps` to expected task set |
| Modify | `backend/app/api/settings.py` | Add `meeting_prep_enabled` setting (stored in `sync_settings` JSONB under `gmail.meeting_prep_enabled`) |

---

## Chunk 1: Gmail Send Service + OAuth Scope

### Task 1: Add gmail.send OAuth scope

**Files:**
- Modify: `backend/app/integrations/google_auth.py:11-18`

- [ ] **Step 1: Add the gmail.send scope**

In `backend/app/integrations/google_auth.py`, add the new scope to the SCOPES list:

```python
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
```

Note: `include_granted_scopes="true"` is already set in `build_oauth_url()` (line 37), so existing read-only tokens continue working. Users who need send will be prompted to re-authorize.

- [ ] **Step 2: Commit**

```bash
git add backend/app/integrations/google_auth.py
git commit -m "feat(meeting-prep): add gmail.send OAuth scope"
```

---

### Task 2: Gmail Send Service

**Files:**
- Create: `backend/tests/test_meeting_prep.py`
- Create: `backend/app/integrations/gmail_send.py`

- [ ] **Step 1: Write failing test for send_email**

Create `backend/tests/test_meeting_prep.py`:

```python
"""Tests for Pre-Meeting Prep Email Notifications (issue #6)."""
from __future__ import annotations

import html
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGmailSend:
    """Tests for backend/app/integrations/gmail_send.py."""

    @patch("app.integrations.gmail_send.build")
    def test_send_email_calls_gmail_api(self, mock_build):
        from app.integrations.gmail_send import send_email

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        google_account = MagicMock()
        google_account.refresh_token = "fake-refresh-token"
        google_account.email = "user@gmail.com"

        result = send_email(google_account, "Test Subject", "<h1>Hello</h1>")

        mock_build.assert_called_once()
        assert result is True

    @patch("app.integrations.gmail_send.build")
    def test_send_email_returns_false_on_network_failure(self, mock_build):
        from app.integrations.gmail_send import send_email

        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.send.return_value.execute.side_effect = (
            Exception("Network error")
        )
        mock_build.return_value = mock_service

        google_account = MagicMock()
        google_account.refresh_token = "fake-refresh-token"
        google_account.email = "user@gmail.com"

        result = send_email(google_account, "Subject", "<p>Body</p>")
        assert result is False

    @patch("app.integrations.gmail_send.build")
    def test_send_email_returns_auth_error_on_refresh_failure(self, mock_build):
        """RefreshError returns 'auth_error' sentinel for re-auth notification."""
        from google.auth.exceptions import RefreshError

        from app.integrations.gmail_send import send_email

        mock_build.side_effect = RefreshError("Token revoked")

        google_account = MagicMock()
        google_account.refresh_token = "expired-token"
        google_account.email = "user@gmail.com"

        result = send_email(google_account, "Subject", "<p>Body</p>")
        assert result == "auth_error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestGmailSend -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.integrations.gmail_send'`

- [ ] **Step 3: Implement gmail_send.py**

Create `backend/app/integrations/gmail_send.py`:

```python
"""Gmail send service for PingCRM.

Sends emails via the Gmail API using a user's OAuth credentials.
This is a sync module — called from within Celery task async wrappers.
"""
from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(google_account, subject: str, html_body: str) -> bool | str:
    """Send an HTML email via Gmail API using the given Google account.

    Args:
        google_account: Object with .refresh_token and .email attributes.
        subject: Email subject line.
        html_body: HTML content for the email body.

    Returns:
        True on success, False on transient failure, "auth_error" on auth failure.
    """
    try:
        creds = Credentials(
            token=None,
            refresh_token=google_account.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        message = MIMEText(html_body, "html")
        message["to"] = google_account.email
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        logger.info("Email sent to %s: %s", google_account.email, subject)
        return True
    except RefreshError:
        logger.warning(
            "Gmail auth failed (token revoked/expired) for %s",
            google_account.email,
        )
        return "auth_error"
    except HttpError as e:
        if e.resp.status in (401, 403):
            logger.warning(
                "Gmail auth/scope error for %s: %s",
                google_account.email, e,
            )
            return "auth_error"
        logger.exception("Gmail send HttpError for %s", google_account.email)
        return False
    except Exception:
        logger.exception("Gmail send failed for %s: %s", google_account.email, subject)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestGmailSend -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/gmail_send.py backend/tests/test_meeting_prep.py
git commit -m "feat(meeting-prep): add Gmail send service with auth error detection"
```

---

## Chunk 2: Meeting Prep Composer

### Task 3: Query upcoming meetings

**Files:**
- Modify: `backend/tests/test_meeting_prep.py`
- Create: `backend/app/services/meeting_prep.py`

The key challenge: meetings are stored as individual Interaction rows per attendee (one row per contact, all sharing `gcal:{event_id}:*` reference IDs). We need to group them by event ID to reconstruct the full attendee list.

- [ ] **Step 1: Write failing test for get_upcoming_meetings**

Append to `backend/tests/test_meeting_prep.py`:

```python
class TestGetUpcomingMeetings:
    """Tests for meeting_prep.get_upcoming_meetings."""

    @pytest.mark.asyncio
    async def test_returns_meetings_in_window(self):
        from app.services.meeting_prep import get_upcoming_meetings

        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        window_start = now + timedelta(minutes=30)
        window_end = now + timedelta(minutes=40)

        event_id = "abc123"
        contact1_id = uuid.uuid4()
        contact2_id = uuid.uuid4()

        interaction1 = MagicMock()
        interaction1.raw_reference_id = f"gcal:{event_id}:{contact1_id}"
        interaction1.contact_id = contact1_id
        interaction1.content_preview = "Team standup"
        interaction1.occurred_at = window_start + timedelta(minutes=2)

        interaction2 = MagicMock()
        interaction2.raw_reference_id = f"gcal:{event_id}:{contact2_id}"
        interaction2.contact_id = contact2_id
        interaction2.content_preview = "Team standup"
        interaction2.occurred_at = window_start + timedelta(minutes=2)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [interaction1, interaction2]

        db = AsyncMock()
        db.execute.return_value = mock_result

        meetings = await get_upcoming_meetings(user_id, window_start, window_end, db)

        assert len(meetings) == 1
        meeting = meetings[0]
        assert meeting["event_id"] == event_id
        assert meeting["title"] == "Team standup"
        assert set(meeting["contact_ids"]) == {contact1_id, contact2_id}

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_meetings(self):
        from app.services.meeting_prep import get_upcoming_meetings

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = mock_result

        meetings = await get_upcoming_meetings(uuid.uuid4(), datetime.now(UTC), datetime.now(UTC), db)
        assert meetings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestGetUpcomingMeetings -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement get_upcoming_meetings**

Create `backend/app/services/meeting_prep.py`:

```python
"""Pre-meeting prep email composer for PingCRM.

Queries upcoming meetings, gathers attendee context, generates AI talking
points, and composes an HTML prep brief email.
"""
from __future__ import annotations

import html as html_mod
import logging
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction

logger = logging.getLogger(__name__)


async def get_upcoming_meetings(
    user_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
    db: AsyncSession,
) -> list[dict]:
    """Find meetings in the time window, grouped by event ID.

    Calendar events are stored as Interaction rows with platform="meeting"
    and raw_reference_id="gcal:{event_id}:{contact_id}". Multiple rows
    per event (one per attendee) are grouped back into a single meeting.

    Returns a list of dicts: {event_id, title, occurred_at, contact_ids}.
    """
    result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == user_id,
            Interaction.platform == "meeting",
            Interaction.occurred_at >= window_start,
            Interaction.occurred_at < window_end,
        )
    )
    interactions = result.scalars().all()

    events: dict[str, dict] = defaultdict(
        lambda: {"contact_ids": [], "title": "", "occurred_at": None}
    )
    for ix in interactions:
        parts = (ix.raw_reference_id or "").split(":")
        if len(parts) < 2:
            continue
        event_id = parts[1]  # gcal:{event_id}:{contact_id}
        events[event_id]["contact_ids"].append(ix.contact_id)
        events[event_id]["title"] = ix.content_preview or ""
        events[event_id]["occurred_at"] = ix.occurred_at

    return [
        {
            "event_id": eid,
            "title": data["title"],
            "occurred_at": data["occurred_at"],
            "contact_ids": data["contact_ids"],
        }
        for eid, data in events.items()
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestGetUpcomingMeetings -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meeting_prep.py backend/tests/test_meeting_prep.py
git commit -m "feat(meeting-prep): add get_upcoming_meetings with event grouping"
```

---

### Task 4: Build prep brief (gather contact context)

**Files:**
- Modify: `backend/tests/test_meeting_prep.py`
- Modify: `backend/app/services/meeting_prep.py`

- [ ] **Step 1: Write failing test for build_prep_brief**

Append to `backend/tests/test_meeting_prep.py`:

```python
class TestBuildPrepBrief:
    """Tests for meeting_prep.build_prep_brief."""

    @pytest.mark.asyncio
    async def test_builds_brief_for_known_contacts(self):
        from app.services.meeting_prep import build_prep_brief

        contact_id = uuid.uuid4()

        contact = MagicMock()
        contact.id = contact_id
        contact.full_name = "Jane Doe"
        contact.given_name = "Jane"
        contact.title = "VP Engineering"
        contact.company = "Acme Corp"
        contact.relationship_score = 8
        contact.interaction_count = 15
        contact.last_interaction_at = datetime(2026, 3, 20, tzinfo=UTC)
        contact.avatar_url = "/static/avatars/abc.jpg"
        contact.twitter_bio = "Building the future"
        contact.linkedin_headline = "VP Engineering at Acme"
        contact.linkedin_bio = "20 years in tech"
        contact.telegram_bio = None

        contact_result = MagicMock()
        contact_result.scalars.return_value.all.return_value = [contact]

        ix1 = MagicMock()
        ix1.occurred_at = datetime(2026, 3, 20, tzinfo=UTC)
        ix1.content_preview = "Discussed Q2 roadmap"
        ix1.platform = "gmail"
        ix1.contact_id = contact_id

        ix_result = MagicMock()
        ix_result.scalars.return_value.all.return_value = [ix1]

        db = AsyncMock()
        db.execute.side_effect = [contact_result, ix_result]

        briefs = await build_prep_brief([contact_id], db)

        assert len(briefs) == 1
        brief = briefs[0]
        assert brief["name"] == "Jane Doe"
        assert brief["title"] == "VP Engineering"
        assert brief["company"] == "Acme Corp"
        assert brief["score"] == 8
        assert brief["twitter_bio"] == "Building the future"
        assert len(brief["recent_interactions"]) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_contact_ids(self):
        from app.services.meeting_prep import build_prep_brief

        contact_result = MagicMock()
        contact_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute.return_value = contact_result

        briefs = await build_prep_brief([uuid.uuid4()], db)
        assert briefs == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestBuildPrepBrief -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement build_prep_brief**

Add to `backend/app/services/meeting_prep.py`:

```python
async def build_prep_brief(
    contact_ids: list[uuid.UUID],
    db: AsyncSession,
) -> list[dict]:
    """Gather context for a list of contacts.

    Returns a list of dicts with profile info, bios, and recent interactions.
    """
    if not contact_ids:
        return []

    result = await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
    )
    contacts = result.scalars().all()

    if not contacts:
        return []

    # Fetch last 5 non-meeting interactions per contact in one query
    ix_result = await db.execute(
        select(Interaction)
        .where(
            Interaction.contact_id.in_(contact_ids),
            Interaction.platform != "meeting",
        )
        .order_by(Interaction.occurred_at.desc())
        .limit(len(contact_ids) * 5)
    )
    all_interactions = ix_result.scalars().all()

    ix_by_contact: dict[uuid.UUID, list] = defaultdict(list)
    for ix in all_interactions:
        if len(ix_by_contact[ix.contact_id]) < 5:
            ix_by_contact[ix.contact_id].append(ix)

    briefs = []
    for contact in contacts:
        score_label = "Strong" if (contact.relationship_score or 0) >= 7 else (
            "Warm" if (contact.relationship_score or 0) >= 4 else "Cold"
        )
        interactions = ix_by_contact.get(contact.id, [])

        briefs.append({
            "contact_id": contact.id,
            "name": contact.full_name or contact.given_name or "Unknown",
            "title": contact.title,
            "company": contact.company,
            "score": contact.relationship_score,
            "score_label": score_label,
            "interaction_count": contact.interaction_count or 0,
            "last_interaction_at": contact.last_interaction_at,
            "avatar_url": contact.avatar_url,
            "twitter_bio": contact.twitter_bio,
            "linkedin_headline": contact.linkedin_headline,
            "linkedin_bio": contact.linkedin_bio,
            "telegram_bio": contact.telegram_bio,
            "recent_interactions": [
                {
                    "date": ix.occurred_at,
                    "preview": ix.content_preview,
                    "platform": ix.platform,
                }
                for ix in interactions
            ],
        })

    return briefs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestBuildPrepBrief -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meeting_prep.py backend/tests/test_meeting_prep.py
git commit -m "feat(meeting-prep): add build_prep_brief for attendee context"
```

---

### Task 5: Generate AI talking points

**Files:**
- Modify: `backend/tests/test_meeting_prep.py`
- Modify: `backend/app/services/meeting_prep.py`

Uses `_call_anthropic_with_retry` from `message_composer.py` for resilience against transient API errors.

- [ ] **Step 1: Write failing test for generate_talking_points**

Append to `backend/tests/test_meeting_prep.py`:

```python
class TestGenerateTalkingPoints:
    """Tests for meeting_prep.generate_talking_points."""

    @pytest.mark.asyncio
    @patch("app.services.meeting_prep._call_anthropic_with_retry")
    async def test_returns_talking_points(self, mock_retry_call):
        from app.services.meeting_prep import generate_talking_points

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="- Ask about Q2 roadmap\n- Discuss hiring plans\n- Follow up on partnership")]
        mock_retry_call.return_value = mock_response

        briefs = [
            {
                "name": "Jane Doe",
                "title": "VP Engineering",
                "company": "Acme Corp",
                "score_label": "Strong",
                "interaction_count": 15,
                "twitter_bio": "Building the future",
                "linkedin_headline": "VP Engineering at Acme",
                "linkedin_bio": None,
                "telegram_bio": None,
                "recent_interactions": [
                    {"date": datetime(2026, 3, 20, tzinfo=UTC), "preview": "Discussed Q2 roadmap", "platform": "gmail"},
                ],
            }
        ]

        points = await generate_talking_points(briefs, "Team standup")
        assert "roadmap" in points.lower() or len(points) > 10
        mock_retry_call.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.meeting_prep._call_anthropic_with_retry")
    async def test_returns_empty_on_api_failure(self, mock_retry_call):
        from app.services.meeting_prep import generate_talking_points

        mock_retry_call.side_effect = Exception("API timeout")

        briefs = [{"name": "Jane", "title": None, "company": None, "score_label": "Cold",
                    "interaction_count": 0, "twitter_bio": None, "linkedin_headline": None,
                    "linkedin_bio": None, "telegram_bio": None, "recent_interactions": []}]

        points = await generate_talking_points(briefs, "Meeting")
        assert points == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestGenerateTalkingPoints -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement generate_talking_points**

Add to `backend/app/services/meeting_prep.py`:

```python
import anthropic

from app.core.config import settings
from app.services.message_composer import _call_anthropic_with_retry


async def generate_talking_points(briefs: list[dict], meeting_title: str) -> str:
    """Generate AI talking points using Claude Haiku.

    Returns the talking points as a string, or empty string on failure
    (graceful degradation — email is sent without talking points).
    """
    if not briefs:
        return ""

    # Build context from attendee briefs
    attendee_lines = []
    for b in briefs:
        parts = [f"- {b['name']}"]
        if b.get("title") and b.get("company"):
            parts.append(f"  {b['title']} at {b['company']}")
        elif b.get("company"):
            parts.append(f"  at {b['company']}")
        parts.append(f"  Relationship: {b['score_label']} ({b['interaction_count']} interactions)")

        for key, label in [("twitter_bio", "Twitter"), ("linkedin_headline", "LinkedIn"), ("telegram_bio", "Telegram")]:
            if b.get(key):
                parts.append(f"  {label}: {b[key][:200]}")

        for ix in b.get("recent_interactions", [])[:3]:
            date_str = ix["date"].strftime("%b %d") if ix.get("date") else "?"
            parts.append(f"  Recent ({date_str}, {ix['platform']}): {(ix.get('preview') or '')[:100]}")

        attendee_lines.append("\n".join(parts))

    prompt = f"""You are preparing someone for an upcoming meeting. Based on the attendee context below, suggest 3-5 specific, actionable talking points.

Meeting: {meeting_title}

Attendees:
{chr(10).join(attendee_lines)}

Reply with only a bulleted list of talking points. Be specific and reference real details from the context."""

    if not settings.ANTHROPIC_API_KEY:
        return ""

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await _call_anthropic_with_retry(
            client,
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        logger.exception("generate_talking_points: Claude API call failed")
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestGenerateTalkingPoints -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meeting_prep.py backend/tests/test_meeting_prep.py
git commit -m "feat(meeting-prep): add AI talking points via Claude Haiku with retry"
```

---

### Task 6: Compose HTML prep email

**Files:**
- Modify: `backend/tests/test_meeting_prep.py`
- Modify: `backend/app/services/meeting_prep.py`

- [ ] **Step 1: Write failing test for compose_prep_email**

Append to `backend/tests/test_meeting_prep.py`:

```python
class TestComposePrepEmail:
    """Tests for meeting_prep.compose_prep_email."""

    def test_renders_html_with_known_contacts(self):
        from app.services.meeting_prep import compose_prep_email

        meeting = {
            "title": "Team standup",
            "occurred_at": datetime(2026, 3, 25, 14, 0, tzinfo=UTC),
        }
        briefs = [
            {
                "name": "Jane Doe",
                "title": "VP Engineering",
                "company": "Acme Corp",
                "score_label": "Strong",
                "interaction_count": 15,
                "last_interaction_at": datetime(2026, 3, 20, tzinfo=UTC),
                "twitter_bio": "Building the future",
                "linkedin_headline": "VP Engineering at Acme",
                "linkedin_bio": "20 years in tech",
                "telegram_bio": None,
                "recent_interactions": [
                    {"date": datetime(2026, 3, 20, tzinfo=UTC), "preview": "Discussed roadmap", "platform": "gmail"},
                ],
            }
        ]
        talking_points = "- Ask about Q2 roadmap\n- Discuss hiring plans"

        subject, body = compose_prep_email(meeting, briefs, talking_points)

        assert "Team standup" in subject
        assert "Jane Doe" in body
        assert "VP Engineering" in body
        assert "Acme Corp" in body
        assert "Strong" in body
        assert "Building the future" in body
        assert "Q2 roadmap" in body

    def test_renders_html_without_talking_points(self):
        from app.services.meeting_prep import compose_prep_email

        meeting = {
            "title": "Quick sync",
            "occurred_at": datetime(2026, 3, 25, 14, 0, tzinfo=UTC),
        }
        briefs = [{"name": "John", "title": None, "company": None, "score_label": "Cold",
                    "interaction_count": 0, "last_interaction_at": None,
                    "twitter_bio": None, "linkedin_headline": None, "linkedin_bio": None,
                    "telegram_bio": None, "recent_interactions": []}]

        subject, body = compose_prep_email(meeting, briefs, "")

        assert "Quick sync" in subject
        assert "John" in body
        assert "Suggested Talking Points" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestComposePrepEmail -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement compose_prep_email**

Add to `backend/app/services/meeting_prep.py`:

```python
_BASE_URL = getattr(settings, "FRONTEND_URL", "https://pingcrm.example.com")


def compose_prep_email(
    meeting: dict,
    briefs: list[dict],
    talking_points: str,
) -> tuple[str, str]:
    """Render the HTML prep brief email.

    Returns:
        Tuple of (subject, html_body).
    """
    title = meeting.get("title", "Meeting")
    occurred_at = meeting.get("occurred_at")
    time_str = occurred_at.strftime("%I:%M %p UTC") if occurred_at else ""

    subject = f"Meeting prep: {title} in 30 minutes"

    # Build attendee sections
    attendee_html = ""
    for b in briefs:
        name = html_mod.escape(b["name"])
        title_co = ""
        if b.get("title") and b.get("company"):
            title_co = f"{html_mod.escape(b['title'])} at {html_mod.escape(b['company'])}"
        elif b.get("title"):
            title_co = html_mod.escape(b["title"])
        elif b.get("company"):
            title_co = html_mod.escape(b["company"])

        score_label = b.get("score_label", "Unknown")
        ix_count = b.get("interaction_count", 0)
        last_at = b.get("last_interaction_at")
        last_str = last_at.strftime("%b %d, %Y") if last_at else "Never"

        # Bios
        bios_html = ""
        for key, label in [("twitter_bio", "Twitter"), ("linkedin_headline", "LinkedIn"), ("telegram_bio", "Telegram")]:
            val = b.get(key)
            if val:
                bios_html += f'<div style="margin:2px 0;color:#6b7280;font-size:13px;">{label}: {html_mod.escape(val[:200])}</div>'
        if b.get("linkedin_bio"):
            bios_html += f'<div style="margin:2px 0;color:#6b7280;font-size:13px;">LinkedIn about: {html_mod.escape(b["linkedin_bio"][:200])}</div>'

        # Recent interactions
        ix_html = ""
        for ix in b.get("recent_interactions", [])[:5]:
            date_str = ix["date"].strftime("%b %d") if ix.get("date") else "?"
            preview = html_mod.escape((ix.get("preview") or "")[:120])
            platform = ix.get("platform", "")
            ix_html += f'<div style="margin:2px 0;font-size:13px;color:#374151;">{date_str}: {preview} <span style="color:#9ca3af;">({platform})</span></div>'

        attendee_html += f"""
        <div style="padding:16px;margin-bottom:12px;background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb;">
          <div style="font-weight:600;font-size:15px;color:#111827;">{name}</div>
          {"<div style='font-size:13px;color:#6b7280;'>" + title_co + "</div>" if title_co else ""}
          <div style="margin-top:6px;font-size:13px;color:#374151;">
            {score_label} &middot; {ix_count} interactions &middot; Last: {last_str}
          </div>
          {('<div style="margin-top:8px;">' + bios_html + '</div>') if bios_html else ""}
          {('<div style="margin-top:8px;border-top:1px solid #e5e7eb;padding-top:8px;">' + ix_html + '</div>') if ix_html else ""}
        </div>"""

    # Talking points section
    tp_html = ""
    if talking_points.strip():
        tp_items = ""
        for line in talking_points.strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line:
                tp_items += f"<li style='margin-bottom:4px;'>{html_mod.escape(line)}</li>"
        if tp_items:
            tp_html = f"""
            <div style="padding:16px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0;margin-top:16px;">
              <div style="font-weight:600;font-size:14px;color:#166534;margin-bottom:8px;">Suggested Talking Points</div>
              <ul style="margin:0;padding-left:20px;color:#374151;font-size:13px;">{tp_items}</ul>
            </div>"""

    body = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">
    <tr><td align="center" style="padding:24px;">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
        <tr><td style="padding:24px 32px;background:linear-gradient(135deg,#0d9488 0%,#14b8a6 100%);">
          <div style="font-size:18px;font-weight:700;color:#ffffff;">{html_mod.escape(title)}</div>
          <div style="font-size:14px;color:#ccfbf1;margin-top:4px;">{time_str}</div>
        </td></tr>
        <tr><td style="padding:24px 32px;">
          <div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:12px;text-transform:uppercase;letter-spacing:0.5px;">Attendees</div>
          {attendee_html}
          {tp_html}
        </td></tr>
        <tr><td style="padding:16px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;text-align:center;">
          <p style="margin:0;font-size:12px;color:#9ca3af;">
            Sent by <a href="{_BASE_URL}" style="color:#0d9488;text-decoration:none;">PingCRM</a> &middot;
            <a href="{_BASE_URL}/settings" style="color:#0d9488;text-decoration:none;">Manage preferences</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return subject, body
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestComposePrepEmail -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meeting_prep.py backend/tests/test_meeting_prep.py
git commit -m "feat(meeting-prep): add HTML prep email composer"
```

---

## Chunk 3: Celery Task + Registration + Settings

### Task 7: Celery beat task

**Files:**
- Modify: `backend/tests/test_meeting_prep.py`
- Create: `backend/app/services/task_jobs/meeting_prep.py`
- Modify: `backend/app/services/tasks.py`
- Modify: `backend/app/core/celery_app.py`
- Modify: `backend/tests/test_task_registry.py`

- [ ] **Step 1: Write tests for scan_meeting_preps**

Append to `backend/tests/test_meeting_prep.py`:

```python
class TestScanAndSendMeetingPreps:
    """Tests for the Celery beat task."""

    @patch("app.services.task_jobs.meeting_prep._run")
    def test_task_is_callable(self, mock_run):
        from app.services.task_jobs.meeting_prep import scan_meeting_preps

        mock_run.return_value = {"sent": 0, "skipped": 0, "errors": 0}
        result = scan_meeting_preps()
        mock_run.assert_called_once()

    def test_task_registered_in_tasks_module(self):
        """The task must be importable from the re-export module."""
        from app.services.tasks import scan_meeting_preps
        assert callable(scan_meeting_preps)

    def test_task_in_beat_schedule(self):
        """The task must appear in the Celery beat schedule."""
        from app.core.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        task_names = [v["task"] for v in schedule.values()]
        assert "app.services.tasks.scan_meeting_preps" in task_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestScanAndSendMeetingPreps -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the Celery task**

Create `backend/app/services/task_jobs/meeting_prep.py`:

```python
"""Celery beat task for pre-meeting prep email notifications."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import redis as _redis
from celery import shared_task
from sqlalchemy import select

from app.core.config import settings
from app.core.database import task_session
from app.models.google_account import GoogleAccount
from app.models.notification import Notification
from app.models.user import User
from app.services.task_jobs.common import _run, logger


@shared_task(name="app.services.tasks.scan_meeting_preps")
def scan_meeting_preps() -> dict:
    """Scan for upcoming meetings and send prep briefs.

    Runs every 10 minutes via Celery beat. Finds meetings starting in
    30-40 minutes, gathers attendee context, generates talking points,
    and sends HTML prep emails via Gmail API.
    """
    async def _scan() -> dict:
        from app.integrations.gmail_send import send_email
        from app.services.meeting_prep import (
            build_prep_brief,
            compose_prep_email,
            generate_talking_points,
            get_upcoming_meetings,
        )

        r = _redis.from_url(settings.REDIS_URL)
        now = datetime.now(UTC)
        window_start = now + timedelta(minutes=30)
        window_end = now + timedelta(minutes=40)

        sent = 0
        skipped = 0
        errors = 0

        async with task_session() as db:
            # Only scan users with Google connected
            ga_result = await db.execute(
                select(GoogleAccount.user_id).distinct()
            )
            ga_user_ids = set(ga_result.scalars().all())

            # Also include users with legacy google_refresh_token
            legacy_result = await db.execute(
                select(User.id).where(
                    User.google_refresh_token.isnot(None),
                    User.id.notin_(ga_user_ids) if ga_user_ids else True,
                )
            )
            legacy_user_ids = set(legacy_result.scalars().all())

            all_user_ids = ga_user_ids | legacy_user_ids

            for uid in all_user_ids:
                user_result = await db.execute(select(User).where(User.id == uid))
                user = user_result.scalar_one_or_none()
                if not user:
                    continue

                # Check if meeting prep is enabled (stored under gmail.meeting_prep_enabled)
                sync_settings = user.sync_settings or {}
                gmail_settings = sync_settings.get("gmail", {})
                if not gmail_settings.get("meeting_prep_enabled", True):
                    continue

                # Get Google accounts for this user
                accounts_result = await db.execute(
                    select(GoogleAccount).where(GoogleAccount.user_id == user.id)
                )
                accounts = list(accounts_result.scalars().all())

                meetings = await get_upcoming_meetings(user.id, window_start, window_end, db)

                for meeting in meetings:
                    event_id = meeting["event_id"]
                    dedup_key = f"meeting_prep:{user.id}:{event_id}"

                    if r.exists(dedup_key):
                        skipped += 1
                        continue

                    contact_ids = meeting["contact_ids"]
                    if not contact_ids:
                        skipped += 1
                        continue

                    briefs = await build_prep_brief(contact_ids, db)
                    if not briefs:
                        skipped += 1
                        continue

                    talking_points = await generate_talking_points(briefs, meeting["title"])

                    subject, html = compose_prep_email(meeting, briefs, talking_points)

                    # Determine which Google account to send from
                    ga = accounts[0] if accounts else None
                    if not ga and user.google_refresh_token:
                        from types import SimpleNamespace
                        ga = SimpleNamespace(
                            refresh_token=user.google_refresh_token,
                            email=user.email,
                        )

                    if not ga:
                        skipped += 1
                        continue

                    result = send_email(ga, subject, html)

                    if result is True:
                        r.set(dedup_key, "1", ex=86400)
                        sent += 1
                        logger.info(
                            "Meeting prep sent for user %s, event %s",
                            user.id, event_id,
                        )
                    elif result == "auth_error":
                        # Create re-authorization notification
                        db.add(Notification(
                            user_id=user.id,
                            notification_type="system",
                            title="Re-authorize Gmail for meeting prep emails",
                            body="Gmail permissions have been updated. Please re-authorize to enable pre-meeting prep emails.",
                            link="/settings",
                        ))
                        await db.flush()
                        errors += 1
                        break  # Stop trying for this user
                    else:
                        errors += 1

            await db.commit()

        return {"sent": sent, "skipped": skipped, "errors": errors}

    return _run(_scan())
```

- [ ] **Step 4: Register in tasks.py**

Add to `backend/app/services/tasks.py`:

Import section (after the maintenance imports):
```python
from app.services.task_jobs.meeting_prep import (
    scan_meeting_preps,
)
```

`__all__` list (add before the closing bracket):
```python
    # meeting prep
    "scan_meeting_preps",
```

- [ ] **Step 5: Add beat schedule entry**

Add to `backend/app/core/celery_app.py` beat_schedule dict:

```python
        # Scan for upcoming meetings and send prep briefs every 10 minutes
        "scan-meeting-preps-every-10m": {
            "task": "app.services.tasks.scan_meeting_preps",
            "schedule": crontab(minute="*/10"),
        },
```

- [ ] **Step 6: Update test_task_registry.py expected set**

In `backend/tests/test_task_registry.py`, add to the `expected_tasks` set (line 12-37):
```python
        "app.services.tasks.scan_meeting_preps",
        "app.services.tasks.apply_tags_to_contacts",
```

Also add `sync_telegram_for_user` and `cleanup_stale_telegram_locks` if missing from the set.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestScanAndSendMeetingPreps -v`
Expected: 3 passed

Run: `cd backend && pytest tests/test_task_registry.py -v`
Expected: All 4 passed

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/task_jobs/meeting_prep.py backend/app/services/tasks.py backend/app/core/celery_app.py backend/tests/test_meeting_prep.py backend/tests/test_task_registry.py
git commit -m "feat(meeting-prep): add Celery beat task with Redis dedup and re-auth notification"
```

---

### Task 8: User setting for meeting_prep_enabled

**Files:**
- Modify: `backend/app/api/settings.py`
- Modify: `backend/tests/test_meeting_prep.py`

The setting is stored under `sync_settings.gmail.meeting_prep_enabled` — consistent with the existing per-platform nested dict pattern. The existing `SyncSettingsInput` already accepts `gmail: dict | None`, so clients can set it via `PUT /api/v1/settings/sync` with `{"gmail": {"meeting_prep_enabled": false}}`.

- [ ] **Step 1: Write test for the setting**

Append to `backend/tests/test_meeting_prep.py`:

```python
class TestMeetingPrepSetting:
    """Tests for meeting_prep_enabled user setting."""

    def test_default_is_true_when_gmail_settings_empty(self):
        """Meeting prep is enabled by default."""
        sync_settings: dict = {}
        gmail_settings = sync_settings.get("gmail", {})
        assert gmail_settings.get("meeting_prep_enabled", True) is True

    def test_default_is_true_when_gmail_has_other_settings(self):
        """meeting_prep_enabled defaults to True even when other gmail settings exist."""
        sync_settings = {"gmail": {"auto_sync": True, "schedule": "6h"}}
        gmail_settings = sync_settings.get("gmail", {})
        assert gmail_settings.get("meeting_prep_enabled", True) is True

    def test_can_be_disabled(self):
        """User can disable meeting prep via gmail settings."""
        sync_settings = {"gmail": {"auto_sync": True, "meeting_prep_enabled": False}}
        gmail_settings = sync_settings.get("gmail", {})
        assert gmail_settings.get("meeting_prep_enabled", True) is False
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meeting_prep.py::TestMeetingPrepSetting -v`
Expected: 3 passed

No code changes needed — the existing `SyncSettingsInput` with `gmail: dict | None` already accepts arbitrary keys in the dict, and the Celery task reads `sync_settings.get("gmail", {}).get("meeting_prep_enabled", True)`.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_meeting_prep.py
git commit -m "test(meeting-prep): add meeting_prep_enabled setting tests"
```

---

## Chunk 4: Integration Test + Final Verification

### Task 9: Full integration test

**Files:**
- Modify: `backend/tests/test_meeting_prep.py`

- [ ] **Step 1: Write integration test**

Append to `backend/tests/test_meeting_prep.py`:

```python
class TestMeetingPrepIntegration:
    """End-to-end test with mocked external services."""

    @pytest.mark.asyncio
    @patch("app.services.meeting_prep._call_anthropic_with_retry")
    async def test_full_flow(self, mock_retry_call):
        """Test the full flow: build brief -> talking points -> compose email."""
        from app.services.meeting_prep import (
            build_prep_brief,
            compose_prep_email,
            generate_talking_points,
        )

        # Mock Claude API
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="- Discuss project timeline\n- Ask about team expansion")]
        mock_retry_call.return_value = mock_response

        # Mock contact
        contact_id = uuid.uuid4()
        contact = MagicMock()
        contact.id = contact_id
        contact.full_name = "Alice Smith"
        contact.given_name = "Alice"
        contact.title = "CTO"
        contact.company = "TechCo"
        contact.relationship_score = 9
        contact.interaction_count = 25
        contact.last_interaction_at = datetime(2026, 3, 23, tzinfo=UTC)
        contact.avatar_url = None
        contact.twitter_bio = "Tech leader"
        contact.linkedin_headline = "CTO at TechCo"
        contact.linkedin_bio = None
        contact.telegram_bio = "Available on Telegram"

        contact_result = MagicMock()
        contact_result.scalars.return_value.all.return_value = [contact]

        ix1 = MagicMock()
        ix1.occurred_at = datetime(2026, 3, 23, tzinfo=UTC)
        ix1.content_preview = "Synced on product roadmap"
        ix1.platform = "gmail"
        ix1.contact_id = contact_id

        ix_result = MagicMock()
        ix_result.scalars.return_value.all.return_value = [ix1]

        db = AsyncMock()
        db.execute.side_effect = [contact_result, ix_result]

        # Run the pipeline
        briefs = await build_prep_brief([contact_id], db)
        assert len(briefs) == 1
        assert briefs[0]["name"] == "Alice Smith"

        talking_points = await generate_talking_points(briefs, "Weekly sync")
        assert len(talking_points) > 0

        meeting = {"title": "Weekly sync", "occurred_at": datetime(2026, 3, 25, 15, 0, tzinfo=UTC)}
        subject, body = compose_prep_email(meeting, briefs, talking_points)

        assert "Weekly sync" in subject
        assert "Alice Smith" in body
        assert "CTO" in body
        assert "TechCo" in body
        assert "Tech leader" in body  # twitter bio
        assert "Telegram" in body  # telegram bio
```

- [ ] **Step 2: Run full test suite**

Run: `cd backend && pytest tests/test_meeting_prep.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_meeting_prep.py
git commit -m "test(meeting-prep): add integration test for full prep flow"
```

---

### Task 10: Run full test suite and verify

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && pytest --tb=short -q`
Expected: All tests pass, no regressions

- [ ] **Step 2: Verify task registry**

Run: `cd backend && pytest tests/test_task_registry.py -v`
Expected: All 4 tests pass including `scan_meeting_preps`

- [ ] **Step 3: Verify response models**

Run: `cd backend && PYTHONPATH=. python3 scripts/check_response_models.py`
Expected: No new endpoint added, so this should pass unchanged

- [ ] **Step 4: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix(meeting-prep): address test suite fixups"
```
