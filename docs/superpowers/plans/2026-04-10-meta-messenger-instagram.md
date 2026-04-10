# Meta Messenger & Instagram DM Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync Facebook Messenger and Instagram DM conversations into PingCRM via the Chrome extension, storing messages as Interactions with reactions and read receipts.

**Architecture:** Extend the existing Chrome extension to capture Meta session cookies and execute same-origin GraphQL requests on facebook.com/instagram.com. Raw data is pushed to a new `POST /api/v1/meta/push` backend endpoint that handles contact resolution, dedup, and interaction creation — mirroring the LinkedIn push pattern. A new "Meta" card in frontend settings controls the integration.

**Tech Stack:** Python/FastAPI (backend), SQLAlchemy + Alembic (models/migrations), Chrome Extension MV3 (JS), Next.js/React (frontend)

---

## File Structure

### New Files
| File | Responsibility |
|---|---|
| `backend/app/api/meta.py` | Push endpoint + Pydantic schemas for Meta data |
| `backend/app/schemas/meta.py` | Response types (MetaPushResult, MetaBackfillItem) |
| `backend/tests/test_meta_push.py` | Backend tests for the Meta push endpoint |
| `chrome-extension/background/meta-client.js` | Same-origin fetch proxy for Meta GraphQL API |
| `chrome-extension/background/meta-sync-utils.js` | Constants, cookie helpers, parsers for Meta |
| `chrome-extension/background/sync-facebook.js` | Messenger sync orchestrator |
| `chrome-extension/background/sync-instagram.js` | Instagram DM sync orchestrator |
| `chrome-extension/content/meta-notify.js` | Content script for facebook.com + instagram.com |
| `frontend/src/app/settings/_components/platform-cards/meta-card.tsx` | Meta integration card |

### Modified Files
| File | Changes |
|---|---|
| `backend/app/models/contact.py` | Add facebook_*, instagram_* columns |
| `backend/app/models/interaction.py` | Add `metadata` JSON column |
| `backend/app/models/user.py` | Add meta_connected, meta_connected_name, meta_sync_* |
| `backend/app/schemas/user.py` | Add meta fields to UserResponse |
| `backend/app/schemas/responses.py` | Add MetaPushResult, MetaBackfillItem |
| `backend/app/main.py` | Register meta_router |
| `backend/alembic/versions/` | New migration file |
| `chrome-extension/manifest.json` | Add host_permissions + content_scripts for Meta |
| `chrome-extension/background/service-worker.js` | Import Meta modules, add META_PAGE_VISIT + META_SYNC_NOW handlers |
| `frontend/src/app/settings/_components/integrations-tab.tsx` | Add MetaCard |
| `frontend/src/app/settings/_hooks/use-settings-controller.ts` | Add meta fields to ConnectedAccounts |

---

### Task 1: Database Models — Add Meta Fields to Contact, Interaction, User

**Files:**
- Modify: `backend/app/models/contact.py:66-70` (after whatsapp fields)
- Modify: `backend/app/models/interaction.py:28` (after is_read_by_recipient)
- Modify: `backend/app/models/user.py:46-48` (after linkedin_extension_paired_at)

- [ ] **Step 1: Add Facebook/Instagram fields to Contact model**

In `backend/app/models/contact.py`, add after line 70 (`whatsapp_bio_checked_at`):

```python
    facebook_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    facebook_name: Mapped[str | None] = mapped_column(String, nullable=True)
    facebook_avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    instagram_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    instagram_username: Mapped[str | None] = mapped_column(String, nullable=True)
    instagram_avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 2: Add metadata JSON column to Interaction model**

In `backend/app/models/interaction.py`, add the `JSON` import to the sqlalchemy import line:

```python
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
```
becomes:
```python
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
```

Then add after line 28 (`is_read_by_recipient`):

```python
    metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

Note: `UUID` import already exists via `from sqlalchemy.dialects.postgresql import UUID`. Add `JSON` to that import instead:
```python
from sqlalchemy.dialects.postgresql import JSON, UUID
```

- [ ] **Step 3: Add Meta fields to User model**

In `backend/app/models/user.py`, add after line 48 (`linkedin_extension_paired_at`):

```python
    meta_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    meta_connected_name: Mapped[str | None] = mapped_column(String, nullable=True)
    meta_sync_facebook: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    meta_sync_instagram: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
```

- [ ] **Step 4: Generate Alembic migration**

Run:
```bash
cd backend && PYTHONPATH=. alembic revision --autogenerate -m "add meta facebook instagram fields"
```

Expected: New migration file created in `backend/alembic/versions/`

- [ ] **Step 5: Run migration**

Run:
```bash
cd backend && PYTHONPATH=. alembic upgrade head
```

