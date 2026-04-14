"""Extended tests for the message composer service.

Covers compose_followup_message with:
- Contact not found -> ValueError
- No API key (Anthropic raises AuthenticationError)
- Successful mocked API call returns trimmed text
- Correct model and max_tokens passed to Anthropic
- All three trigger types (time_based, event_based, scheduled)
- event_based trigger includes event summary in the prompt
- Formal tone reflected in the prompt
- Casual tone reflected in the prompt
- Contact name present in the prompt
- Contact with no given_name falls back to first token of full_name
- Contact with no company or title still produces a result
- Preferred channel derived from interactions
- No interactions defaults preferred channel to email
- analyze_conversation_tone edge cases (boundary 40%, all-None content,
  outbound direction)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.services.message_composer import (
    analyze_conversation_tone,
    compose_followup_message,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_interaction(
    content: str | None,
    direction: str = "inbound",
    platform: str = "email",
    days_ago: int = 5,
) -> MagicMock:
    """Build a MagicMock Interaction."""
    ix = MagicMock(spec=Interaction)
    ix.content_preview = content
    ix.direction = direction
    ix.platform = platform
    ix.occurred_at = datetime.now(UTC) - timedelta(days=days_ago)
    return ix


def _make_contact(
    contact_id: uuid.UUID | None = None,
    full_name: str = "Jane Smith",
    given_name: str | None = "Jane",
    company: str | None = "Acme Corp",
    title: str | None = "CTO",
    relationship_score: int = 7,
    last_interaction_at: datetime | None = None,
    twitter_handle: str | None = None,
    twitter_bio: str | None = None,
    telegram_bio: str | None = None,
) -> MagicMock:
    """Build a MagicMock Contact."""
    c = MagicMock(spec=Contact)
    c.id = contact_id or uuid.uuid4()
    c.full_name = full_name
    c.given_name = given_name
    c.company = company
    c.title = title
    c.relationship_score = relationship_score
    c.last_interaction_at = last_interaction_at or datetime.now(UTC) - timedelta(days=90)
    c.twitter_handle = twitter_handle
    c.twitter_bio = twitter_bio
    c.telegram_bio = telegram_bio
    return c


def _mock_anthropic_response(text: str) -> MagicMock:
    """Build a MagicMock that looks like an anthropic.Message response."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_db() -> AsyncMock:
    """Provide a fully mocked AsyncSession that never hits the DB."""
    return AsyncMock(spec=AsyncSession)


def _configure_db(
    mock_db: AsyncMock,
    contact: MagicMock | None,
    interactions: list[MagicMock] | None = None,
) -> None:
    """Wire mock_db.execute for the two sequential calls made by compose_followup_message."""
    interactions = interactions or []

    contact_result = MagicMock()
    contact_result.scalar_one_or_none.return_value = contact

    interaction_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = interactions
    interaction_result.scalars.return_value = scalars_mock

    mock_db.execute = AsyncMock(side_effect=[contact_result, interaction_result])


# ---------------------------------------------------------------------------
# Tests that already exist in this file (kept for completeness)
# — The originals use a real DB session; these use fully mocked sessions
#   so they run without a database connection.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compose_followup_message_contact_not_found_mocked(mock_db: AsyncMock):
    """When the contact query returns None a ValueError is raised."""
    contact_result = MagicMock()
    contact_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=contact_result)

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic"):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        with pytest.raises(ValueError, match="not found"):
            await compose_followup_message(
                contact_id=uuid.uuid4(),
                trigger_type="time_based",
                event_summary=None,
                db=mock_db,
            )


# ---------------------------------------------------------------------------
# No API key — client raises authentication error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compose_followup_no_api_key_returns_fallback(mock_db: AsyncMock):
    """When ANTHROPIC_API_KEY is empty, the composer returns a fallback message."""
    contact = _make_contact()
    _configure_db(mock_db, contact, [])

    with patch("app.services.message_composer.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = ""

        result = await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )
    assert "Jane" in result
    assert "check in" in result.lower()


@pytest.mark.asyncio
async def test_compose_followup_empty_api_key_skips_anthropic(mock_db: AsyncMock):
    """When ANTHROPIC_API_KEY is empty, Anthropic client is never instantiated."""
    contact = _make_contact()
    _configure_db(mock_db, contact, [])

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic") as mock_ctor:
        mock_settings.ANTHROPIC_API_KEY = ""

        result = await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    mock_ctor.assert_not_called()
    assert "Jane" in result


