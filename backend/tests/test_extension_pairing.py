"""Tests for the LinkedIn extension pairing API."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extension_pairing import ExtensionPairing
from app.models.user import User


# ---------------------------------------------------------------------------
# Helper: create a scoped extension JWT directly (mirrors _create_extension_token)
# ---------------------------------------------------------------------------


def _make_extension_token(user_id: str, *, exp: datetime | None = None) -> str:
    """Create an extension-scoped JWT (aud: pingcrm-extension) for tests."""
    from jose import jwt

    from app.core.config import settings

    payload = {
        "sub": user_id,
        "aud": "pingcrm-extension",
        "exp": exp if exp is not None else datetime.now(UTC) + timedelta(days=30),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

PAIR_URL = "/api/v1/extension/pair"
REFRESH_URL = "/api/v1/extension/refresh"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _post_code(client: AsyncClient, code: str, headers: dict) -> dict:
    resp = await client.post(PAIR_URL, json={"code": code}, headers=headers)
    return resp


# ---------------------------------------------------------------------------
# Task 1: POST creates pairing successfully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_pair_creates_pairing(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
):
    """POST /pair creates an ExtensionPairing row and returns status ok."""
    code = "TESTCODE1234"
    resp = await client.post(PAIR_URL, json={"code": code}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ok"

    result = await db.execute(
        select(ExtensionPairing).where(ExtensionPairing.code == code)
    )
    pairing = result.scalar_one_or_none()
    assert pairing is not None
    assert pairing.user_id == test_user.id
    assert pairing.token != ""
    assert pairing.claimed_at is None

    # User should have linkedin_extension_paired_at set
    await db.refresh(test_user)
    assert test_user.linkedin_extension_paired_at is not None


# ---------------------------------------------------------------------------
# Task 2: GET returns 404 for unknown code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pair_404_unknown_code(client: AsyncClient):
    """GET /pair with an unknown code returns 404."""
    resp = await client.get(PAIR_URL, params={"code": "NOSUCHCODE1"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 3: GET returns token after POST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pair_returns_token_after_post(
    client: AsyncClient,
    auth_headers: dict,
):
    """After a POST, GET /pair returns the scoped token."""
    code = "VALIDCODE123"
    post_resp = await client.post(PAIR_URL, json={"code": code}, headers=auth_headers)
    assert post_resp.status_code == 200

    get_resp = await client.get(PAIR_URL, params={"code": code})
    assert get_resp.status_code == 200

    data = get_resp.json()["data"]
    assert "token" in data
    assert data["token"] != ""
    assert "api_url" in data


# ---------------------------------------------------------------------------
# Task 4: GET returns 410 for expired code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pair_410_expired_code(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """GET /pair returns 410 when the pairing code has expired."""
    code = "EXPIREDCODE1"
    pairing = ExtensionPairing(
        code=code,
        user_id=test_user.id,
        token="some-token",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),  # already expired
    )
    db.add(pairing)
    await db.commit()

    resp = await client.get(PAIR_URL, params={"code": code})
    assert resp.status_code == 410


# ---------------------------------------------------------------------------
# Task 5: GET returns 429 after 20 attempts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pair_429_after_max_attempts(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """GET /pair returns 429 when attempts >= 20."""
    code = "MAXATTEMPTS1"
    pairing = ExtensionPairing(
        code=code,
        user_id=test_user.id,
        token="some-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        attempts=20,
    )
    db.add(pairing)
    await db.commit()

    resp = await client.get(PAIR_URL, params={"code": code})
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Task 6: DELETE disconnects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_pair_disconnects(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: User,
):
    """DELETE /pair removes all pairings and clears linkedin_extension_paired_at."""
    code = "DELETEME1234"
    post_resp = await client.post(PAIR_URL, json={"code": code}, headers=auth_headers)
    assert post_resp.status_code == 200

    delete_resp = await client.delete(PAIR_URL, headers=auth_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["status"] == "ok"

    # Pairing should be gone
    result = await db.execute(
        select(ExtensionPairing).where(ExtensionPairing.user_id == test_user.id)
    )
    assert result.scalar_one_or_none() is None

    # linkedin_extension_paired_at should be cleared
    await db.refresh(test_user)
    assert test_user.linkedin_extension_paired_at is None


# ---------------------------------------------------------------------------
# Task 7: POST rejects duplicate code from a different user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_pair_rejects_duplicate_code_different_user(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
):
    """POST /pair with a code already claimed by another user returns 409."""
    code = "DUPCODE12345"

    # Create a second user who owns the pairing
    from app.core.auth import hash_password

    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password=hash_password("otherpass"),
        full_name="Other User",
    )
    db.add(other_user)
    await db.commit()

    # Pre-create a pairing owned by other_user with this code
    pairing = ExtensionPairing(
        code=code,
        user_id=other_user.id,
        token="other-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(pairing)
    await db.commit()

    # test_user (via auth_headers) tries to pair with the same code
    resp = await client.post(PAIR_URL, json={"code": code}, headers=auth_headers)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST requires authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_pair_requires_auth(client: AsyncClient):
    """POST /pair without auth returns 401."""
    resp = await client.post(PAIR_URL, json={"code": "NOAUTHCODE12"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE requires authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_pair_requires_auth(client: AsyncClient):
    """DELETE /pair without auth returns 401."""
    resp = await client.delete(PAIR_URL)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Extension JWT — suggestions list endpoint
# ---------------------------------------------------------------------------


SUGGESTIONS_URL = "/api/v1/suggestions"
REGEN_URL_TEMPLATE = "/api/v1/suggestions/{suggestion_id}/regenerate"


@pytest.mark.asyncio
async def test_suggestions_list_accepts_extension_jwt(
    client: AsyncClient,
    test_user: User,
):
    """GET /suggestions must accept a JWT issued with aud: pingcrm-extension."""
    token = _make_extension_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(SUGGESTIONS_URL, headers=headers)
    # 200 with an empty list — the important thing is it is not 401/403
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert isinstance(body["data"], list)


# ---------------------------------------------------------------------------
# Extension JWT — suggestion regenerate endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggestion_regenerate_accepts_extension_jwt(
    client: AsyncClient,
    auth_headers: dict,
    test_user: User,
    db: AsyncSession,
):
    """POST /suggestions/{id}/regenerate must accept an extension JWT.

    We create a suggestion via the DB directly, then call regenerate with an
    extension-scoped token and verify we get 200 (not 401/403).  The
    compose_followup_message service may return an empty string in the test
    environment — that is acceptable; the auth layer is what we are testing.
    """
    import uuid as _uuid

    from app.models.contact import Contact
    from app.models.follow_up import FollowUpSuggestion

    # Create a minimal contact + suggestion owned by test_user
    contact = Contact(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        full_name="Regen Test",
        source="manual",
        linkedin_url="https://www.linkedin.com/in/regen-test",
    )
    db.add(contact)
    await db.flush()

    suggestion = FollowUpSuggestion(
        id=_uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="Original message",
        suggested_channel="linkedin",
        status="pending",
    )
    db.add(suggestion)
    await db.commit()

    token = _make_extension_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}
    url = REGEN_URL_TEMPLATE.format(suggestion_id=str(suggestion.id))

    resp = await client.post(url, json={}, headers=headers)
    # The endpoint must not reject the extension token (not 401/403).
    assert resp.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# Extension JWT — enrichment includes linkedin_profile_id and linkedin_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggestions_list_enrichment_includes_linkedin_fields(
    client: AsyncClient,
    test_user: User,
    db: AsyncSession,
):
    """Suggestion contact object must expose linkedin_profile_id and linkedin_url."""
    import uuid as _uuid

    from app.models.contact import Contact
    from app.models.follow_up import FollowUpSuggestion

    # Create a contact that has LinkedIn data and a reachable channel
    contact = Contact(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        full_name="LinkedIn Person",
        source="linkedin",
        linkedin_profile_id="linkedin-person-slug",
        linkedin_url="https://www.linkedin.com/in/linkedin-person-slug",
    )
    db.add(contact)
    await db.flush()

    suggestion = FollowUpSuggestion(
        id=_uuid.uuid4(),
        contact_id=contact.id,
        user_id=test_user.id,
        trigger_type="time_based",
        suggested_message="Hey LinkedIn Person",
        suggested_channel="linkedin",
        status="pending",
    )
    db.add(suggestion)
    await db.commit()

    token = _make_extension_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(SUGGESTIONS_URL, headers=headers)
    assert resp.status_code == 200

    items = resp.json()["data"]
    assert len(items) >= 1

    # Find the suggestion we just created
    found = next(
        (item for item in items if str(item.get("id")) == str(suggestion.id)),
        None,
    )
    assert found is not None, "Suggestion not found in list response"

    contact_data = found.get("contact")
    assert contact_data is not None
    assert contact_data["linkedin_profile_id"] == "linkedin-person-slug"
    assert contact_data["linkedin_url"] == "https://www.linkedin.com/in/linkedin-person-slug"


# ---------------------------------------------------------------------------
# Refresh endpoint: expired token within grace yields a new token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_exchanges_expired_token_within_grace(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """A token expired 5 days ago is refreshable while the user is still paired."""
    test_user.linkedin_extension_paired_at = datetime.now(UTC) - timedelta(days=35)
    await db.commit()

    expired = _make_extension_token(
        str(test_user.id), exp=datetime.now(UTC) - timedelta(days=5)
    )

    resp = await client.post(REFRESH_URL, json={"token": expired})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["token"] and data["token"] != expired
    assert data["api_url"]

    # Decoding the new token should yield a future exp.
    from jose import jwt

    from app.core.config import settings

    claims = jwt.decode(
        data["token"],
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        audience="pingcrm-extension",
    )
    assert claims["sub"] == str(test_user.id)
    assert claims["exp"] > datetime.now(UTC).timestamp()


# ---------------------------------------------------------------------------
# Refresh endpoint: still-valid tokens can also be exchanged (proactive refresh)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_accepts_still_valid_token(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """A non-expired extension token can also be refreshed."""
    test_user.linkedin_extension_paired_at = datetime.now(UTC) - timedelta(days=1)
    await db.commit()

    token = _make_extension_token(str(test_user.id))

    resp = await client.post(REFRESH_URL, json={"token": token})
    assert resp.status_code == 200

    from jose import jwt

    from app.core.config import settings

    claims = jwt.decode(
        resp.json()["data"]["token"],
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        audience="pingcrm-extension",
    )
    assert claims["sub"] == str(test_user.id)
    assert claims["exp"] > datetime.now(UTC).timestamp()


# ---------------------------------------------------------------------------
# Refresh endpoint: tokens older than the grace window are rejected and
# the user's paired_at flag is cleared so the web UI stops lying.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_rejects_token_beyond_grace_and_clears_paired_at(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    test_user.linkedin_extension_paired_at = datetime.now(UTC) - timedelta(days=200)
    await db.commit()

    ancient = _make_extension_token(
        str(test_user.id), exp=datetime.now(UTC) - timedelta(days=120)
    )

    resp = await client.post(REFRESH_URL, json={"token": ancient})
    assert resp.status_code == 401

    await db.refresh(test_user)
    assert test_user.linkedin_extension_paired_at is None


# ---------------------------------------------------------------------------
# Refresh endpoint: refuses web-audience tokens (scope separation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_rejects_web_audience_token(
    client: AsyncClient,
    test_user: User,
):
    """A regular web-session JWT must not be refreshable as an extension token."""
    from app.core.auth import create_access_token

    web_token = create_access_token(data={"sub": str(test_user.id)})
    resp = await client.post(REFRESH_URL, json={"token": web_token})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh endpoint: rejects tokens for users who already disconnected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_rejects_disconnected_user(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
):
    """If linkedin_extension_paired_at is NULL, refresh must fail."""
    assert test_user.linkedin_extension_paired_at is None
    token = _make_extension_token(str(test_user.id))

    resp = await client.post(REFRESH_URL, json={"token": token})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh endpoint: rejects tokens with a bad signature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_rejects_tampered_token(client: AsyncClient):
    """Tampered JWTs must return 401."""
    resp = await client.post(REFRESH_URL, json={"token": "not.a.jwt"})
    assert resp.status_code == 401