Expected: Migration applies successfully

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/contact.py backend/app/models/interaction.py backend/app/models/user.py backend/alembic/versions/*meta*
git commit -m "feat: add Meta (Facebook/Instagram) fields to Contact, Interaction, User models"
```

---

### Task 2: Backend Schemas — MetaPushResult and UserResponse Updates

**Files:**
- Modify: `backend/app/schemas/responses.py:103` (after LinkedInPushResult)
- Modify: `backend/app/schemas/user.py:31-33` (after whatsapp fields in UserResponse)

- [ ] **Step 1: Add MetaBackfillItem and MetaPushResult to responses.py**

In `backend/app/schemas/responses.py`, add after `LinkedInPushResult` (after line 103):

```python

class MetaBackfillItem(BaseModel):
    contact_id: str
    platform_id: str
    platform: str  # "facebook" | "instagram"


class MetaPushResult(BaseModel):
    contacts_created: int
    contacts_updated: int
    interactions_created: int
    interactions_skipped: int
    backfill_needed: list[MetaBackfillItem] = []
```

- [ ] **Step 2: Add Meta fields to UserResponse**

In `backend/app/schemas/user.py`, add after line 33 (`whatsapp_phone`):

```python
    meta_connected: bool = False
    meta_connected_name: str | None = None
    meta_sync_facebook: bool = True
    meta_sync_instagram: bool = True
```

- [ ] **Step 3: Update UserResponse.from_user() to include Meta fields**

In `backend/app/schemas/user.py`, inside the `from_user()` method, add after the `whatsapp_phone` line:

```python
            meta_connected=bool(user.meta_connected),
            meta_connected_name=getattr(user, "meta_connected_name", None),
            meta_sync_facebook=bool(getattr(user, "meta_sync_facebook", True)),
            meta_sync_instagram=bool(getattr(user, "meta_sync_instagram", True)),
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/responses.py backend/app/schemas/user.py
git commit -m "feat: add Meta schemas for push endpoint and UserResponse"
```

---

### Task 3: Backend — Meta Push Endpoint (Tests First)

**Files:**
- Create: `backend/tests/test_meta_push.py`
- Create: `backend/app/api/meta.py`
- Modify: `backend/app/main.py:95` (add router import + registration)

- [ ] **Step 1: Write failing tests for Meta push endpoint**

Create `backend/tests/test_meta_push.py`:

```python
"""Tests for the Meta (Facebook/Instagram) push endpoint."""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User


@pytest.mark.asyncio
async def test_push_creates_contact_and_interaction(client, test_user, auth_headers):
    """Push a new profile + message → creates contact and interaction."""
    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [
                {
                    "platform_id": "100012345",
                    "name": "Jane Doe",
                    "username": "janedoe",
                    "avatar_url": "https://example.com/avatar.jpg",
                }
            ],
            "messages": [
                {
                    "message_id": "mid.001",
                    "conversation_id": "conv_123",
                    "platform_id": "100012345",
                    "sender_name": "Jane Doe",
                    "direction": "inbound",
                    "content_preview": "Hey, how are you?",
                    "timestamp": "2026-04-09T14:30:00Z",
                    "reactions": [{"reactor_id": "100099", "type": "love"}],
                    "read_by": ["100012345"],
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contacts_created"] == 1
    assert data["interactions_created"] == 1


@pytest.mark.asyncio
async def test_push_deduplicates_messages(client, test_user, auth_headers):
    """Pushing the same message_id twice → second is skipped."""
    payload = {
        "platform": "facebook",
        "profiles": [],
        "messages": [
            {
                "message_id": "mid.dedup",
                "conversation_id": "conv_1",
                "platform_id": "100012345",
                "sender_name": "Jane Doe",
                "direction": "inbound",
                "content_preview": "Hello",
                "timestamp": "2026-04-09T10:00:00Z",
                "reactions": [],
                "read_by": [],
            }
        ],
    }
    resp1 = await client.post("/api/v1/meta/push", json=payload, headers=auth_headers)
    assert resp1.json()["data"]["interactions_created"] == 1

    resp2 = await client.post("/api/v1/meta/push", json=payload, headers=auth_headers)
    assert resp2.json()["data"]["interactions_created"] == 0
    assert resp2.json()["data"]["interactions_skipped"] == 1


@pytest.mark.asyncio
async def test_push_updates_existing_contact(client, db, test_user, auth_headers):
    """Push a profile whose facebook_id matches an existing contact → updates it."""
    contact = Contact(
        user_id=test_user.id,
        full_name="Jane D",
        facebook_id="100012345",
    )
    db.add(contact)
    await db.commit()

    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [
                {
                    "platform_id": "100012345",
                    "name": "Jane Doe",
                    "username": "janedoe",
                    "avatar_url": None,
                }
            ],
            "messages": [],
        },
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["contacts_created"] == 0
    assert data["contacts_updated"] == 1


@pytest.mark.asyncio
async def test_push_instagram_platform(client, test_user, auth_headers):
    """Push with platform=instagram uses instagram_id for contact matching."""
    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "instagram",
            "profiles": [
                {
                    "platform_id": "ig_555",
                    "name": "Bob Smith",
                    "username": "bobsmith",
                    "avatar_url": None,
                }
            ],
            "messages": [
                {
                    "message_id": "mid.ig001",
                    "conversation_id": "ig_conv_1",
                    "platform_id": "ig_555",
                    "sender_name": "Bob Smith",
                    "direction": "inbound",
                    "content_preview": "Nice pic!",
                    "timestamp": "2026-04-09T15:00:00Z",
                    "reactions": [],
                    "read_by": [],
                }
            ],
        },
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["contacts_created"] == 1
    assert data["interactions_created"] == 1


@pytest.mark.asyncio
async def test_push_stores_reactions_and_read_receipts(client, db, test_user, auth_headers):
    """Reactions and read_by are stored in interaction metadata."""
    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [],
            "messages": [
                {
                    "message_id": "mid.react",
                    "conversation_id": "conv_r",
                    "platform_id": "100012345",
                    "sender_name": "Jane Doe",
                    "direction": "inbound",
                    "content_preview": "Check this out",
                    "timestamp": "2026-04-09T16:00:00Z",
                    "reactions": [{"reactor_id": "100099", "type": "love"}],
                    "read_by": ["100012345", "100099"],
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.json()["data"]["interactions_created"] == 1

    result = await db.execute(
        select(Interaction).where(Interaction.raw_reference_id == "facebook:mid.react")
    )
    interaction = result.scalar_one()
    assert interaction.metadata is not None
    assert interaction.metadata["reactions"][0]["type"] == "love"
    assert "100099" in interaction.metadata["read_by"]


@pytest.mark.asyncio
async def test_push_sets_meta_connected_flag(client, db, test_user, auth_headers):
    """First push sets meta_connected=True on the user."""
    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [
                {
                    "platform_id": "100012345",
                    "name": "Jane Doe",
                    "username": None,
                    "avatar_url": None,
                }
            ],
            "messages": [],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    await db.refresh(test_user)
    assert test_user.meta_connected is True


@pytest.mark.asyncio
async def test_push_cross_platform_name_match(client, db, test_user, auth_headers):
    """A Facebook message with name matching an existing LinkedIn contact → links to it."""
    contact = Contact(
        user_id=test_user.id,
        full_name="Jane Doe",
        linkedin_profile_id="janedoe",
    )
    db.add(contact)
    await db.commit()

    resp = await client.post(
        "/api/v1/meta/push",
        json={
            "platform": "facebook",
            "profiles": [],
            "messages": [
                {
                    "message_id": "mid.xplat",
                    "conversation_id": "conv_x",
                    "platform_id": "100012345",
                    "sender_name": "Jane Doe",
                    "direction": "inbound",
                    "content_preview": "Hey!",
                    "timestamp": "2026-04-09T17:00:00Z",
                    "reactions": [],
                    "read_by": [],
                }
            ],
        },
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["contacts_created"] == 0  # Matched existing contact
    assert data["interactions_created"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && PYTHONPATH=. pytest tests/test_meta_push.py -v
```

Expected: FAIL — endpoint not found (404) or import error

- [ ] **Step 3: Implement the Meta push endpoint**

Create `backend/app/api/meta.py`:

```python
"""Meta (Facebook Messenger & Instagram DM) push endpoint."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_extension_or_web_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.follow_up import FollowUpSuggestion
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.responses import Envelope, MetaBackfillItem, MetaPushResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])


# ── Request schemas ──────────────────────────────────────────────────────────

class MetaProfilePush(BaseModel):
    platform_id: str
    name: str
    username: str | None = None
    avatar_url: str | None = None


class MetaReaction(BaseModel):
    reactor_id: str
    type: str


class MetaMessagePush(BaseModel):
    message_id: str
    conversation_id: str
    platform_id: str | None = None
    sender_name: str
    direction: str  # "inbound" | "outbound"
    content_preview: str
    timestamp: str  # ISO 8601
    reactions: list[MetaReaction] = []
    read_by: list[str] = []


class MetaPushRequest(BaseModel):
    platform: str  # "facebook" | "instagram"
    profiles: list[MetaProfilePush] = Field(default=[], max_length=50)
    messages: list[MetaMessagePush] = Field(default=[], max_length=500)


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/push", response_model=Envelope[MetaPushResult])
async def push_meta_data(
    body: MetaPushRequest,
    current_user: User = Depends(get_extension_or_web_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive profile and message data from the Chrome Extension for Facebook/Instagram."""
    platform = body.platform  # "facebook" or "instagram"
    contacts_created = 0
    contacts_updated = 0
    interactions_created = 0
    interactions_skipped = 0
    contacts_with_new_interactions: set[uuid.UUID] = set()
    touched_contacts: list[Contact] = []

    # Mark user as meta-connected on first push
    if not current_user.meta_connected:
        current_user.meta_connected = True

    # ── Pre-load all user contacts for in-memory matching ──
    all_contacts_result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id)
    )
    all_user_contacts = list(all_contacts_result.scalars().all())

    # Build lookup maps by platform ID and name
    fb_id_map: dict[str, Contact] = {}
    ig_id_map: dict[str, Contact] = {}
    name_map: dict[str, Contact] = {}
    for c in all_user_contacts:
        if c.facebook_id:
            fb_id_map[c.facebook_id] = c
        if c.instagram_id:
            ig_id_map[c.instagram_id] = c
        if c.full_name:
            name_map[c.full_name.lower()] = c

    id_map = fb_id_map if platform == "facebook" else ig_id_map

    # ── Pre-load existing interaction refs for dedup ──
    all_refs: list[str] = []
    for msg in body.messages:
        all_refs.append(f"{platform}:{msg.message_id}")
    existing_refs: set[str] = set()
    if all_refs:
        refs_result = await db.execute(
            select(Interaction.raw_reference_id).where(
                Interaction.user_id == current_user.id,
                Interaction.raw_reference_id.in_(all_refs),
            )
        )
        existing_refs = set(refs_result.scalars().all())

    # ── Profiles ──
    from app.services.sync_utils import sync_set_field
    for profile in body.profiles:
        contact = id_map.get(profile.platform_id)

        # Cross-platform: check the other Meta ID map
        if not contact:
            other_map = ig_id_map if platform == "facebook" else fb_id_map
            contact = other_map.get(profile.platform_id)

        # Fallback: name match
        if not contact and profile.name:
            contact = name_map.get(profile.name.lower())

        if contact:
            sync_set_field(contact, "full_name", profile.name)
            if platform == "facebook":
                contact.facebook_id = profile.platform_id
                if profile.avatar_url:
                    contact.facebook_avatar_url = profile.avatar_url
                if profile.name:
                    contact.facebook_name = profile.name
            else:
                contact.instagram_id = profile.platform_id
                if profile.username:
                    contact.instagram_username = profile.username
                if profile.avatar_url:
                    contact.instagram_avatar_url = profile.avatar_url
            contacts_updated += 1
        else:
            name_parts = (profile.name or "").split(None, 1)
            contact_kwargs = dict(
                user_id=current_user.id,
                full_name=profile.name,
                given_name=name_parts[0] if name_parts else None,
                family_name=name_parts[1] if len(name_parts) > 1 else None,
            )
            if platform == "facebook":
                contact_kwargs["facebook_id"] = profile.platform_id
                contact_kwargs["facebook_name"] = profile.name
                contact_kwargs["facebook_avatar_url"] = profile.avatar_url
            else:
                contact_kwargs["instagram_id"] = profile.platform_id
                contact_kwargs["instagram_username"] = profile.username
                contact_kwargs["instagram_avatar_url"] = profile.avatar_url
            contact = Contact(**contact_kwargs)
            db.add(contact)
            await db.flush()
            contacts_created += 1
            # Update in-memory maps
            if platform == "facebook":
                fb_id_map[profile.platform_id] = contact
            else:
                ig_id_map[profile.platform_id] = contact
            if contact.full_name:
                name_map[contact.full_name.lower()] = contact

        id_map[profile.platform_id] = contact
        touched_contacts.append(contact)

    # ── Messages ──
    for msg in body.messages:
        raw_ref = f"{platform}:{msg.message_id}"

        if raw_ref in existing_refs:
            interactions_skipped += 1
            continue

        # Find contact
        contact = id_map.get(msg.platform_id) if msg.platform_id else None

        if not contact and msg.sender_name:
            contact = name_map.get(msg.sender_name.lower())
            if contact and msg.platform_id:
                # Link platform ID to matched contact
                if platform == "facebook" and not contact.facebook_id:
                    contact.facebook_id = msg.platform_id
                    fb_id_map[msg.platform_id] = contact
                elif platform == "instagram" and not contact.instagram_id:
                    contact.instagram_id = msg.platform_id
                    ig_id_map[msg.platform_id] = contact
                id_map[msg.platform_id] = contact

        if not contact:
            name_parts = (msg.sender_name or "").split(None, 1)
            contact_kwargs = dict(
                user_id=current_user.id,
                full_name=msg.sender_name,
                given_name=name_parts[0] if name_parts else None,
                family_name=name_parts[1] if len(name_parts) > 1 else None,
            )
            if platform == "facebook" and msg.platform_id:
                contact_kwargs["facebook_id"] = msg.platform_id
            elif platform == "instagram" and msg.platform_id:
                contact_kwargs["instagram_id"] = msg.platform_id
            contact = Contact(**contact_kwargs)
            db.add(contact)
            await db.flush()
            contacts_created += 1
            if msg.platform_id:
                id_map[msg.platform_id] = contact
            if contact.full_name:
                name_map[contact.full_name.lower()] = contact

        touched_contacts.append(contact)

        try:
            occurred_at = datetime.fromisoformat(msg.timestamp)
        except ValueError:
            occurred_at = datetime.now(UTC)

        # Build metadata from reactions + read receipts
        meta = None
        if msg.reactions or msg.read_by:
            meta = {}
            if msg.reactions:
                meta["reactions"] = [r.model_dump() for r in msg.reactions]
            if msg.read_by:
                meta["read_by"] = msg.read_by

        interaction = Interaction(
            contact_id=contact.id,
            user_id=current_user.id,
            platform=platform,
            direction=msg.direction if msg.direction in ("inbound", "outbound") else "inbound",
            content_preview=msg.content_preview[:500] if msg.content_preview else None,
            raw_reference_id=raw_ref,
            occurred_at=occurred_at,
            metadata=meta,
        )
        db.add(interaction)
        interactions_created += 1
        contacts_with_new_interactions.add(contact.id)

        if not contact.last_interaction_at or occurred_at > contact.last_interaction_at:
            contact.last_interaction_at = occurred_at
        contact.interaction_count = (contact.interaction_count or 0) + 1

    # Auto-dismiss pending suggestions for contacts with new interactions
    if contacts_with_new_interactions:
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(FollowUpSuggestion)
            .where(
                FollowUpSuggestion.contact_id.in_(list(contacts_with_new_interactions)),
                FollowUpSuggestion.status == "pending",
            )
            .values(status="dismissed")
        )

    await db.flush()

    # Record sync event
    if contacts_created + contacts_updated + interactions_created > 0:
        from app.services.sync_history import record_sync_start, record_sync_complete
        sync_event = await record_sync_start(current_user.id, platform, "webhook", db)
        await record_sync_complete(
            sync_event,
            records_created=contacts_created + interactions_created,
            records_updated=contacts_updated,
            details={
                "contacts_created": contacts_created,
                "contacts_updated": contacts_updated,
                "interactions_created": interactions_created,
                "interactions_skipped": interactions_skipped,
            },
            db=db,
        )
        await db.flush()

    # Auto-merge deterministic duplicates
    if contacts_created > 0:
        try:
            from app.services.identity_resolution import find_deterministic_matches
            merged = await find_deterministic_matches(current_user.id, db)
            if merged:
                logger.info("meta push: auto-merged %d duplicate(s) for user %s", len(merged), current_user.id)
        except Exception:
            logger.warning("meta push: auto-merge failed for user %s", current_user.id, exc_info=True)
        await db.flush()

    # Collect backfill items (contacts missing avatar)
    backfill_needed: list[MetaBackfillItem] = []
    seen_ids: set[uuid.UUID] = set()
    for contact in touched_contacts:
        if contact.id in seen_ids:
            continue
        seen_ids.add(contact.id)
        if platform == "facebook" and contact.facebook_id and not contact.facebook_avatar_url:
            backfill_needed.append(MetaBackfillItem(
                contact_id=str(contact.id),
                platform_id=contact.facebook_id,
                platform="facebook",
            ))
        elif platform == "instagram" and contact.instagram_id and not contact.instagram_avatar_url:
            backfill_needed.append(MetaBackfillItem(
                contact_id=str(contact.id),
                platform_id=contact.instagram_id,
                platform="instagram",
            ))

    return {
        "data": MetaPushResult(
            contacts_created=contacts_created,
            contacts_updated=contacts_updated,
            interactions_created=interactions_created,
            interactions_skipped=interactions_skipped,
            backfill_needed=backfill_needed,
        ),
        "error": None,
        "meta": None,
    }
```

- [ ] **Step 4: Register the Meta router in main.py**

In `backend/app/main.py`, add the import alongside other router imports:

```python
from app.api.meta import router as meta_router
```

And add after the whatsapp_router registration (line 99):

```python
app.include_router(meta_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd backend && PYTHONPATH=. pytest tests/test_meta_push.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run:
```bash
cd backend && PYTHONPATH=. pytest --timeout=30 -x -q
```

Expected: All existing tests still pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/meta.py backend/tests/test_meta_push.py backend/app/main.py backend/app/schemas/responses.py backend/app/schemas/user.py
git commit -m "feat: add Meta push endpoint for Facebook Messenger & Instagram DMs"
```

---

### Task 4: Chrome Extension — Manifest & Content Script

**Files:**
- Modify: `chrome-extension/manifest.json`
- Create: `chrome-extension/content/meta-notify.js`

- [ ] **Step 1: Update manifest.json — add Meta host permissions and content scripts**

In `chrome-extension/manifest.json`, add to `host_permissions` array:

```json
"https://www.facebook.com/*",
"https://www.instagram.com/*"
```

Add a new entry to the `content_scripts` array:

```json
{
  "matches": ["https://www.facebook.com/*", "https://www.instagram.com/*"],
  "js": ["content/meta-notify.js"],
  "run_at": "document_idle"
}
```

- [ ] **Step 2: Create meta-notify.js content script**

Create `chrome-extension/content/meta-notify.js`:

```javascript
/**
 * Content script for Facebook and Instagram pages.
 * Notifies the service worker on page load to refresh cookies
 * and trigger a throttled Meta sync.
 *
 * Also proxies Meta GraphQL requests from the service worker.
 * Content scripts run same-origin, so cookies (c_user, xs) are
 * attached automatically — no MV3 service-worker restrictions.
 */