# ---------------------------------------------------------------------------
# Successful API call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compose_followup_success_returns_stripped_text(mock_db: AsyncMock):
    """Result is the trimmed content[0].text from the API response."""
    contact = _make_contact()
    _configure_db(mock_db, contact, [])

    expected = "Hi Jane, hope things are going well!"
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response(f"\n  {expected}\n"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        result = await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    assert result == expected


@pytest.mark.asyncio
async def test_compose_followup_uses_correct_model_and_token_limit(mock_db: AsyncMock):
    """Anthropic messages.create must use claude-sonnet-4-20250514 with max_tokens=200."""
    contact = _make_contact()
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("ok"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-20250514"
    assert kwargs["max_tokens"] == 200


# ---------------------------------------------------------------------------
# Trigger-type variations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type,event_summary", [
    ("time_based", None),
    ("event_based", "Jane announced a new product launch."),
    ("scheduled", None),
])
async def test_compose_followup_all_trigger_types(
    mock_db: AsyncMock,
    trigger_type: str,
    event_summary: str | None,
):
    """All trigger types complete without error and return a non-empty string."""
    contact = _make_contact()
    _configure_db(mock_db, contact, [])

    text = f"Message for {trigger_type}."
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response(text))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        result = await compose_followup_message(
            contact_id=contact.id,
            trigger_type=trigger_type,
            event_summary=event_summary,
            db=mock_db,
        )

    assert result == text


@pytest.mark.asyncio
async def test_compose_followup_event_based_includes_summary_in_prompt(mock_db: AsyncMock):
    """For event_based triggers the event_summary must appear in the API prompt."""
    contact = _make_contact()
    _configure_db(mock_db, contact, [])

    event_summary = "Jane was promoted to VP of Engineering."
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Congrats!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="event_based",
            event_summary=event_summary,
            db=mock_db,
        )

    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert event_summary in prompt


# ---------------------------------------------------------------------------
# Tone settings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compose_followup_formal_tone_in_prompt(mock_db: AsyncMock):
    """Formal interactions produce a prompt containing the word 'formal'."""
    contact = _make_contact()
    formal_interactions = [
        _make_interaction("Dear Jane, please find the proposal attached."),
        _make_interaction("We appreciate your prompt response."),
        _make_interaction("Kindly review the documentation at your earliest convenience."),
    ]
    _configure_db(mock_db, contact, formal_interactions)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Formal reply."))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "formal" in prompt.lower()


@pytest.mark.asyncio
async def test_compose_followup_casual_tone_in_prompt(mock_db: AsyncMock):
    """Casual interactions produce a prompt containing the word 'casual'."""
    contact = _make_contact()
    casual_interactions = [
        _make_interaction("hey! great to hear from you :)"),
        _make_interaction("lol yeah that was awesome"),
        _make_interaction("thx for the intro!"),
        _make_interaction("btw, check out this article"),
        _make_interaction("hey hey! how's it going?"),
    ]
    _configure_db(mock_db, contact, casual_interactions)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Casual reply."))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "casual" in prompt.lower()


# ---------------------------------------------------------------------------
# Contact context in prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compose_followup_contact_first_name_in_prompt(mock_db: AsyncMock):
    """The contact's first name must appear in the constructed prompt."""
    contact = _make_contact(full_name="Alice Wonderland", given_name="Alice")
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Hi Alice!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="scheduled",
            event_summary=None,
            db=mock_db,
        )

    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Alice" in prompt


@pytest.mark.asyncio
async def test_compose_followup_no_given_name_uses_first_token_of_full_name(mock_db: AsyncMock):
    """When given_name is None the first word of full_name is used as the first name."""
    contact = _make_contact(full_name="Robert Tables", given_name=None)
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Hi Robert!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        result = await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    assert result == "Hi Robert!"
    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Robert" in prompt


@pytest.mark.asyncio
async def test_compose_followup_no_company_no_title(mock_db: AsyncMock):
    """A contact without a company or title should still generate a message without error."""
    contact = _make_contact(company=None, title=None)
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Hey Jane!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        result = await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    assert result == "Hey Jane!"


# ---------------------------------------------------------------------------
# Preferred channel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compose_followup_preferred_channel_from_most_recent_interaction(mock_db: AsyncMock):
    """The platform of the first (most-recent) interaction is used as preferred channel."""
    contact = _make_contact()
    interactions = [
        _make_interaction("hey!", platform="telegram"),
        _make_interaction("sounds good", platform="email"),
    ]
    _configure_db(mock_db, contact, interactions)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Hey!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "telegram" in prompt.lower()


