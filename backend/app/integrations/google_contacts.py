"""Google Contacts one-way sync using the People API."""
from __future__ import annotations

from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.core.config import settings


def _build_people_service(access_token: str) -> Any:
    credentials = Credentials(
        token=access_token,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("people", "v1", credentials=credentials, cache_discovery=False)


def _extract_contact_fields(person: dict[str, Any]) -> dict[str, Any]:
    """Map a Google People API person resource to our Contact model fields."""
    names = person.get("names", [])
    given_name: str | None = None
    family_name: str | None = None
    full_name: str | None = None
    if names:
        primary = names[0]
        given_name = primary.get("givenName")
        family_name = primary.get("familyName")
        full_name = primary.get("displayName")

    email_addresses = person.get("emailAddresses", [])
    emails: list[str] = [
        e["value"] for e in email_addresses if e.get("value")
    ]

    phone_numbers = person.get("phoneNumbers", [])
    phones: list[str] = [
        p["value"] for p in phone_numbers if p.get("value")
    ]

    organizations = person.get("organizations", [])
    company: str | None = None
    title: str | None = None
    if organizations:
        org = organizations[0]
        company = org.get("name")
        title = org.get("title")

    return {
        "full_name": full_name,
        "given_name": given_name,
        "family_name": family_name,
        "emails": emails or None,
        "phones": phones or None,
        "company": company,
        "title": title,
        "source": "google",
    }


def fetch_google_contacts(access_token: str) -> list[dict[str, Any]]:
    """Fetch all connections from the authenticated user's Google account.

    Returns a list of mapped contact field dicts ready to be merged into the DB.
    """
    service = _build_people_service(access_token)
    contacts: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        kwargs: dict[str, Any] = {
            "resourceName": "people/me",
            "pageSize": 1000,
            "personFields": "names,emailAddresses,phoneNumbers,organizations",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.people().connections().list(**kwargs).execute()
        connections: list[dict[str, Any]] = response.get("connections", [])
        for person in connections:
            fields = _extract_contact_fields(person)
            # Skip contacts without any identifying information.
            if fields["full_name"] or fields["emails"]:
                contacts.append(fields)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return contacts
