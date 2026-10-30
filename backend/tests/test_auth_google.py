import uuid
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.integrations.google_accounts import load_google_mailboxes
from app.models.google_account import GoogleAccount
from app.models.user import User


_fake_redis_instance = None


@pytest.fixture(autouse=True)
def _patch_redis():
    global _fake_redis_instance
    fr = fakeredis.aioredis.FakeRedis(decode_responses=True)
    _fake_redis_instance = fr
    with patch("app.core.redis.get_redis", return_value=fr), \
         patch("app.api.auth_google.get_redis", return_value=fr):
        yield fr
    _fake_redis_instance = None


async def _inject_state(state: str, user_id: str | None) -> str:
    from app.api.auth_google import _store_google_state
    await _store_google_state(state, user_id)
    return state


@pytest.mark.asyncio
async def test_google_url_returns_oauth_url(client: AsyncClient, auth_headers: dict):
    """GET /auth/google/url returns an authorization URL when credentials are configured."""
    with patch("app.api.auth_google.settings") as mock_settings, \
         patch("app.api.auth_google.build_oauth_url", return_value=("https://accounts.google.com/o/oauth2/auth?mock=1", "state123")):
        mock_settings.GOOGLE_CLIENT_ID = "test-client-id"
        mock_settings.GOOGLE_CLIENT_SECRET = "test-client-secret"
        mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1440
        resp = await client.get("/api/v1/auth/google/url", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "url" in data
    assert data["url"].startswith("https://accounts.google.com")
    assert "state" in data


@pytest.mark.asyncio
async def test_google_url_stores_state_nonce(client: AsyncClient, auth_headers: dict):
    """GET /auth/google/url stores the state in Redis."""
    with patch("app.api.auth_google.settings") as mock_settings, \
         patch("app.api.auth_google.build_oauth_url", return_value=("https://accounts.google.com/mock", "nonce-abc")):
        mock_settings.GOOGLE_CLIENT_ID = "test-client-id"
        mock_settings.GOOGLE_CLIENT_SECRET = "test-client-secret"
        mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 1440
        resp = await client.get("/api/v1/auth/google/url", headers=auth_headers)

    assert resp.status_code == 200
    # Verify the state was stored in Redis
    assert await _fake_redis_instance.exists("oauth_state:nonce-abc")


@pytest.mark.asyncio
async def test_google_url_without_credentials(client: AsyncClient, auth_headers: dict):
    """GET /auth/google/url returns 400 when GOOGLE_CLIENT_ID is not set."""
    with patch("app.api.auth_google.settings") as mock_settings:
        mock_settings.GOOGLE_CLIENT_ID = ""
        mock_settings.GOOGLE_CLIENT_SECRET = ""
        resp = await client.get("/api/v1/auth/google/url", headers=auth_headers)
    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_url_requires_auth(client: AsyncClient):
    """GET /auth/google/url returns 401 without auth headers."""
    resp = await client.get("/api/v1/auth/google/url")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_callback_missing_state(client: AsyncClient):
    """POST /auth/google/callback returns 400 when state is missing."""
    resp = await client.post(
        "/api/v1/auth/google/callback",
        json={"code": "valid-code"},
    )
    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_google_callback_invalid_state(client: AsyncClient):
    """POST /auth/google/callback returns 400 when state doesn't match any stored nonce."""
    resp = await client.post(
        "/api/v1/auth/google/callback",
        json={"code": "valid-code", "state": "bogus-state"},
    )
    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_google_callback_state_consumed_once(client: AsyncClient, test_user: User, auth_headers: dict):
    state = await _inject_state("one-time-state", str(test_user.id))
    mock_tokens = {"id_token": "fake", "refresh_token": "ref"}
    id_info = {"email": "onetime@example.com", "name": "One Time", "sub": "789"}

    with patch("app.api.auth_google.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth_google.google_id_token.verify_oauth2_token", return_value=id_info):
        resp1 = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code", "state": state},
            headers=auth_headers,
        )
        resp2 = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code", "state": state},
            headers=auth_headers,
        )
    assert resp1.status_code == 200
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_google_callback_exchange_fails(client: AsyncClient, test_user: User, auth_headers: dict):
    state = await _inject_state("exchange-fail-state", str(test_user.id))
    with patch("app.api.auth_google.exchange_code", side_effect=RuntimeError("bad code")):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "bad-code", "state": state},
            headers=auth_headers,
        )
    assert resp.status_code == 400
    assert "Failed to exchange" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_callback_invalid_id_token(client: AsyncClient, test_user: User, auth_headers: dict):
    state = await _inject_state("invalid-token-state", str(test_user.id))
    mock_tokens = {"id_token": "fake", "refresh_token": "ref"}
    with patch("app.api.auth_google.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth_google.google_id_token.verify_oauth2_token", side_effect=ValueError("bad token")):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code", "state": state},
            headers=auth_headers,
        )
    assert resp.status_code == 400
    assert "Invalid Google ID token" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_callback_no_email(client: AsyncClient, test_user: User, auth_headers: dict):
    state = await _inject_state("no-email-state", str(test_user.id))
    mock_tokens = {"id_token": "fake", "refresh_token": "ref"}
    with patch("app.api.auth_google.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth_google.google_id_token.verify_oauth2_token", return_value={"sub": "123"}):
        resp = await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code", "state": state},
            headers=auth_headers,
        )
    assert resp.status_code == 400
    assert "does not provide an email" in resp.json()["detail"]