try {
  const platform = location.hostname.includes("instagram") ? "instagram" : "facebook";
  chrome.runtime.sendMessage({ type: "META_PAGE_VISIT", platform });
} catch (e) {
  // Extension context may not be ready yet
}

// ── Meta GraphQL proxy ──────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "META_GRAPHQL_PROXY") return false;

  const { url, options } = message;

  (async () => {
    try {
      const resp = await fetch(url, {
        ...options,
        credentials: "same-origin",
      });

      const status = resp.status;
      if (!resp.ok) {
        const body = await resp.text().catch(() => "");
        sendResponse({ ok: false, status, body: body.substring(0, 2000) });
        return;
      }

      const data = await resp.json();
      sendResponse({ ok: true, status, data });
    } catch (e) {
      sendResponse({ ok: false, status: 0, body: e.message });
    }
  })();

  return true;
});
```

- [ ] **Step 3: Commit**

```bash
git add chrome-extension/manifest.json chrome-extension/content/meta-notify.js
git commit -m "feat: add Meta host permissions and content script to Chrome extension"
```

---

### Task 5: Chrome Extension — Meta GraphQL Client

**Files:**
- Create: `chrome-extension/background/meta-client.js`

- [ ] **Step 1: Create meta-client.js**

Create `chrome-extension/background/meta-client.js`:

```javascript
/**
 * Meta GraphQL API client for Chrome extension service worker.
 *
 * Executes GraphQL requests inside Facebook/Instagram tabs via
 * chrome.scripting.executeScript — required for MV3 cookie access.
 * Extracts fb_dtsg CSRF token from page context.
 */