@pytest.mark.asyncio
async def test_compose_followup_no_interactions_defaults_channel_to_email(mock_db: AsyncMock):
    """When there are no interactions, the preferred channel defaults to 'email'."""
    contact = _make_contact()
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Hey!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "email" in prompt.lower()


# ---------------------------------------------------------------------------
# analyze_conversation_tone — additional edge cases
# ---------------------------------------------------------------------------

def test_tone_boundary_exactly_40_percent_casual():
    """Exactly 40% casual messages is at the boundary and should return 'casual'."""
    # 2 out of 5 = 0.40 — should satisfy >= 0.4
    interactions = [
        _make_interaction("Hey! Great to hear from you."),
        _make_interaction("lol that was funny"),
        _make_interaction("Please review the attached proposal."),
        _make_interaction("We appreciate your timely response."),
        _make_interaction("The quarterly metrics look strong."),
    ]
    assert analyze_conversation_tone(interactions) == "casual"


def test_tone_boundary_just_below_40_percent():
    """Zero casual out of three (0%) is below the 40% threshold — result is 'formal'."""
    interactions = [
        _make_interaction("We appreciate the detailed proposal."),
        _make_interaction("Please send the invoice at your convenience."),
        _make_interaction("We look forward to the partnership."),
    ]
    assert analyze_conversation_tone(interactions) == "formal"


def test_tone_all_none_content_returns_formal():
    """When every interaction has None content, total_checked is 0 and tone is formal."""
    interactions: list[MagicMock] = []
    for _ in range(4):
        ix = MagicMock(spec=Interaction)
        ix.content_preview = None
        interactions.append(ix)
    assert analyze_conversation_tone(interactions) == "formal"


def test_tone_outbound_messages_counted_toward_tone():
    """Outbound messages with casual language should push the tone to 'casual'."""
    interactions = [
        _make_interaction("Hey! Awesome catch, thanks!", direction="outbound"),
        _make_interaction("lol yes definitely btw!", direction="outbound"),
        _make_interaction("cheers!", direction="outbound"),
    ]
    assert analyze_conversation_tone(interactions) == "casual"


def test_tone_single_casual_interaction():
    """A single casual interaction (100% >= 0.4) returns 'casual'."""
    interactions = [_make_interaction("hey, what's up?")]
    assert analyze_conversation_tone(interactions) == "casual"


def test_tone_single_formal_interaction():
    """A single formal interaction (0% < 0.4) returns 'formal'."""
    interactions = [_make_interaction("Please find the report enclosed.")]
    assert analyze_conversation_tone(interactions) == "formal"


# ---------------------------------------------------------------------------
# Twitter context enrichment
# ---------------------------------------------------------------------------

_FAKE_TWEETS = [
    {"text": "Excited to launch our new AI product!", "createdAt": "Sat Mar 01 12:00:00 +0000 2026"},
    {"text": "Great panel at TechConf today", "createdAt": "Fri Feb 28 09:00:00 +0000 2026"},
    {"text": "Hiring engineers — DM me", "createdAt": "Tue Feb 25 15:00:00 +0000 2026"},
]


@pytest.mark.asyncio
async def test_twitter_context_included_for_time_based(mock_db: AsyncMock):
    """For time_based triggers, recent tweets are fetched and included in the prompt."""
    contact = _make_contact(twitter_handle="janesmith", twitter_bio="CTO at Acme")
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Hey Jane!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client), \
         patch("app.services.message_composer._get_cached_tweets", new_callable=AsyncMock, return_value=_FAKE_TWEETS):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "RECENT TWITTER ACTIVITY" in prompt
    assert "Excited to launch our new AI product!" in prompt
    assert "CTO at Acme" in prompt


@pytest.mark.asyncio
async def test_twitter_context_skipped_for_event_based(mock_db: AsyncMock):
    """For event_based triggers, _get_cached_tweets is NOT called."""
    contact = _make_contact(twitter_handle="janesmith")
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Congrats!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client), \
         patch("app.services.message_composer._get_cached_tweets", new_callable=AsyncMock) as mock_fetch:
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="event_based",
            event_summary="Jane raised a Series A.",
            db=mock_db,
        )

    mock_fetch.assert_not_called()
    prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "RECENT TWITTER ACTIVITY" not in prompt