async def _connect(client, state, headers, email, refresh_token="ref"):
    mock_tokens = {"id_token": "fake", "refresh_token": refresh_token}
    id_info = {"email": email, "name": "Google Person", "sub": "g-sub"}
    with patch("app.api.auth_google.exchange_code", return_value=mock_tokens), \
         patch("app.api.auth_google.google_id_token.verify_oauth2_token", return_value=id_info):
        return await client.post(
            "/api/v1/auth/google/callback",
            json={"code": "valid-code", "state": state},
            headers=headers,
        )


def _token_subject(resp) -> str:
    token = resp.json()["data"]["access_token"]
    return jwt.decode(token, options={"verify_signature": False})["sub"]


@pytest.mark.asyncio
async def test_connect_google_with_different_email_keeps_caller(
    client: AsyncClient, db: AsyncSession, test_user: User, auth_headers: dict
):
    user_count_before = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    state = await _inject_state("connect-different-email", str(test_user.id))

    resp = await _connect(client, state, auth_headers, "g@gmail.com")

    assert resp.status_code == 200
    assert _token_subject(resp) == str(test_user.id)
    assert (await db.execute(select(func.count()).select_from(User))).scalar_one() == user_count_before
    accounts = (await db.execute(select(GoogleAccount))).scalars().all()
    assert [(a.user_id, a.email) for a in accounts] == [(test_user.id, "g@gmail.com")]
    await db.refresh(test_user)
    assert test_user.google_refresh_token == "ref"


@pytest.mark.asyncio
async def test_connect_google_matching_other_user_email_does_not_switch_account(
    client: AsyncClient, db: AsyncSession, test_user: User, auth_headers: dict
):
    other = User(
        id=uuid.uuid4(),
        email="victim@example.com",
        hashed_password=hash_password("pass"),
        full_name="Victim",
        google_refresh_token="victim-refresh",
    )
    db.add(other)
    await db.commit()
    state = await _inject_state("connect-other-email", str(test_user.id))

    resp = await _connect(client, state, auth_headers, "victim@example.com")

    assert resp.status_code == 200
    assert _token_subject(resp) == str(test_user.id)
    accounts = (await db.execute(select(GoogleAccount))).scalars().all()
    assert [(a.user_id, a.email) for a in accounts] == [(test_user.id, "victim@example.com")]
    await db.refresh(other)
    assert other.email == "victim@example.com"
    assert other.google_refresh_token == "victim-refresh"
    await db.refresh(test_user)
    assert test_user.email != "victim@example.com"


@pytest.mark.asyncio
async def test_connect_google_twice_updates_existing_account(
    client: AsyncClient, db: AsyncSession, test_user: User, auth_headers: dict
):
    for n, refresh in enumerate(["first", "second"]):
        state = await _inject_state(f"connect-twice-{n}", str(test_user.id))
        resp = await _connect(client, state, auth_headers, "g@gmail.com", refresh_token=refresh)
        assert resp.status_code == 200
    accounts = (await db.execute(select(GoogleAccount))).scalars().all()
    assert len(accounts) == 1
    assert accounts[0].refresh_token == "second"


@pytest.mark.asyncio
async def test_google_callback_anonymous_state_rejected(client: AsyncClient, db: AsyncSession, auth_headers: dict):
    state = await _inject_state("anon-state", None)
    resp = await _connect(client, state, auth_headers, "g@gmail.com")
    assert resp.status_code == 403
    assert (await db.execute(select(func.count()).select_from(GoogleAccount))).scalar_one() == 0