const META_GRAPHQL_URL = "https://www.facebook.com/api/graphql/";

/**
 * Find a Facebook or Instagram tab to execute requests in.
 * @param {"facebook"|"instagram"} platform
 * @returns {Promise<number>} Tab ID
 * @throws {Error} "NO_META_TAB" if none found
 */
async function _requireMetaTab(platform) {
  const pattern = platform === "instagram"
    ? "https://www.instagram.com/*"
    : "https://www.facebook.com/*";
  const tabs = await chrome.tabs.query({ url: pattern });
  const tabId = tabs.find(t => t.active)?.id ?? tabs[0]?.id;
  if (!tabId) throw new Error("NO_META_TAB");
  return tabId;
}

/**
 * Execute a Meta GraphQL query inside a Facebook/Instagram tab.
 *
 * @param {string} docId - GraphQL doc_id (query hash)
 * @param {Object} variables - Query variables
 * @param {"facebook"|"instagram"} platform - Which tab to use
 * @returns {Promise<Object>} Parsed JSON response
 */
async function metaGraphQL(docId, variables, platform = "facebook") {
  const tabId = await _requireMetaTab(platform);

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (graphqlUrl, docId, variablesJson) => {
      try {
        // Extract fb_dtsg from page — it's in a hidden input or __comet_req config
        let fbDtsg = "";

        // Method 1: hidden input (most reliable)
        const dtsgInput = document.querySelector('input[name="fb_dtsg"]');
        if (dtsgInput) {
          fbDtsg = dtsgInput.value;
        }

        // Method 2: __comet_req script data
        if (!fbDtsg) {
          const scripts = document.querySelectorAll("script");
          for (const s of scripts) {
            const text = s.textContent || "";
            const match = text.match(/"DTSGInitialData"[^}]*"token":"([^"]+)"/);
            if (match) {
              fbDtsg = match[1];
              break;
            }
          }
        }

        if (!fbDtsg) {
          return { ok: false, status: 0, body: "NO_FB_DTSG" };
        }

        const formData = new URLSearchParams();
        formData.append("fb_dtsg", fbDtsg);
        formData.append("doc_id", docId);
        formData.append("variables", variablesJson);

        const resp = await fetch(graphqlUrl, {
          method: "POST",
          body: formData,
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
        });

        if (!resp.ok) {
          const text = await resp.text().catch(() => "");
          return { ok: false, status: resp.status, body: text.substring(0, 2000) };
        }

        const data = await resp.json();
        return { ok: true, status: resp.status, data };
      } catch (e) {
        return { ok: false, status: 0, body: e.message };
      }
    },
    args: [META_GRAPHQL_URL, docId, JSON.stringify(variables)],
    world: "MAIN",
  });

  const result = results?.[0]?.result;
  if (!result) throw new Error("SCRIPT_EXEC_FAILED");

  if (result.status === 429) {
    const error = new Error("RATE_LIMITED");
    error.retryAfter = 900;
    throw error;
  }
  if (result.status === 401 || result.status === 403) {
    throw new Error("AUTH_EXPIRED");
  }
  if (!result.ok) {
    console.error(`[MetaClient] ${result.status}: ${result.body}`);
    throw new Error(`META_ERROR:${result.status}`);
  }

  return result.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add chrome-extension/background/meta-client.js
git commit -m "feat: add Meta GraphQL client for Chrome extension"
```

---

### Task 6: Chrome Extension — Meta Sync Utils

**Files:**
- Create: `chrome-extension/background/meta-sync-utils.js`

- [ ] **Step 1: Create meta-sync-utils.js**

Create `chrome-extension/background/meta-sync-utils.js`:

```javascript
/**
 * Shared utilities for Meta sync: constants, cookie helpers,
 * response parsers.
 *
 * Loaded via importScripts before sync-facebook.js / sync-instagram.js.
 */

// ── Constants ────────────────────────────────────────────────────────────────

const META_SYNC_THROTTLE_MS = 15 * 60 * 1000;       // 15 min between auto-syncs
const META_RATE_LIMIT_DELAY_MS = 1000;                // 1 sec between GraphQL calls
const META_BACKFILL_WINDOW_MS = 30 * 24 * 60 * 60 * 1000; // 30 days for first sync
const META_CONVERSATION_MAX = 50;                     // max conversations per sync cycle
const META_MESSAGES_PER_CONV_MAX = 100;               // max messages per conversation

// ── Cookie helpers ───────────────────────────────────────────────────────────

/**
 * Read Meta session cookies.
 * @returns {Promise<{cUser: string, xs: string}>}
 * @throws {Error} "MISSING_META_COOKIES" if c_user or xs missing
 */
async function _readMetaCookies() {
  const cookies = await chrome.cookies.getAll({ domain: ".facebook.com" });
  const map = Object.fromEntries(cookies.map(c => [c.name, c.value]));
  const cUser = map["c_user"];
  const xs = map["xs"];
  if (!cUser || !xs) throw new Error("MISSING_META_COOKIES");
  return { cUser, xs };
}

// ── Delay helper ─────────────────────────────────────────────────────────────

function _metaDelay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ── Messenger parsers ────────────────────────────────────────────────────────

/**
 * Parse conversations from Messenger GraphQL response.
 * @param {Object} raw - GraphQL response
 * @returns {Array} Array of thread objects
 */
function _parseMetaConversations(raw) {
  // LSPlatformGraphQLLightspeedRequestQuery response
  const threads = raw?.data?.viewer?.message_threads?.nodes ?? [];
  if (threads.length > 0) return threads;

  // Alternate path
  const edges = raw?.data?.viewer?.message_threads?.edges ?? [];
  return edges.map(e => e.node).filter(Boolean);
}