@pytest.mark.asyncio
async def test_twitter_context_skipped_no_handle(mock_db: AsyncMock):
    """Contact without twitter_handle — no Twitter API call made."""
    contact = _make_contact(twitter_handle=None)
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Hey Jane!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client), \
         patch("app.services.message_composer._get_cached_tweets", new_callable=AsyncMock) as mock_fetch:
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_twitter_fetch_failure_doesnt_block(mock_db: AsyncMock):
    """When _get_cached_tweets raises, message is still generated."""
    contact = _make_contact(twitter_handle="janesmith")
    _configure_db(mock_db, contact, [])

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response("Hey Jane!"))

    with patch("app.services.message_composer.settings") as mock_settings, \
         patch("anthropic.AsyncAnthropic", return_value=mock_client), \
         patch("app.services.message_composer._get_cached_tweets", new_callable=AsyncMock, side_effect=RuntimeError("CLI failed")):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"

        result = await compose_followup_message(
            contact_id=contact.id,
            trigger_type="time_based",
            event_summary=None,
            db=mock_db,
        )

    assert result == "Hey Jane!"


# ---------------------------------------------------------------------------
# _get_cached_tweets — Redis caching + bird CLI
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_cached_tweets_returns_from_redis_cache():
    """When Redis has cached tweets, bird CLI is not called."""
    import json
    from app.services.message_composer import _get_cached_tweets

    contact = _make_contact(twitter_handle="janesmith")

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(_FAKE_TWEETS))

    with patch("app.core.redis.get_redis", return_value=mock_redis), \
         patch("app.integrations.bird.fetch_user_tweets_bird", new_callable=AsyncMock) as mock_bird:

        result = await _get_cached_tweets(contact)

    assert result == _FAKE_TWEETS
    mock_bird.assert_not_called()


@pytest.mark.asyncio
async def test_get_cached_tweets_calls_bird_and_caches():
    """On cache miss, fetches via bird CLI and caches result in Redis."""
    import json
    from unittest.mock import MagicMock
    from app.services.message_composer import _get_cached_tweets, _TWEET_CACHE_TTL

    contact = _make_contact(twitter_handle="janesmith")
    mock_user = MagicMock()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)  # cache miss
    mock_redis.set = AsyncMock()

    with patch("app.core.redis.get_redis", return_value=mock_redis), \
         patch("app.services.bird_session.get_cookies", return_value=("tok", "ct0")), \
         patch("app.integrations.bird.fetch_user_tweets_bird", new_callable=AsyncMock, return_value=(_FAKE_TWEETS, None)):

        result = await _get_cached_tweets(contact, user=mock_user)

    assert result == _FAKE_TWEETS
    mock_redis.set.assert_called_once_with(
        "twitter_tweets:janesmith", json.dumps(_FAKE_TWEETS), ex=_TWEET_CACHE_TTL,
    )


@pytest.mark.asyncio
async def test_fetch_user_tweets_bird_parses_json():
    """bird CLI stdout is parsed correctly."""
    import json
    from app.integrations.bird import fetch_user_tweets_bird, BirdResult

    fake_output = json.dumps(_FAKE_TWEETS)

    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data=_FAKE_TWEETS, error=None)):
        result, err = await fetch_user_tweets_bird("janesmith", auth_token="x", ct0="y")

    assert err is None
    assert result == _FAKE_TWEETS


@pytest.mark.asyncio
async def test_fetch_user_tweets_bird_handles_dict_response():
    """bird CLI may return { tweets: [...], nextCursor: ... }."""
    from app.integrations.bird import fetch_user_tweets_bird, BirdResult

    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data={"tweets": _FAKE_TWEETS, "nextCursor": "abc"}, error=None)):
        result, err = await fetch_user_tweets_bird("janesmith", auth_token="x", ct0="y")

    assert err is None
    assert result == _FAKE_TWEETS


@pytest.mark.asyncio
async def test_fetch_user_tweets_bird_not_installed():
    """When bird CLI is not on PATH, returns empty list."""
    from app.integrations.bird import fetch_user_tweets_bird, BirdResult

    with patch("app.integrations.bird._run_bird", new_callable=AsyncMock, return_value=BirdResult(data=None, error="bird not found")):
        result, err = await fetch_user_tweets_bird("janesmith", auth_token="x", ct0="y")

    assert result == []
    assert err is not None
