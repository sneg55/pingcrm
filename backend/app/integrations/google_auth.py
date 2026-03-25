"""Google OAuth integration using google-auth-oauthlib."""
from __future__ import annotations

from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.core.config import settings

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

_CLIENT_CONFIG = {
    "web": {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
    }
}


def build_oauth_url(redirect_uri: str | None = None) -> tuple[str, str]:
    """Return (authorization_url, state) for the Google consent screen."""
    flow = Flow.from_client_config(_CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url, state


def exchange_code(code: str, redirect_uri: str | None = None) -> dict[str, Any]:
    """Exchange an authorization code for OAuth tokens.

    Returns a dict with keys: access_token, refresh_token, id_token, expiry.
    """
    flow = Flow.from_client_config(_CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI
    flow.fetch_token(code=code)
    credentials: Credentials = flow.credentials
    return {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "id_token": credentials.id_token,
        "expiry": credentials.expiry,
    }


def refresh_access_token(refresh_token: str) -> str:
    """Use a stored refresh token to obtain a fresh access token.

    Returns the new access token string.
    """
    import google.auth.transport.requests as google_requests

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )
    request = google_requests.Request()
    credentials.refresh(request)
    return credentials.token  # type: ignore[return-value]