/**
 * Parse messages from a Messenger thread.
 * @param {Object} raw - GraphQL response for thread messages
 * @returns {Array} Array of message objects
 */
function _parseMetaMessages(raw) {
  const nodes = raw?.data?.message_thread?.messages?.nodes ?? [];
  if (nodes.length > 0) return nodes;

  const edges = raw?.data?.message_thread?.messages?.edges ?? [];
  return edges.map(e => e.node).filter(Boolean);
}

/**
 * Convert a Messenger message into the shape expected by /meta/push.
 */
function _metaMessageToPayload(msg, conversationId, partnerId, partnerName, selfUserId) {
  const text = msg?.snippet ?? msg?.message?.text ?? msg?.body ?? "";
  const timestamp = msg?.timestamp_precise
    ? new Date(parseInt(msg.timestamp_precise)).toISOString()
    : new Date(msg?.timestamp ?? Date.now()).toISOString();

  const senderId = msg?.message_sender?.id ?? msg?.sender?.id ?? null;
  const direction = senderId === selfUserId ? "outbound" : "inbound";

  const reactions = (msg?.message_reactions ?? []).map(r => ({
    reactor_id: r?.user?.id ?? "",
    type: r?.reaction ?? "like",
  }));

  const readBy = (msg?.read_receipts?.nodes ?? []).map(r => r?.user?.id).filter(Boolean);

  return {
    message_id: msg?.message_id ?? `${conversationId}:${msg?.timestamp_precise ?? Date.now()}`,
    conversation_id: conversationId,
    platform_id: partnerId,
    sender_name: partnerName ?? partnerId ?? "",
    direction,
    content_preview: String(text).substring(0, 500),
    timestamp,
    reactions,
    read_by: readBy,
  };
}

// ── Instagram DM parsers ─────────────────────────────────────────────────────

/**
 * Parse Instagram DM threads.
 */
function _parseInstagramThreads(raw) {
  const threads = raw?.data?.viewer?.inbox?.threads?.nodes ?? [];
  if (threads.length > 0) return threads;

  const edges = raw?.data?.viewer?.inbox?.threads?.edges ?? [];
  return edges.map(e => e.node).filter(Boolean);
}

/**
 * Parse messages from an Instagram DM thread.
 */
function _parseInstagramMessages(raw) {
  const items = raw?.data?.message_thread?.messages?.nodes
    ?? raw?.data?.xdt_message_thread?.messages?.nodes
    ?? [];
  if (items.length > 0) return items;

  const edges = raw?.data?.message_thread?.messages?.edges
    ?? raw?.data?.xdt_message_thread?.messages?.edges
    ?? [];
  return edges.map(e => e.node).filter(Boolean);
}

/**
 * Convert an Instagram DM message into the shape expected by /meta/push.
 */
function _igMessageToPayload(msg, conversationId, partnerId, partnerName, selfUserId) {
  const text = msg?.text ?? msg?.message?.text ?? "";
  const timestamp = msg?.timestamp
    ? new Date(parseInt(msg.timestamp) / 1000).toISOString()
    : new Date().toISOString();

  const senderId = msg?.sender?.id ?? msg?.user_id ?? null;
  const direction = senderId === selfUserId ? "outbound" : "inbound";

  const reactions = (msg?.reactions ?? []).map(r => ({
    reactor_id: r?.user?.id ?? r?.sender_id ?? "",
    type: r?.emoji ?? r?.reaction ?? "like",
  }));

  const seenBy = (msg?.seen_by ?? []).map(u => u?.id ?? u).filter(Boolean);

  return {
    message_id: msg?.item_id ?? msg?.message_id ?? `ig:${conversationId}:${Date.now()}`,
    conversation_id: conversationId,
    platform_id: partnerId,
    sender_name: partnerName ?? partnerId ?? "",
    direction,
    content_preview: String(text).substring(0, 500),
    timestamp,
    reactions,
    read_by: seenBy,
  };
}

// ── Error handler ────────────────────────────────────────────────────────────

async function _handleMetaSyncError(e, result) {
  result.error = e.message;

  if (e.message === "RATE_LIMITED") {
    const waitMs = (e.retryAfter ?? 900) * 1000;
    const nextRetryAt = new Date(Date.now() + waitMs).toISOString();
    await chrome.storage.local.set({ metaNextRetryAt: nextRetryAt });
  } else if (e.message === "NO_META_TAB") {
    console.warn("[MetaSync] No Facebook/Instagram tab open");
  } else if (e.message === "AUTH_EXPIRED") {
    try {
      await _readMetaCookies();
      console.warn("[MetaSync] GraphQL auth rejected but cookies present");
      result.error = "META_AUTH_REJECTED";
    } catch {
      await chrome.storage.local.set({ metaCookiesValid: false });
    }
  }

  return result;
}
```

- [ ] **Step 2: Commit**

```bash
git add chrome-extension/background/meta-sync-utils.js
git commit -m "feat: add Meta sync utilities (constants, parsers, cookie helpers)"
```

---

### Task 7: Chrome Extension — Facebook Messenger Sync

**Files:**
- Create: `chrome-extension/background/sync-facebook.js`

- [ ] **Step 1: Create sync-facebook.js**

Create `chrome-extension/background/sync-facebook.js`:

```javascript
/**
 * Facebook Messenger sync orchestrator.
 *
 * Fetches conversations and messages via Meta's internal GraphQL API,
 * then pushes results to the PingCRM backend.
 *
 * Storage keys (chrome.storage.local):
 *   fbWatermark        - ISO timestamp of newest message (delta cursor)
 *   lastFacebookSync   - ISO timestamp of last sync completion
 *   metaNextRetryAt    - ISO timestamp; block syncs until (rate-limit backoff)
 *   metaCookiesValid   - boolean
 */

// GraphQL doc_id hashes — these are Meta's internal query identifiers.
// They may change when Meta deploys updates; update as needed.
const FB_CONVERSATIONS_DOC_ID = "8845758248780392";  // LSPlatformGraphQLLightspeedRequestQuery
const FB_MESSAGES_DOC_ID = "9106571592726805";        // thread messages query

let _fbSyncRunning = false;

/**
 * Run a Facebook Messenger sync cycle.
 *
 * @param {string} apiUrl - PingCRM backend base URL
 * @param {string} token  - Bearer token for the backend
 * @param {boolean} [force=false] - Skip throttle check
 * @returns {Promise<Object>} { skipped, conversations, messages, error }
 */
async function runFacebookSync(apiUrl, token, force = false) {
  const result = { skipped: false, conversations: 0, messages: 0, error: null };

  if (_fbSyncRunning) {
    result.skipped = true;
    return result;
  }
  _fbSyncRunning = true;

  try {
    return await _runFacebookSyncInner(apiUrl, token, force, result);
  } finally {
    _fbSyncRunning = false;
  }
}

