from datetime import UTC, datetime
from unittest.mock import patch

from app.services.meeting_prep_email import compose_prep_email

_MEETING = {
    "event_id": "evt789",
    "title": "Instance links",
    "occurred_at": datetime(2026, 4, 3, 9, 0, tzinfo=UTC),
    "contact_ids": [],
}


def test_links_point_at_configured_frontend_url():
    with patch("app.services.meeting_prep_email.settings") as mock_settings:
        mock_settings.FRONTEND_URL = "https://crm.self-hosted.test"
        _, html = compose_prep_email(_MEETING, [], "")

    assert 'href="https://crm.self-hosted.test"' in html
    assert 'href="https://crm.self-hosted.test/settings"' in html
    assert "sawinyh" not in html


def test_frontend_url_defaults_to_localhost():
    from app.core.config import Settings

    assert Settings.model_fields["FRONTEND_URL"].default == "http://localhost:3000"