@pytest.mark.asyncio
async def test_google_callback_anonymous_state_without_caller_creates_nothing(client: AsyncClient, db: AsyncSession):
    user_count_before = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    state = await _inject_state("anon-state-no-caller", None)
    resp = await _connect(client, state, {}, "g@gmail.com")
    assert resp.status_code == 403
    assert (await db.execute(select(func.count()).select_from(User))).scalar_one() == user_count_before


@pytest.mark.asyncio
async def test_google_callback_bound_state_without_caller_rejected(
    client: AsyncClient, db: AsyncSession, test_user: User
):
    state = await _inject_state("bound-no-caller", str(test_user.id))
    resp = await _connect(client, state, {}, "g@gmail.com")
    assert resp.status_code == 403
    assert (await db.execute(select(func.count()).select_from(GoogleAccount))).scalar_one() == 0


@pytest.mark.asyncio
async def test_legacy_token_is_kept_as_account_when_linking_different_email(
    client: AsyncClient, db: AsyncSession, test_user: User, auth_headers: dict
):
    test_user.google_refresh_token = "legacy-token"
    await db.commit()
    state = await _inject_state("legacy-link-different", str(test_user.id))

    resp = await _connect(client, state, auth_headers, "g@gmail.com", refresh_token="new-token")

    assert resp.status_code == 200
    accounts = (await db.execute(select(GoogleAccount))).scalars().all()
    assert {(a.email, a.refresh_token) for a in accounts} == {
        (test_user.email, "legacy-token"),
        ("g@gmail.com", "new-token"),
    }
    await db.refresh(test_user)
    assert test_user.google_refresh_token == "new-token"


@pytest.mark.asyncio
async def test_legacy_user_reconnecting_same_email_creates_one_account(
    client: AsyncClient, db: AsyncSession, test_user: User, auth_headers: dict
):
    test_user.google_refresh_token = "legacy-token"
    await db.commit()
    state = await _inject_state("legacy-link-same", str(test_user.id))

    resp = await _connect(client, state, auth_headers, test_user.email, refresh_token="new-token")

    assert resp.status_code == 200
    accounts = (await db.execute(select(GoogleAccount))).scalars().all()
    assert [(a.email, a.refresh_token) for a in accounts] == [(test_user.email, "new-token")]


async def _delete_account(client, headers, email, db):
    account = (await db.execute(select(GoogleAccount).where(GoogleAccount.email == email))).scalar_one()
    resp = await client.delete(f"/api/v1/auth/google/accounts/{account.id}", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_removing_only_account_clears_token_and_mailboxes(
    client: AsyncClient, db: AsyncSession, test_user: User, auth_headers: dict
):
    state = await _inject_state("remove-only", str(test_user.id))
    await _connect(client, state, auth_headers, "g@gmail.com", refresh_token="tok-g")

    await _delete_account(client, auth_headers, "g@gmail.com", db)

    await db.refresh(test_user)
    assert test_user.google_refresh_token is None
    assert (await load_google_mailboxes(test_user, db)).accounts == []


@pytest.mark.asyncio
async def test_removing_one_of_two_accounts_points_token_at_the_remaining_one(
    client: AsyncClient, db: AsyncSession, test_user: User, auth_headers: dict
):
    for n, (email, token) in enumerate([("g@gmail.com", "tok-g"), ("h@gmail.com", "tok-h")]):
        state = await _inject_state(f"remove-one-{n}", str(test_user.id))
        await _connect(client, state, auth_headers, email, refresh_token=token)

    await _delete_account(client, auth_headers, "h@gmail.com", db)

    await db.refresh(test_user)
    assert test_user.google_refresh_token == "tok-g"


@pytest.mark.asyncio
async def test_connect_remove_connect_leaves_only_the_last_account(
    client: AsyncClient, db: AsyncSession, test_user: User, auth_headers: dict
):
    state = await _inject_state("flow-b", str(test_user.id))
    await _connect(client, state, auth_headers, "b@gmail.com", refresh_token="tok-b")
    await _delete_account(client, auth_headers, "b@gmail.com", db)
    state = await _inject_state("flow-c", str(test_user.id))
    await _connect(client, state, auth_headers, "c@gmail.com", refresh_token="tok-c")

    accounts = (await db.execute(select(GoogleAccount))).scalars().all()
    assert [(a.email, a.refresh_token) for a in accounts] == [("c@gmail.com", "tok-c")]