async function _runFacebookSyncInner(apiUrl, token, force, result) {
  // ── Throttle check ──
  if (!force) {
    const stored = await chrome.storage.local.get(["lastFacebookSync", "metaNextRetryAt"]);

    if (stored.metaNextRetryAt && Date.now() < new Date(stored.metaNextRetryAt).getTime()) {
      result.skipped = true;
      return result;
    }

    if (stored.lastFacebookSync) {
      const elapsed = Date.now() - new Date(stored.lastFacebookSync).getTime();
      if (elapsed < META_SYNC_THROTTLE_MS) {
        result.skipped = true;
        return result;
      }
    }
  }

  // ── Read cookies ──
  let cUser;
  try {
    ({ cUser } = await _readMetaCookies());
  } catch (e) {
    result.error = e.message;
    await chrome.storage.local.set({ metaCookiesValid: false });
    return result;
  }

  await chrome.storage.local.set({ metaCookiesValid: true });
  console.log("[FBSync] Cookies OK, self user ID:", cUser);

  // ── Determine sync mode ──
  const { fbWatermark } = await chrome.storage.local.get(["fbWatermark"]);
  const isFirstSync = !fbWatermark;
  const cutoffMs = isFirstSync
    ? Date.now() - META_BACKFILL_WINDOW_MS
    : new Date(fbWatermark).getTime();

  // ── Fetch conversations ──
  let conversations;
  try {
    const raw = await metaGraphQL(FB_CONVERSATIONS_DOC_ID, {
      limit: META_CONVERSATION_MAX,
      before: null,
    }, "facebook");
    conversations = _parseMetaConversations(raw);
    await _metaDelay(META_RATE_LIMIT_DELAY_MS);
  } catch (e) {
    return await _handleMetaSyncError(e, result);
  }

  result.conversations = conversations.length;
  console.log("[FBSync] Fetched", conversations.length, "conversations");

  // ── Process conversations → messages ──
  const allMessages = [];
  let newestTimestamp = fbWatermark ? new Date(fbWatermark).getTime() : 0;

  for (const thread of conversations) {
    const threadId = thread?.thread_key?.thread_fbid ?? thread?.id ?? null;
    if (!threadId) continue;

    const lastActivityMs = thread?.updated_time_precise
      ? parseInt(thread.updated_time_precise)
      : (thread?.updated_time ?? 0) * 1000;

    if (!isFirstSync && lastActivityMs <= cutoffMs) continue;

    // Identify conversation partner
    const participants = thread?.all_participants?.nodes ?? thread?.participants?.nodes ?? [];
    const partner = participants.find(p => (p?.id ?? p?.messaging_actor?.id) !== cUser);
    const partnerId = partner?.id ?? partner?.messaging_actor?.id ?? null;
    const partnerName = partner?.name ?? partner?.messaging_actor?.name ?? "Unknown";

    // Fetch messages for this thread
    let messages;
    try {
      const msgRaw = await metaGraphQL(FB_MESSAGES_DOC_ID, {
        thread_id: threadId,
        message_limit: META_MESSAGES_PER_CONV_MAX,
      }, "facebook");
      messages = _parseMetaMessages(msgRaw);
      await _metaDelay(META_RATE_LIMIT_DELAY_MS);
    } catch (e) {
      if (e.message === "RATE_LIMITED" || e.message === "AUTH_EXPIRED") {
        return await _handleMetaSyncError(e, result);
      }
      console.warn("[FBSync] Failed to fetch messages for thread", threadId, e.message);
      continue;
    }

    for (const msg of messages) {
      const createdAtMs = msg?.timestamp_precise
        ? parseInt(msg.timestamp_precise)
        : (msg?.timestamp ?? 0) * 1000;

      if (!isFirstSync && createdAtMs <= cutoffMs) continue;

      const payload = _metaMessageToPayload(msg, threadId, partnerId, partnerName, cUser);
      allMessages.push(payload);

      if (createdAtMs > newestTimestamp) newestTimestamp = createdAtMs;
    }
  }

  result.messages = allMessages.length;
  console.log("[FBSync] Extracted", allMessages.length, "messages");

  // ── Push to backend ──
  try {
    const pushResp = await fetch(`${apiUrl}/api/v1/meta/push`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        platform: "facebook",
        profiles: [],
        messages: allMessages,
      }),
    });

    if (!pushResp.ok) {
      const errBody = await pushResp.text().catch(() => "");
      console.error("[FBSync] Push failed:", pushResp.status, errBody.substring(0, 500));
      if (pushResp.status === 401) {
        result.error = "AUTH_EXPIRED";
        return result;
      }
      result.error = `PUSH_FAILED:${pushResp.status}`;
      return result;
    }

    const pushData = (await pushResp.json())?.data ?? {};
    console.log("[FBSync] Push OK:", pushData);
  } catch (e) {
    result.error = e.message;
    return result;
  }

  // ── Persist watermark ──
  const updates = { lastFacebookSync: new Date().toISOString(), metaNextRetryAt: null };
  if (newestTimestamp > 0) {
    updates.fbWatermark = new Date(newestTimestamp).toISOString();
  }
  await chrome.storage.local.set(updates);

  return result;
}
```

- [ ] **Step 2: Commit**

```bash
git add chrome-extension/background/sync-facebook.js
git commit -m "feat: add Facebook Messenger sync orchestrator"
```

---

### Task 8: Chrome Extension — Instagram DM Sync

**Files:**
- Create: `chrome-extension/background/sync-instagram.js`

- [ ] **Step 1: Create sync-instagram.js**

Create `chrome-extension/background/sync-instagram.js`:

```javascript
/**
 * Instagram DM sync orchestrator.
 *
 * Fetches DM threads and messages via Meta's internal GraphQL API
 * (shared with Facebook), then pushes to PingCRM backend.
 *
 * Storage keys (chrome.storage.local):
 *   igWatermark        - ISO timestamp of newest message (delta cursor)
 *   lastInstagramSync  - ISO timestamp of last sync completion
 *   metaNextRetryAt    - shared with Facebook sync
 *   metaCookiesValid   - shared with Facebook sync
 */

// Instagram DM GraphQL doc_ids
const IG_THREADS_DOC_ID = "6707582879298508";   // IGDInboxQuery
const IG_MESSAGES_DOC_ID = "7123744197665318";   // thread detail query

let _igSyncRunning = false;

/**
 * Run an Instagram DM sync cycle.
 *
 * @param {string} apiUrl - PingCRM backend base URL
 * @param {string} token  - Bearer token for the backend
 * @param {boolean} [force=false] - Skip throttle check
 * @returns {Promise<Object>} { skipped, conversations, messages, error }
 */
async function runInstagramSync(apiUrl, token, force = false) {
  const result = { skipped: false, conversations: 0, messages: 0, error: null };

  if (_igSyncRunning) {
    result.skipped = true;
    return result;
  }
  _igSyncRunning = true;

  try {
    return await _runInstagramSyncInner(apiUrl, token, force, result);
  } finally {
    _igSyncRunning = false;
  }
}

async function _runInstagramSyncInner(apiUrl, token, force, result) {
  // ── Throttle check ──
  if (!force) {
    const stored = await chrome.storage.local.get(["lastInstagramSync", "metaNextRetryAt"]);

    if (stored.metaNextRetryAt && Date.now() < new Date(stored.metaNextRetryAt).getTime()) {
      result.skipped = true;
      return result;
    }

    if (stored.lastInstagramSync) {
      const elapsed = Date.now() - new Date(stored.lastInstagramSync).getTime();
      if (elapsed < META_SYNC_THROTTLE_MS) {
        result.skipped = true;
        return result;
      }
    }
  }

  // ── Read cookies (shared Meta session) ──
  let cUser;
  try {
    ({ cUser } = await _readMetaCookies());
  } catch (e) {
    result.error = e.message;
    await chrome.storage.local.set({ metaCookiesValid: false });
    return result;
  }

  await chrome.storage.local.set({ metaCookiesValid: true });
  console.log("[IGSync] Cookies OK, self user ID:", cUser);

  // ── Determine sync mode ──
  const { igWatermark } = await chrome.storage.local.get(["igWatermark"]);
  const isFirstSync = !igWatermark;
  const cutoffMs = isFirstSync
    ? Date.now() - META_BACKFILL_WINDOW_MS
    : new Date(igWatermark).getTime();

  // ── Fetch threads ──
  let threads;
  try {
    // Instagram DMs use the same GraphQL endpoint but via instagram.com tab
    const raw = await metaGraphQL(IG_THREADS_DOC_ID, {
      limit: META_CONVERSATION_MAX,
      before: null,
    }, "instagram");
    threads = _parseInstagramThreads(raw);
    await _metaDelay(META_RATE_LIMIT_DELAY_MS);
  } catch (e) {
    return await _handleMetaSyncError(e, result);
  }

  result.conversations = threads.length;
  console.log("[IGSync] Fetched", threads.length, "threads");

  // ── Process threads → messages ──
  const allMessages = [];
  let newestTimestamp = igWatermark ? new Date(igWatermark).getTime() : 0;

  for (const thread of threads) {
    const threadId = thread?.thread_id ?? thread?.id ?? null;
    if (!threadId) continue;

    const lastActivityMs = thread?.last_activity_at
      ? parseInt(thread.last_activity_at)
      : 0;

    if (!isFirstSync && lastActivityMs <= cutoffMs) continue;

    // Identify conversation partner
    const users = thread?.users ?? thread?.participants ?? [];
    const partner = users.find(u => (u?.pk ?? u?.id) !== cUser);
    const partnerId = partner?.pk ?? partner?.id ?? null;
    const partnerName = partner?.full_name ?? partner?.username ?? "Unknown";
    const partnerUsername = partner?.username ?? null;

    // Fetch messages for this thread
    let messages;
    try {
      const msgRaw = await metaGraphQL(IG_MESSAGES_DOC_ID, {
        thread_id: threadId,
        message_limit: META_MESSAGES_PER_CONV_MAX,
      }, "instagram");
      messages = _parseInstagramMessages(msgRaw);
      await _metaDelay(META_RATE_LIMIT_DELAY_MS);
    } catch (e) {
      if (e.message === "RATE_LIMITED" || e.message === "AUTH_EXPIRED") {
        return await _handleMetaSyncError(e, result);
      }
      console.warn("[IGSync] Failed to fetch messages for thread", threadId, e.message);
      continue;
    }

    for (const msg of messages) {
      const createdAtMs = msg?.timestamp ? parseInt(msg.timestamp) / 1000 : 0;

      if (!isFirstSync && createdAtMs <= cutoffMs) continue;

      const payload = _igMessageToPayload(msg, threadId, partnerId, partnerName, cUser);
      allMessages.push(payload);

      if (createdAtMs > newestTimestamp) newestTimestamp = createdAtMs;
    }
  }

  result.messages = allMessages.length;
  console.log("[IGSync] Extracted", allMessages.length, "messages");

  // ── Push to backend ──
  try {
    // Build profiles from thread partners for contact creation
    const profilesSeen = new Set();
    const profiles = [];
    for (const thread of threads) {
      const users = thread?.users ?? thread?.participants ?? [];
      const partner = users.find(u => (u?.pk ?? u?.id) !== cUser);
      if (!partner) continue;
      const pid = partner?.pk ?? partner?.id;
      if (!pid || profilesSeen.has(pid)) continue;
      profilesSeen.add(pid);
      profiles.push({
        platform_id: pid,
        name: partner?.full_name ?? partner?.username ?? "",
        username: partner?.username ?? null,
        avatar_url: partner?.profile_pic_url ?? null,
      });
    }

    const pushResp = await fetch(`${apiUrl}/api/v1/meta/push`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        platform: "instagram",
        profiles,
        messages: allMessages,
      }),
    });

    if (!pushResp.ok) {
      const errBody = await pushResp.text().catch(() => "");
      console.error("[IGSync] Push failed:", pushResp.status, errBody.substring(0, 500));
      if (pushResp.status === 401) {
        result.error = "AUTH_EXPIRED";
        return result;
      }
      result.error = `PUSH_FAILED:${pushResp.status}`;
      return result;
    }

    const pushData = (await pushResp.json())?.data ?? {};
    console.log("[IGSync] Push OK:", pushData);
  } catch (e) {
    result.error = e.message;
    return result;
  }

  // ── Persist watermark ──
  const updates = { lastInstagramSync: new Date().toISOString(), metaNextRetryAt: null };
  if (newestTimestamp > 0) {
    updates.igWatermark = new Date(newestTimestamp).toISOString();
  }
  await chrome.storage.local.set(updates);

  return result;
}
```

- [ ] **Step 2: Commit**

```bash
git add chrome-extension/background/sync-instagram.js
git commit -m "feat: add Instagram DM sync orchestrator"
```

---

### Task 9: Chrome Extension — Service Worker Integration

**Files:**
- Modify: `chrome-extension/background/service-worker.js`

- [ ] **Step 1: Add Meta module imports to service worker**

In `chrome-extension/background/service-worker.js`, update the `importScripts` line (line 9):

```javascript
importScripts("../lib/storage.js", "voyager-client.js", "sync-utils.js", "sync.js", "pairing.js", "meta-client.js", "meta-sync-utils.js", "sync-facebook.js", "sync-instagram.js");
```

- [ ] **Step 2: Add Meta sync throttle state**

After `_lastProfileSyncAt` / `PROFILE_SYNC_THROTTLE_MS` (line 48), add:

```javascript
// ── Throttle state for Meta auto-sync ────────────────────────────────────────
let _lastMetaSyncAt = 0;
const META_AUTO_SYNC_THROTTLE_MS = 5 * 60 * 1000; // 5 minutes

async function _maybeRunMetaSync(platform) {
  if (Date.now() - _lastMetaSyncAt < META_AUTO_SYNC_THROTTLE_MS) return;
  _lastMetaSyncAt = Date.now();

  const { apiUrl, token, metaSyncFacebook, metaSyncInstagram } = await chrome.storage.local.get([
    "apiUrl", "token", "metaSyncFacebook", "metaSyncInstagram",
  ]);
  if (!apiUrl || !token) return;

  if (platform === "facebook" && metaSyncFacebook !== false) {
    const result = await runFacebookSync(apiUrl, token, false);
    if (result.error) {
      console.warn("[SW] Auto Meta sync error (facebook):", result.error);
    }
  }

  if (platform === "instagram" && metaSyncInstagram !== false) {
    const result = await runInstagramSync(apiUrl, token, false);
    if (result.error) {
      console.warn("[SW] Auto Meta sync error (instagram):", result.error);
    }
  }
}
```

- [ ] **Step 3: Add META_PAGE_VISIT handler**

In the `chrome.runtime.onMessage.addListener` callback, add before the `return false;` at the end (before line 338):

```javascript
  // META_PAGE_VISIT — user visited Facebook or Instagram
  if (message.type === "META_PAGE_VISIT") {
    (async () => {
      try {
        const cookies = await chrome.cookies.getAll({ domain: ".facebook.com" });
        const cUser = cookies.find(c => c.name === "c_user")?.value;
        const xs = cookies.find(c => c.name === "xs")?.value;
        const valid = !!(cUser && xs);
        await chrome.storage.local.set({ metaCookiesValid: valid });
        console.log("[SW] Meta cookie refresh:", valid ? "valid" : "missing");

        if (valid) {
          _maybeRunMetaSync(message.platform).catch(e =>
            console.warn("[SW] Auto Meta sync failed:", e.message)
          );
        }
      } catch (e) {
        console.warn("[SW] Meta cookie refresh failed:", e.message);
      }
      sendResponse({ ok: true });
    })();
    return true;
  }

  // META_SYNC_NOW — force Meta sync (from popup or frontend)
  if (message.type === "META_SYNC_NOW") {
    (async () => {
      try {
        const { apiUrl, token } = await chrome.storage.local.get(["apiUrl", "token"]);
        if (!apiUrl || !token) {
          sendResponse({ ok: false, error: "Not paired" });
          return;
        }

        setBadge("...", "#64748b");
        const platform = message.platform || "both";

        let fbResult = { skipped: true, conversations: 0, messages: 0 };
        let igResult = { skipped: true, conversations: 0, messages: 0 };

        if (platform === "facebook" || platform === "both") {
          fbResult = await runFacebookSync(apiUrl, token, true);
          if (fbResult.error) {
            setBadge("X", "#FF9800");
            sendResponse({ ok: false, error: fbResult.error, platform: "facebook" });
            return;
          }
        }

        if (platform === "instagram" || platform === "both") {
          igResult = await runInstagramSync(apiUrl, token, true);
          if (igResult.error) {
            setBadge("X", "#FF9800");
            sendResponse({ ok: false, error: igResult.error, platform: "instagram" });
            return;
          }
        }

        setBadge("OK", "#4CAF50");
        setTimeout(() => setBadge("", ""), 3000);

        sendResponse({
          ok: true,
          facebook: {
            conversations: fbResult.conversations,
            messages: fbResult.messages,
          },
          instagram: {
            conversations: igResult.conversations,
            messages: igResult.messages,
          },
        });
      } catch (e) {
        console.error("[SW] META_SYNC_NOW crashed:", e.message, e.stack);
        setBadge("X", "#FF9800");
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true;
  }
```

- [ ] **Step 4: Commit**

```bash
git add chrome-extension/background/service-worker.js
git commit -m "feat: integrate Meta sync modules into Chrome extension service worker"
```

---

### Task 10: Frontend — Meta Card Component

**Files:**
- Create: `frontend/src/app/settings/_components/platform-cards/meta-card.tsx`
- Modify: `frontend/src/app/settings/_components/integrations-tab.tsx`
- Modify: `frontend/src/app/settings/_hooks/use-settings-controller.ts`

- [ ] **Step 1: Add Meta fields to ConnectedAccounts interface**

In `frontend/src/app/settings/_hooks/use-settings-controller.ts`, add to the `ConnectedAccounts` interface (after `whatsapp_phone`):

```typescript
  meta_connected: boolean;
  meta_connected_name?: string | null;
  meta_sync_facebook: boolean;
  meta_sync_instagram: boolean;
```

And in the `useState<ConnectedAccounts>` default (around line 126), add the new defaults:

```typescript
    meta_connected: false,
    meta_connected_name: null,
    meta_sync_facebook: true,
    meta_sync_instagram: true,
```

- [ ] **Step 2: Create meta-card.tsx**

Create `frontend/src/app/settings/_components/platform-cards/meta-card.tsx`:

```tsx
"use client";

import { useState } from "react";
import { RefreshCw, Check, History, Unplug } from "lucide-react";
import { cn } from "@/lib/utils";
import { ConnectionBadge, KebabMenu, SyncButtonWrapper } from "../shared";
import { SyncHistoryModal } from "../sync-history-modal";
import type { ConnectedAccounts } from "../../_hooks/use-settings-controller";
import type { SyncPhase } from "../shared";

function MetaIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2C6.477 2 2 6.477 2 12c0 4.991 3.657 9.128 8.438 9.879V14.89h-2.54V12h2.54V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.89h-2.33v6.989C18.343 21.129 22 16.99 22 12c0-5.523-4.477-10-10-10z"
        fill="#1877F2"
      />
    </svg>
  );
}

export interface MetaCardProps {
  connected: ConnectedAccounts;
  fetchConnectionStatus: () => Promise<void>;
}

export function MetaCard({ connected, fetchConnectionStatus }: MetaCardProps) {
  const [syncStatus, setSyncStatus] = useState<SyncPhase>("idle");
  const [showSyncHistory, setShowSyncHistory] = useState(false);
  const [showFbHistory, setShowFbHistory] = useState(false);

  const isConnected = connected.meta_connected;

  async function handleSync() {
    setSyncStatus("loading");

    // Send META_SYNC_NOW message to extension via content script relay
    try {
      // Try postMessage to extension content script
      window.postMessage({ type: "PINGCRM_META_SYNC", platform: "both" }, "*");

      // Fallback timeout — the extension will push data to backend directly
      setTimeout(() => {
        setSyncStatus("success");
        setTimeout(() => setSyncStatus("idle"), 2000);
        void fetchConnectionStatus();
      }, 3000);
    } catch {
      setSyncStatus("error");
      setTimeout(() => setSyncStatus("idle"), 3000);
    }
  }

  return (
    <>
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 hover:shadow-sm transition-shadow">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            <div
              className={cn(
                "w-11 h-11 rounded-lg flex items-center justify-center shrink-0",
                isConnected ? "bg-blue-50 dark:bg-blue-950" : "bg-stone-100 dark:bg-stone-800"
              )}
            >
              <MetaIcon />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Meta</h3>
                <ConnectionBadge connected={isConnected} />
              </div>
              <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
                Sync Facebook Messenger &amp; Instagram DMs via browser extension
              </p>
              {isConnected && connected.meta_connected_name && (
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                  Connected &middot; <strong>{connected.meta_connected_name}</strong>
                </p>
              )}
              {isConnected && (
                <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
                  {connected.meta_sync_facebook ? "Messenger" : ""}
                  {connected.meta_sync_facebook && connected.meta_sync_instagram ? " + " : ""}
                  {connected.meta_sync_instagram ? "Instagram DMs" : ""}
                  {!connected.meta_sync_facebook && !connected.meta_sync_instagram ? "No platforms enabled" : " enabled"}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isConnected ? (
              <>
                <SyncButtonWrapper phase={syncStatus}>
                  <button
                    onClick={() => void handleSync()}
                    disabled={syncStatus === "loading"}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors disabled:opacity-50"
                  >
                    {syncStatus === "loading" ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : syncStatus === "success" ? (
                      <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5" />
                    )}
                    {syncStatus === "loading"
                      ? "Syncing..."
                      : syncStatus === "success"
                      ? "Done"
                      : "Sync now"}
                  </button>
                </SyncButtonWrapper>
                <KebabMenu
                  items={[
                    { icon: History, label: "Messenger history", onClick: () => setShowSyncHistory(true) },
                    { icon: History, label: "Instagram history", onClick: () => setShowFbHistory(true) },
                    { icon: Unplug, label: "---" },
                    { icon: Unplug, label: "Disconnect Meta", danger: true, onClick: () => {} },
                  ]}
                />
              </>
            ) : (
              <div className="text-xs text-stone-400 dark:text-stone-500 max-w-48 text-right">
                Install extension, visit facebook.com to connect automatically
              </div>
            )}
          </div>
        </div>
      </div>

      {showSyncHistory && <SyncHistoryModal platform="facebook" onClose={() => setShowSyncHistory(false)} />}
      {showFbHistory && <SyncHistoryModal platform="instagram" onClose={() => setShowFbHistory(false)} />}
    </>
  );
}
```

- [ ] **Step 3: Add MetaCard to integrations-tab.tsx**

In `frontend/src/app/settings/_components/integrations-tab.tsx`, add the import:

```typescript
import { MetaCard } from "./platform-cards/meta-card";
```

And add the card after the WhatsAppCard in the JSX:

```tsx
      <MetaCard
        connected={connected}
        fetchConnectionStatus={fetchConnectionStatus}
      />
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/settings/_components/platform-cards/meta-card.tsx frontend/src/app/settings/_components/integrations-tab.tsx frontend/src/app/settings/_hooks/use-settings-controller.ts
git commit -m "feat: add Meta integration card to settings UI"
```

---

### Task 11: API Type Generation & Final Verification

**Files:**
- Modify: `backend/openapi.json` (auto-generated)
- Modify: `frontend/src/lib/api-types.d.ts` (auto-generated)

- [ ] **Step 1: Regenerate API types**

Run:
```bash
cd backend && PYTHONPATH=. python3 -c "
import json; from app.main import app; from fastapi.openapi.utils import get_openapi
schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
with open('openapi.json', 'w') as f: json.dump(schema, f, indent=2)
"
```

```bash
cd frontend && npm run generate:api
```

- [ ] **Step 2: Run CI guards**

```bash
cd backend && PYTHONPATH=. python3 scripts/check_response_models.py
cd frontend && bash scripts/check-as-any.sh
```

Expected: Both pass

- [ ] **Step 3: Run backend tests**

```bash
cd backend && PYTHONPATH=. pytest --timeout=30 -x -q
```

Expected: All tests pass including new meta push tests

- [ ] **Step 4: Run frontend build check**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no type errors

- [ ] **Step 5: Commit generated files**

```bash
git add backend/openapi.json frontend/src/lib/api-types.d.ts
git commit -m "chore: regenerate API types after Meta integration"
```
