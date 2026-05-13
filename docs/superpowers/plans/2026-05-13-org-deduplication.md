# Organization Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user-initiated dedup flow for organizations — Tier 1 deterministic (auto-merge on shared domain / LinkedIn / name+website) + Tier 2 probabilistic (queue fuzzy pairs for review on a new Orgs tab of `/identity`).

**Architecture:** New `org_identity_matches` table + `org_identity_resolution` service. Reuses contact-side scoring primitives (`_levenshtein`, `_name_similarity`, `_username_similarity`) from `app/services/identity_scoring.py`. Frontend refactors `MatchCard` into a generic `MatchCardShell`, then adds a thin `OrgMatchCard` wrapper. Three logical PRs: backend foundation → API + refactor → org tab UI.

**Tech Stack:** Python (FastAPI, SQLAlchemy, packaging), Alembic, TypeScript (Next.js, React Query, vitest), shared `IdentityMatchShell` UI.

**Spec:** `docs/superpowers/specs/2026-05-13-org-deduplication-design.md`

**Reuse map:**
- `app/services/identity_scoring._levenshtein`, `_name_similarity`, `_username_similarity`, `_normalize_name` — imported as-is
- `app/api/organizations.merge_organizations` endpoint body — refactored to call the new `merge_org_pair` helper (Task 6)
- `frontend/src/app/identity/_components/match-card.tsx` — refactored to wrap `MatchCardShell` (Task 16); public props unchanged
- `frontend/src/components/CompanyFavicon` — used inside `OrgPanel`

---

## Phase 1 — Backend foundation

### Task 1: Add `OrgIdentityMatch` model + migration

**Files:**
- Create: `backend/app/models/org_identity_match.py`
- Create: `backend/alembic/versions/<new_rev>_add_org_identity_matches.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the model**

Create `backend/app/models/org_identity_match.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrgIdentityMatch(Base):
    __tablename__ = "org_identity_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    org_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    # "deterministic_domain" | "deterministic_linkedin" | "deterministic_name_website" | "probabilistic"
    match_method: Mapped[str] = mapped_column(String, nullable=False)
    # "pending_review" | "merged" | "dismissed"
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending_review")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
```

- [ ] **Step 2: Register the model in `__init__.py`**

Open `backend/app/models/__init__.py` and add a line in the import section so the model is loaded on app start (search for existing imports of `IdentityMatch` and add the new one right after):

```python
from app.models.org_identity_match import OrgIdentityMatch  # noqa: F401
```

- [ ] **Step 3: Generate the migration**

Run (from project root):

```bash
cd backend && alembic revision --autogenerate -m "add org_identity_matches"
```

Open the new file in `backend/alembic/versions/`. Auto-generation will create the basic table; you must edit the `upgrade()` function to add the case-insensitive unique pair index (auto-generate can't produce LEAST/GREATEST expressions). Replace the body of `upgrade()` and `downgrade()` with:

```python
def upgrade() -> None:
    op.create_table(
        "org_identity_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("org_a_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_b_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_score", sa.Float, nullable=False),
        sa.Column("match_method", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_org_identity_matches_user_pair",
        "org_identity_matches",
        [sa.text("user_id"), sa.text("LEAST(org_a_id, org_b_id)"), sa.text("GREATEST(org_a_id, org_b_id)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_org_identity_matches_user_pair", table_name="org_identity_matches")
    op.drop_table("org_identity_matches")
```

Make sure these imports exist at the top of the migration:

```python
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
```

- [ ] **Step 4: Apply the migration**

Run: `cd backend && alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> <new_rev>, add org_identity_matches`.

- [ ] **Step 5: Verify model imports cleanly**

Run: `cd backend && PYTHONPATH=. python3 -c "from app.models.org_identity_match import OrgIdentityMatch; print(OrgIdentityMatch.__tablename__)"`
Expected: `org_identity_matches`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/org_identity_match.py backend/alembic/versions/*_add_org_identity_matches.py backend/app/models/__init__.py
git commit -m "feat(orgs): add org_identity_matches table"
```

---

### Task 2: URL normalizers for orgs

**Files:**
- Create: `backend/app/services/org_identity_scoring.py`
- Create: `backend/tests/test_org_identity_scoring.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_org_identity_scoring.py`:

```python
"""Tests for app.services.org_identity_scoring."""
import pytest

from app.services.org_identity_scoring import (
    _normalize_linkedin_url,
    _normalize_website,
    _same_non_generic_domain,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.linkedin.com/company/anthropic/", "linkedin.com/company/anthropic"),
        ("http://linkedin.com/company/anthropic", "linkedin.com/company/anthropic"),
        ("linkedin.com/company/anthropic/", "linkedin.com/company/anthropic"),
        ("https://linkedin.com/company/anthropic-ai/about/", "linkedin.com/company/anthropic-ai"),
        ("", None),
        (None, None),
        ("not a url", None),
    ],
)
def test_normalize_linkedin_url(url, expected):
    assert _normalize_linkedin_url(url) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.anthropic.com/", "anthropic.com"),
        ("http://anthropic.com", "anthropic.com"),
        ("anthropic.com/", "anthropic.com"),
        ("https://anthropic.com/careers", "anthropic.com"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_website(url, expected):
    assert _normalize_website(url) == expected


@pytest.mark.parametrize(
    "domain_a,domain_b,expected",
    [
        ("anthropic.com", "anthropic.com", True),
        ("Anthropic.COM", "anthropic.com", True),
        ("gmail.com", "gmail.com", False),
        ("yahoo.com", "yahoo.com", False),
        ("anthropic.com", "openai.com", False),
        ("anthropic.com", None, False),
        (None, "anthropic.com", False),
        ("", "", False),
    ],
)
def test_same_non_generic_domain(domain_a, domain_b, expected):
    assert _same_non_generic_domain(domain_a, domain_b) is expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py -v`
Expected: ImportError / ModuleNotFoundError on `app.services.org_identity_scoring`.

- [ ] **Step 3: Create the module with the normalizers**

Create `backend/app/services/org_identity_scoring.py`:

```python
"""Identity-resolution scoring primitives for organizations.

Pure helpers (no DB I/O). Mirrors the structure of app.services.identity_scoring
but operates on Organization fields. Reuses _name_similarity, _username_similarity,
_levenshtein, _normalize_name from the contact scoring module.
"""
from __future__ import annotations

import re

from app.models.organization import Organization
from app.services.identity_scoring import (
    _name_similarity,
    _normalize_name,
    _username_similarity,
)

GENERIC_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "mail.com", "aol.com", "protonmail.com",
}

_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/(company|school)/([^/?#]+)",
    re.IGNORECASE,
)


def _normalize_linkedin_url(url: str | None) -> str | None:
    """Return canonical linkedin.com/company/<slug> form, or None for unparseable."""
    if not url:
        return None
    m = _LINKEDIN_RE.search(url.strip())
    if not m:
        return None
    kind, slug = m.group(1).lower(), m.group(2).lower().rstrip("/")
    if not slug:
        return None
    return f"linkedin.com/{kind}/{slug}"


def _normalize_website(url: str | None) -> str | None:
    """Strip protocol, www, trailing slash, path. Return bare host or None."""
    if not url:
        return None
    text = url.strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    text = text.split("/", 1)[0]
    text = text.rstrip("/")
    if not text or "." not in text:
        return None
    return text


def _same_non_generic_domain(a: str | None, b: str | None) -> bool:
    """True iff both are the same domain AND not a generic provider."""
    if not a or not b:
        return False
    da, db = a.strip().lower(), b.strip().lower()
    if not da or not db:
        return False
    if da != db:
        return False
    return da not in GENERIC_DOMAINS
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py -v`
Expected: all parametrized cases pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/org_identity_scoring.py backend/tests/test_org_identity_scoring.py
git commit -m "feat(orgs): URL normalizers + non-generic-domain check"
```

---

### Task 3: LinkedIn match helper

**Files:**
- Modify: `backend/app/services/org_identity_scoring.py`
- Modify: `backend/tests/test_org_identity_scoring.py`

- [ ] **Step 1: Append failing test**

Append to `backend/tests/test_org_identity_scoring.py`:

```python
from app.services.org_identity_scoring import _same_linkedin


@pytest.mark.parametrize(
    "url_a,url_b,expected",
    [
        (
            "https://www.linkedin.com/company/anthropic/",
            "linkedin.com/company/anthropic",
            True,
        ),
        (
            "https://linkedin.com/company/anthropic-ai/about/",
            "https://www.linkedin.com/company/anthropic-ai",
            True,
        ),
        (
            "https://linkedin.com/company/anthropic",
            "https://linkedin.com/company/openai",
            False,
        ),
        ("https://linkedin.com/company/anthropic", None, False),
        (None, None, False),
        ("garbage", "garbage", False),
    ],
)
def test_same_linkedin(url_a, url_b, expected):
    assert _same_linkedin(url_a, url_b) is expected
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py::test_same_linkedin -v`
Expected: ImportError on `_same_linkedin`.

- [ ] **Step 3: Implement `_same_linkedin`**

Append to `backend/app/services/org_identity_scoring.py`:

```python
def _same_linkedin(a: str | None, b: str | None) -> bool:
    """True iff both URLs normalize to the same linkedin.com/company/<slug>."""
    na = _normalize_linkedin_url(a)
    nb = _normalize_linkedin_url(b)
    return na is not None and na == nb
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/org_identity_scoring.py backend/tests/test_org_identity_scoring.py
git commit -m "feat(orgs): _same_linkedin helper"
```

---

### Task 4: `compute_org_adaptive_score`

**Files:**
- Modify: `backend/app/services/org_identity_scoring.py`
- Modify: `backend/tests/test_org_identity_scoring.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_org_identity_scoring.py`:

```python
from dataclasses import dataclass
from typing import Optional

from app.services.org_identity_scoring import compute_org_adaptive_score


@dataclass
class FakeOrg:
    """Stand-in for Organization for pure-scoring tests."""
    name: str
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    website: Optional[str] = None
    twitter_handle: Optional[str] = None


def test_score_identical_orgs_high():
    a = FakeOrg(
        name="Anthropic", domain="anthropic.com",
        linkedin_url="https://linkedin.com/company/anthropic",
        website="https://anthropic.com", twitter_handle="AnthropicAI",
    )
    b = FakeOrg(
        name="Anthropic", domain="anthropic.com",
        linkedin_url="https://www.linkedin.com/company/anthropic/",
        website="https://www.anthropic.com/", twitter_handle="AnthropicAI",
    )
    assert compute_org_adaptive_score(a, b) >= 0.95


def test_score_name_variation_with_shared_domain():
    a = FakeOrg(name="Anthropic", domain="anthropic.com")
    b = FakeOrg(name="Anthropic, Inc.", domain="anthropic.com")
    score = compute_org_adaptive_score(a, b)
    assert 0.60 <= score <= 1.0


def test_score_different_names_shared_domain_capped():
    """Different orgs at same domain (e.g. parent + subsidiary) — cap to force review."""
    a = FakeOrg(name="Google", domain="google.com")
    b = FakeOrg(name="DeepMind", domain="google.com")
    # name_score will be very low; guard caps total at 0.50
    score = compute_org_adaptive_score(a, b)
    assert score <= 0.50


def test_score_single_token_name_no_other_signal_capped():
    a = FakeOrg(name="Acme")
    b = FakeOrg(name="Acme")
    # Single-token names with no corroborating signal -> cap at 0.70 (name-only)
    score = compute_org_adaptive_score(a, b)
    assert score <= 0.70


def test_score_all_signals_none_zero():
    a = FakeOrg(name="")
    b = FakeOrg(name="")
    assert compute_org_adaptive_score(a, b) == 0.0


def test_score_completely_different_low():
    a = FakeOrg(name="Anthropic", domain="anthropic.com")
    b = FakeOrg(name="Stripe", domain="stripe.com")
    assert compute_org_adaptive_score(a, b) < 0.30
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py::test_score_identical_orgs_high -v`
Expected: ImportError on `compute_org_adaptive_score`.

- [ ] **Step 3: Implement `compute_org_adaptive_score`**

Append to `backend/app/services/org_identity_scoring.py`:

```python
def compute_org_adaptive_score(a: Organization, b: Organization) -> float:
    """Adaptive-weight match score for two organizations.

    Base weights: name=0.40, domain=0.20, linkedin=0.20, website=0.10, twitter=0.10.
    Weights for unavailable signals are redistributed across active signals.
    """
    BASE_WEIGHTS = {
        "name":     0.40,
        "domain":   0.20,
        "linkedin": 0.20,
        "website":  0.10,
        "twitter":  0.10,
    }

    name_a = (a.name or "").strip()
    name_b = (b.name or "").strip()

    name_score = _name_similarity(name_a, name_b)
    domain_score = 1.0 if _same_non_generic_domain(a.domain, b.domain) else 0.0
    linkedin_score = 1.0 if _same_linkedin(a.linkedin_url, b.linkedin_url) else 0.0

    nwa = _normalize_website(a.website)
    nwb = _normalize_website(b.website)
    website_score = 1.0 if nwa and nwa == nwb else 0.0

    twitter_score = _username_similarity(a.twitter_handle, b.twitter_handle)

    scores = {
        "name": name_score,
        "domain": domain_score,
        "linkedin": linkedin_score,
        "website": website_score,
        "twitter": twitter_score,
    }

    has_name = bool(name_a) and bool(name_b)
    has_domain = bool(a.domain) and bool(b.domain) and a.domain.lower() not in GENERIC_DOMAINS
    has_linkedin = bool(a.linkedin_url) and bool(b.linkedin_url)
    has_website = bool(nwa) and bool(nwb)
    has_twitter = bool(a.twitter_handle) and bool(b.twitter_handle)

    available = {
        "name": has_name,
        "domain": has_domain,
        "linkedin": has_linkedin,
        "website": has_website,
        "twitter": has_twitter,
    }

    active_weight_sum = sum(BASE_WEIGHTS[k] for k, v in available.items() if v)
    if active_weight_sum == 0:
        return 0.0

    total = 0.0
    for key in BASE_WEIGHTS:
        if available[key]:
            weight = BASE_WEIGHTS[key] / active_weight_sum
            total += weight * scores[key]

    # Guard: name_score very low even when domain+linkedin both fire — likely
    # shared infrastructure (parent/subsidiary), not the same org.
    if has_name and name_score < 0.5 and (domain_score == 1.0 or linkedin_score == 1.0):
        total = min(total, 0.50)

    # Guard: single-token name on either side AND no corroborating signal.
    name_a_tokens = len(_normalize_name(name_a).split())
    name_b_tokens = len(_normalize_name(name_b).split())
    is_single_token = name_a_tokens <= 1 or name_b_tokens <= 1
    if has_name and is_single_token:
        if not has_domain and not has_linkedin and not has_website and not has_twitter:
            total = min(total, 0.50)

    # Cap: when name is the *only* signal, cap at 0.70 to force review.
    active_count = sum(1 for v in available.values() if v)
    if active_count == 1 and has_name:
        total = min(total, 0.70)

    return total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py -v`
Expected: all tests pass (6 scoring tests + previous URL tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/org_identity_scoring.py backend/tests/test_org_identity_scoring.py
git commit -m "feat(orgs): adaptive-weight scoring for org pairs"
```

---

### Task 5: Pair anchor pre-filter

**Files:**
- Modify: `backend/app/services/org_identity_scoring.py`
- Modify: `backend/tests/test_org_identity_scoring.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_org_identity_scoring.py`:

```python
from app.services.org_identity_scoring import _shares_anchor


def test_shares_anchor_name_prefix():
    a = FakeOrg(name="Anthropic")
    b = FakeOrg(name="Anthropic, Inc.")
    assert _shares_anchor(a, b) is True


def test_shares_anchor_domain():
    a = FakeOrg(name="Foo", domain="anthropic.com")
    b = FakeOrg(name="Bar", domain="anthropic.com")
    assert _shares_anchor(a, b) is True


def test_shares_anchor_linkedin():
    a = FakeOrg(name="Foo", linkedin_url="https://linkedin.com/company/anthropic")
    b = FakeOrg(name="Bar", linkedin_url="https://www.linkedin.com/company/anthropic/")
    assert _shares_anchor(a, b) is True


def test_shares_anchor_website():
    a = FakeOrg(name="Foo", website="https://anthropic.com/x")
    b = FakeOrg(name="Bar", website="https://www.anthropic.com/y")
    assert _shares_anchor(a, b) is True


def test_shares_anchor_no_match():
    a = FakeOrg(name="Anthropic", domain="anthropic.com")
    b = FakeOrg(name="Stripe", domain="stripe.com")
    assert _shares_anchor(a, b) is False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py::test_shares_anchor_name_prefix -v`
Expected: ImportError on `_shares_anchor`.

- [ ] **Step 3: Implement `_shares_anchor`**

Append to `backend/app/services/org_identity_scoring.py`:

```python
def _shares_anchor(a: Organization, b: Organization) -> bool:
    """Cheap pre-filter: True if the pair shares *any* fragment worth scoring.

    Cuts O(n^2) pair comparisons down by >95% before the more expensive
    compute_org_adaptive_score runs.
    """
    na = _normalize_name(a.name or "")
    nb = _normalize_name(b.name or "")
    if na and nb and na[:3] == nb[:3]:
        return True

    if _same_non_generic_domain(a.domain, b.domain):
        return True

    if _same_linkedin(a.linkedin_url, b.linkedin_url):
        return True

    nwa = _normalize_website(a.website)
    nwb = _normalize_website(b.website)
    if nwa and nwa == nwb:
        return True

    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/org_identity_scoring.py backend/tests/test_org_identity_scoring.py
git commit -m "feat(orgs): _shares_anchor pre-filter for pair scan"
```

---

### Task 6: `merge_org_pair` helper + extract endpoint logic

**Files:**
- Create: `backend/app/services/org_identity_resolution.py`
- Create: `backend/tests/test_org_identity_resolution.py`
- Modify: `backend/app/api/organizations.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_org_identity_resolution.py`:

```python
"""Tests for app.services.org_identity_resolution.merge_org_pair."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization
from app.models.user import User
from app.services.org_identity_resolution import merge_org_pair


@pytest.mark.asyncio
async def test_merge_org_pair_moves_contacts(db: AsyncSession, test_user: User):
    target = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    source = Organization(user_id=test_user.id, name="Anthropic, Inc.")
    db.add_all([target, source])
    await db.flush()

    c1 = Contact(user_id=test_user.id, full_name="Alice", emails=["a@anthropic.com"],
                 company="Anthropic, Inc.", organization_id=source.id)
    c2 = Contact(user_id=test_user.id, full_name="Bob", emails=["b@anthropic.com"],
                 company="Anthropic, Inc.", organization_id=source.id)
    db.add_all([c1, c2])
    await db.flush()

    moved = await merge_org_pair(target, source, db)
    await db.flush()

    assert moved == 2
    # Source org is gone
    result = await db.execute(select(Organization).where(Organization.id == source.id))
    assert result.scalar_one_or_none() is None
    # Contacts now point at target
    result = await db.execute(
        select(Contact).where(Contact.organization_id == target.id)
    )
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_merge_org_pair_fills_null_target_fields(db: AsyncSession, test_user: User):
    target = Organization(user_id=test_user.id, name="Anthropic")
    source = Organization(
        user_id=test_user.id, name="Anthropic, Inc.",
        domain="anthropic.com",
        linkedin_url="https://linkedin.com/company/anthropic",
        website="https://anthropic.com",
        industry="AI",
    )
    db.add_all([target, source])
    await db.flush()

    await merge_org_pair(target, source, db)
    await db.flush()

    assert target.domain == "anthropic.com"
    assert target.linkedin_url == "https://linkedin.com/company/anthropic"
    assert target.website == "https://anthropic.com"
    assert target.industry == "AI"


@pytest.mark.asyncio
async def test_merge_org_pair_does_not_overwrite_target_fields(
    db: AsyncSession, test_user: User
):
    target = Organization(
        user_id=test_user.id, name="Anthropic",
        domain="anthropic.com", industry="Research",
    )
    source = Organization(
        user_id=test_user.id, name="Anthropic, Inc.",
        domain="other.com", industry="AI",
    )
    db.add_all([target, source])
    await db.flush()

    await merge_org_pair(target, source, db)
    await db.flush()

    # Target's existing values preserved
    assert target.domain == "anthropic.com"
    assert target.industry == "Research"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_resolution.py -v`
Expected: ImportError on `app.services.org_identity_resolution`.

- [ ] **Step 3: Implement `merge_org_pair` and create the module skeleton**

Create `backend/app/services/org_identity_resolution.py`:

```python
"""Organization deduplication: deterministic + probabilistic matching and merging."""
from __future__ import annotations

import logging

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.organization import Organization

logger = logging.getLogger(__name__)

# Fields that get copied source -> target when target has no value
_MERGE_FILL_FIELDS = (
    "domain", "industry", "location", "website",
    "linkedin_url", "twitter_handle", "notes", "logo_url",
)


async def merge_org_pair(
    target: Organization, source: Organization, db: AsyncSession
) -> int:
    """Move source's contacts to target, fill target's null fields from source, delete source.

    Returns the number of contacts moved.

    Conservative on field merge: never overwrites a non-null target field.
    Caller is responsible for choosing which org is the target (typically the
    one with more contacts).
    """
    if target.user_id != source.user_id:
        raise ValueError("Cannot merge orgs across different users")
    if target.id == source.id:
        return 0

    # Fill any null target fields from source
    for field in _MERGE_FILL_FIELDS:
        if getattr(target, field, None) is None:
            src_val = getattr(source, field, None)
            if src_val is not None:
                setattr(target, field, src_val)

    # Move contacts from source to target
    move_result = await db.execute(
        update(Contact)
        .where(
            Contact.organization_id == source.id,
            Contact.user_id == target.user_id,
        )
        .values(organization_id=target.id, company=target.name)
    )
    moved = move_result.rowcount or 0

    # Delete source
    await db.execute(
        delete(Organization).where(
            Organization.id == source.id,
            Organization.user_id == target.user_id,
        )
    )

    logger.info(
        "merge_org_pair: moved %d contacts from %s -> %s",
        moved, source.id, target.id,
        extra={"target_id": str(target.id), "source_id": str(source.id)},
    )
    return moved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_resolution.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Refactor existing `/merge` endpoint to call the helper**

Open `backend/app/api/organizations.py`. Find the `merge_organizations` endpoint body and replace the contact-move + delete blocks with a loop over sources calling `merge_org_pair`. Add the import at the top with the other service imports:

```python
from app.services.org_identity_resolution import merge_org_pair
```

Replace the existing body (the section after the `target_org` lookup) with:

```python
    total_moved = 0
    sources_merged = 0
    for source_id in source_ids:
        source_result = await db.execute(
            select(Organization).where(
                Organization.id == source_id,
                Organization.user_id == current_user.id,
            )
        )
        source_org = source_result.scalar_one_or_none()
        if source_org is None:
            continue
        moved = await merge_org_pair(target_org, source_org, db)
        total_moved += moved
        sources_merged += 1

    return _envelope({
        "target_id": str(target_id),
        "target_name": target_org.name,
        "contacts_updated": total_moved,
        "source_organizations_merged": sources_merged,
    })
```

- [ ] **Step 6: Verify existing merge tests still pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_organizations_api.py -v -k merge`
Expected: existing merge tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/org_identity_resolution.py backend/tests/test_org_identity_resolution.py backend/app/api/organizations.py
git commit -m "feat(orgs): merge_org_pair helper, used by existing merge endpoint"
```

---

### Task 7: `find_deterministic_org_matches`

**Files:**
- Modify: `backend/app/services/org_identity_resolution.py`
- Modify: `backend/tests/test_org_identity_resolution.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_org_identity_resolution.py`:

```python
from app.services.org_identity_resolution import find_deterministic_org_matches


@pytest.mark.asyncio
async def test_deterministic_same_domain(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic, Inc.", domain="anthropic.com")
    c = Organization(user_id=test_user.id, name="Stripe", domain="stripe.com")
    db.add_all([a, b, c])
    await db.flush()

    pairs = await find_deterministic_org_matches(test_user.id, db)
    pair_ids = {tuple(sorted([p[0].id, p[1].id])) for p in pairs}
    assert tuple(sorted([a.id, b.id])) in pair_ids
    # Stripe shouldn't be paired with anything
    assert all(c.id not in p[:2] for p in pairs)


@pytest.mark.asyncio
async def test_deterministic_same_linkedin(db: AsyncSession, test_user: User):
    a = Organization(
        user_id=test_user.id, name="Foo",
        linkedin_url="https://linkedin.com/company/anthropic",
    )
    b = Organization(
        user_id=test_user.id, name="Bar",
        linkedin_url="https://www.linkedin.com/company/anthropic/",
    )
    db.add_all([a, b])
    await db.flush()

    pairs = await find_deterministic_org_matches(test_user.id, db)
    assert len(pairs) == 1
    assert pairs[0][2] == "deterministic_linkedin"


@pytest.mark.asyncio
async def test_deterministic_generic_domain_ignored(db: AsyncSession, test_user: User):
    """Two orgs with gmail.com as their 'domain' should NOT auto-merge."""
    a = Organization(user_id=test_user.id, name="Acme", domain="gmail.com")
    b = Organization(user_id=test_user.id, name="Widget", domain="gmail.com")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_deterministic_org_matches(test_user.id, db)
    assert len(pairs) == 0


@pytest.mark.asyncio
async def test_deterministic_cross_user_isolation(
    db: AsyncSession, test_user: User, user_factory
):
    other = await user_factory()
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=other.id, name="Anthropic", domain="anthropic.com")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_deterministic_org_matches(test_user.id, db)
    assert len(pairs) == 0  # cross-user pairs never match
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_resolution.py::test_deterministic_same_domain -v`
Expected: ImportError on `find_deterministic_org_matches`.

- [ ] **Step 3: Implement `find_deterministic_org_matches`**

Add the necessary imports to `backend/app/services/org_identity_resolution.py` at the top:

```python
import uuid

from sqlalchemy import func, select

from app.services.org_identity_scoring import (
    GENERIC_DOMAINS,
    _normalize_website,
    _same_linkedin,
    _same_non_generic_domain,
)
```

Then append:

```python
async def find_deterministic_org_matches(
    user_id: uuid.UUID, db: AsyncSession,
) -> list[tuple[Organization, Organization, str]]:
    """Find org pairs that should auto-merge with no review.

    Returns a list of (org_a, org_b, match_method) tuples. match_method is one of:
      - "deterministic_domain"
      - "deterministic_linkedin"
      - "deterministic_name_website"

    Each pair is returned at most once. Convention: org_a.id < org_b.id.
    """
    result = await db.execute(
        select(Organization).where(Organization.user_id == user_id)
    )
    orgs: list[Organization] = list(result.scalars().all())

    pairs: list[tuple[Organization, Organization, str]] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for i, a in enumerate(orgs):
        for b in orgs[i + 1:]:
            # Order canonically so each pair appears once
            if a.id < b.id:
                first, second = a, b
            else:
                first, second = b, a
            key = (first.id, second.id)
            if key in seen:
                continue

            method: str | None = None
            if _same_non_generic_domain(a.domain, b.domain):
                method = "deterministic_domain"
            elif _same_linkedin(a.linkedin_url, b.linkedin_url):
                method = "deterministic_linkedin"
            else:
                na = (a.name or "").strip().lower()
                nb = (b.name or "").strip().lower()
                if na and na == nb:
                    nwa = _normalize_website(a.website)
                    nwb = _normalize_website(b.website)
                    if nwa and nwa == nwb:
                        method = "deterministic_name_website"

            if method is not None:
                seen.add(key)
                pairs.append((first, second, method))

    return pairs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_resolution.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/org_identity_resolution.py backend/tests/test_org_identity_resolution.py
git commit -m "feat(orgs): find_deterministic_org_matches"
```

---

### Task 8: `find_probabilistic_org_matches`

**Files:**
- Modify: `backend/app/services/org_identity_resolution.py`
- Modify: `backend/tests/test_org_identity_resolution.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_org_identity_resolution.py`:

```python
from app.services.org_identity_resolution import find_probabilistic_org_matches


@pytest.mark.asyncio
async def test_probabilistic_finds_name_variation(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic, Inc.", domain="anthropic.com")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_probabilistic_org_matches(test_user.id, db, exclude_ids=set())
    assert len(pairs) == 1
    assert pairs[0][2] >= 0.40


@pytest.mark.asyncio
async def test_probabilistic_skips_excluded(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic, Inc.", domain="anthropic.com")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_probabilistic_org_matches(
        test_user.id, db, exclude_ids={a.id}
    )
    assert pairs == []


@pytest.mark.asyncio
async def test_probabilistic_filters_below_threshold(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic")
    b = Organization(user_id=test_user.id, name="Stripe")
    db.add_all([a, b])
    await db.flush()

    pairs = await find_probabilistic_org_matches(test_user.id, db, exclude_ids=set())
    assert pairs == []  # below 0.40 threshold
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_resolution.py::test_probabilistic_finds_name_variation -v`
Expected: ImportError on `find_probabilistic_org_matches`.

- [ ] **Step 3: Implement `find_probabilistic_org_matches`**

Add to imports in `backend/app/services/org_identity_resolution.py`:

```python
from app.services.org_identity_scoring import (
    _shares_anchor,
    compute_org_adaptive_score,
    # keep the existing imports
)
```

Append:

```python
# Below this, surface to review queue. Above 0.95, auto-merge (treated as Tier 1).
PROBABILISTIC_REVIEW_THRESHOLD = 0.40
PROBABILISTIC_AUTOMERGE_THRESHOLD = 0.95


async def find_probabilistic_org_matches(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    exclude_ids: set[uuid.UUID],
) -> list[tuple[Organization, Organization, float]]:
    """Score org pairs and return those above the review threshold.

    Skips pairs where either org is in *exclude_ids* (used to skip orgs that
    were already auto-merged in the deterministic pass).

    Returns (org_a, org_b, score) with org_a.id < org_b.id.
    Score >= PROBABILISTIC_AUTOMERGE_THRESHOLD → caller should auto-merge.
    Score in [PROBABILISTIC_REVIEW_THRESHOLD, PROBABILISTIC_AUTOMERGE_THRESHOLD) → queue.
    """
    result = await db.execute(
        select(Organization).where(Organization.user_id == user_id)
    )
    orgs: list[Organization] = [
        o for o in result.scalars().all() if o.id not in exclude_ids
    ]

    pairs: list[tuple[Organization, Organization, float]] = []
    for i, a in enumerate(orgs):
        for b in orgs[i + 1:]:
            if not _shares_anchor(a, b):
                continue
            score = compute_org_adaptive_score(a, b)
            if score < PROBABILISTIC_REVIEW_THRESHOLD:
                continue
            if a.id < b.id:
                pairs.append((a, b, score))
            else:
                pairs.append((b, a, score))

    return pairs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_resolution.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/org_identity_resolution.py backend/tests/test_org_identity_resolution.py
git commit -m "feat(orgs): find_probabilistic_org_matches with anchor pre-filter"
```

---

### Task 9: `scan_org_duplicates` orchestrator

**Files:**
- Modify: `backend/app/services/org_identity_resolution.py`
- Modify: `backend/tests/test_org_identity_resolution.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_org_identity_resolution.py`:

```python
from app.models.org_identity_match import OrgIdentityMatch
from app.services.org_identity_resolution import scan_org_duplicates


@pytest.mark.asyncio
async def test_scan_auto_merges_deterministic(db: AsyncSession, test_user: User):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic Inc", domain="anthropic.com")
    db.add_all([a, b])
    await db.flush()

    summary = await scan_org_duplicates(test_user.id, db)
    await db.flush()

    assert summary["auto_merged"] == 1
    # Only one org remains (the deterministic merge ran)
    result = await db.execute(
        select(Organization).where(Organization.user_id == test_user.id)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_scan_queues_probabilistic_for_review(db: AsyncSession, test_user: User):
    # Same first-3 chars but no domain/linkedin/website match — probabilistic territory
    a = Organization(user_id=test_user.id, name="Stripe")
    b = Organization(user_id=test_user.id, name="Stripe Payments")
    db.add_all([a, b])
    await db.flush()

    summary = await scan_org_duplicates(test_user.id, db)
    await db.flush()

    assert summary["pending_review"] >= 1
    result = await db.execute(
        select(OrgIdentityMatch).where(
            OrgIdentityMatch.user_id == test_user.id,
            OrgIdentityMatch.status == "pending_review",
        )
    )
    matches = result.scalars().all()
    assert len(matches) == 1
    assert matches[0].match_method == "probabilistic"


@pytest.mark.asyncio
async def test_scan_idempotent(db: AsyncSession, test_user: User):
    """Running scan twice doesn't create duplicate match rows."""
    a = Organization(user_id=test_user.id, name="Stripe")
    b = Organization(user_id=test_user.id, name="Stripe Payments")
    db.add_all([a, b])
    await db.flush()

    await scan_org_duplicates(test_user.id, db)
    await db.flush()
    await scan_org_duplicates(test_user.id, db)
    await db.flush()

    result = await db.execute(
        select(OrgIdentityMatch).where(OrgIdentityMatch.user_id == test_user.id)
    )
    assert len(result.scalars().all()) == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_resolution.py::test_scan_auto_merges_deterministic -v`
Expected: ImportError on `scan_org_duplicates`.

- [ ] **Step 3: Implement `scan_org_duplicates`**

Add import at top of `backend/app/services/org_identity_resolution.py`:

```python
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.models.org_identity_match import OrgIdentityMatch
```

Append:

```python
async def _count_contacts(org_id: uuid.UUID, db: AsyncSession) -> int:
    """Return the number of contacts assigned to an org."""
    result = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.organization_id == org_id)
    )
    return result.scalar() or 0


async def _pick_target(
    a: Organization, b: Organization, db: AsyncSession
) -> tuple[Organization, Organization]:
    """Return (target, source) — target is the org with more contacts.

    Ties broken by older created_at (the older org is more "canonical").
    """
    count_a = await _count_contacts(a.id, db)
    count_b = await _count_contacts(b.id, db)
    if count_a > count_b:
        return a, b
    if count_b > count_a:
        return b, a
    # Tie — pick older
    if (a.created_at or b.created_at) and a.created_at <= b.created_at:
        return a, b
    return b, a


async def scan_org_duplicates(
    user_id: uuid.UUID, db: AsyncSession,
) -> dict:
    """Full scan: auto-merge deterministic pairs, queue probabilistic ones.

    Returns {"matches_found", "auto_merged", "pending_review"}.
    """
    auto_merged = 0
    merged_org_ids: set[uuid.UUID] = set()

    # Tier 1: deterministic auto-merge
    deterministic = await find_deterministic_org_matches(user_id, db)
    for a, b, method in deterministic:
        if a.id in merged_org_ids or b.id in merged_org_ids:
            continue
        target, source = await _pick_target(a, b, db)
        await merge_org_pair(target, source, db)
        merged_org_ids.add(source.id)
        auto_merged += 1
    if deterministic:
        await db.flush()

    # Tier 2: probabilistic — score remaining orgs
    probabilistic = await find_probabilistic_org_matches(
        user_id, db, exclude_ids=merged_org_ids,
    )

    pending_review = 0
    for a, b, score in probabilistic:
        if score >= PROBABILISTIC_AUTOMERGE_THRESHOLD:
            target, source = await _pick_target(a, b, db)
            await merge_org_pair(target, source, db)
            merged_org_ids.add(source.id)
            auto_merged += 1
            continue

        # Queue for review — try insert; IntegrityError = already in queue from a
        # previous scan (unique index on user, LEAST(a,b), GREATEST(a,b)).
        match = OrgIdentityMatch(
            user_id=user_id,
            org_a_id=a.id,
            org_b_id=b.id,
            match_score=score,
            match_method="probabilistic",
            status="pending_review",
        )
        db.add(match)
        try:
            await db.flush()
            pending_review += 1
        except IntegrityError:
            await db.rollback()
            # Re-load the user's transaction state and continue
            continue

    return {
        "matches_found": auto_merged + pending_review,
        "auto_merged": auto_merged,
        "pending_review": pending_review,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_resolution.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/org_identity_resolution.py backend/tests/test_org_identity_resolution.py
git commit -m "feat(orgs): scan_org_duplicates orchestrator"
```

---

## Phase 2 — API + Frontend refactor

### Task 10: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/org_identity_match.py`

- [ ] **Step 1: Create the schemas**

Create `backend/app/schemas/org_identity_match.py`:

```python
"""Pydantic schemas for the org dedup endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrgSummary(BaseModel):
    """Compact org representation for the duplicate-pair card."""
    id: str
    name: str
    domain: str | None = None
    logo_url: str | None = None
    linkedin_url: str | None = None
    website: str | None = None
    twitter_handle: str | None = None
    contact_count: int = 0


class OrgIdentityMatchData(BaseModel):
    id: str
    match_score: float
    match_method: str
    status: str
    org_a: OrgSummary
    org_b: OrgSummary
    created_at: datetime


class ScanOrgsResult(BaseModel):
    matches_found: int
    auto_merged: int
    pending_review: int


class MergeOrgMatchRequest(BaseModel):
    target_id: str  # must equal org_a_id or org_b_id on the match


class MergeOrgMatchResult(BaseModel):
    merged: bool
    target_id: str
    contacts_moved: int


class DismissOrgMatchResult(BaseModel):
    dismissed: bool
```

- [ ] **Step 2: Verify imports cleanly**

Run: `cd backend && PYTHONPATH=. python3 -c "from app.schemas.org_identity_match import OrgIdentityMatchData, ScanOrgsResult; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/org_identity_match.py
git commit -m "feat(orgs): pydantic schemas for dedup endpoints"
```

---

### Task 11: `/scan-duplicates` endpoint

**Files:**
- Create: `backend/app/api/organizations_duplicates.py`
- Create: `backend/tests/test_api_org_duplicates.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_api_org_duplicates.py`:

```python
"""Tests for organization duplicate endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User


@pytest.mark.asyncio
async def test_scan_duplicates_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/organizations/scan-duplicates", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_scan_duplicates_returns_summary(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    a = Organization(user_id=test_user.id, name="Anthropic", domain="anthropic.com")
    b = Organization(user_id=test_user.id, name="Anthropic Inc", domain="anthropic.com")
    c = Organization(user_id=test_user.id, name="Stripe")
    d = Organization(user_id=test_user.id, name="Stripe Payments")
    db.add_all([a, b, c, d])
    await db.flush()

    resp = await client.post("/api/v1/organizations/scan-duplicates",
                              json={}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["matches_found"] >= 2
    assert data["auto_merged"] == 1  # Anthropic pair
    assert data["pending_review"] >= 1  # Stripe pair


@pytest.mark.asyncio
async def test_scan_duplicates_empty_user(
    client: AsyncClient, auth_headers: dict
):
    """User with no orgs gets zero-result summary."""
    resp = await client.post("/api/v1/organizations/scan-duplicates",
                              json={}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"matches_found": 0, "auto_merged": 0, "pending_review": 0}
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_org_duplicates.py::test_scan_duplicates_returns_summary -v`
Expected: 404 (route not registered).

- [ ] **Step 3: Create the endpoint module**

Create `backend/app/api/organizations_duplicates.py`:

```python
"""Endpoints for organization deduplication."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.org_identity_match import OrgIdentityMatch
from app.models.organization import Organization
from app.models.user import User
from app.schemas.org_identity_match import (
    DismissOrgMatchResult,
    MergeOrgMatchRequest,
    MergeOrgMatchResult,
    OrgIdentityMatchData,
    OrgSummary,
    ScanOrgsResult,
)
from app.schemas.responses import Envelope
from app.services.org_identity_resolution import merge_org_pair, scan_org_duplicates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


@router.post("/scan-duplicates", response_model=Envelope[ScanOrgsResult])
async def scan_duplicates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[ScanOrgsResult]:
    """Run a fresh duplicate scan over the current user's orgs."""
    summary = await scan_org_duplicates(current_user.id, db)
    return {"data": summary, "error": None}
```

- [ ] **Step 4: Register the router in `main.py`**

Open `backend/app/main.py`. Near the other `from app.api.<x> import router as <x>_router` imports, add:

```python
from app.api.organizations_duplicates import router as org_duplicates_router
```

Near the other `app.include_router(...)` calls, add (immediately after `app.include_router(organizations_router)`):

```python
app.include_router(org_duplicates_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_org_duplicates.py -v`
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/organizations_duplicates.py backend/tests/test_api_org_duplicates.py backend/app/main.py
git commit -m "feat(orgs): POST /organizations/scan-duplicates endpoint"
```

---

### Task 12: `GET /duplicates` endpoint

**Files:**
- Modify: `backend/app/api/organizations_duplicates.py`
- Modify: `backend/tests/test_api_org_duplicates.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_api_org_duplicates.py`:

```python
from app.models.org_identity_match import OrgIdentityMatch


@pytest.mark.asyncio
async def test_list_duplicates_returns_pending(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    a = Organization(user_id=test_user.id, name="Stripe")
    b = Organization(user_id=test_user.id, name="Stripe Payments")
    db.add_all([a, b])
    await db.flush()

    match = OrgIdentityMatch(
        user_id=test_user.id,
        org_a_id=a.id, org_b_id=b.id,
        match_score=0.65,
        match_method="probabilistic",
        status="pending_review",
    )
    db.add(match)
    await db.flush()

    resp = await client.get("/api/v1/organizations/duplicates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["match_score"] == 0.65
    assert data[0]["status"] == "pending_review"
    assert data[0]["org_a"]["name"] in ("Stripe", "Stripe Payments")
    assert data[0]["org_b"]["name"] in ("Stripe", "Stripe Payments")


@pytest.mark.asyncio
async def test_list_duplicates_excludes_resolved(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    a = Organization(user_id=test_user.id, name="Foo")
    b = Organization(user_id=test_user.id, name="Foo Inc")
    db.add_all([a, b])
    await db.flush()

    db.add(OrgIdentityMatch(
        user_id=test_user.id, org_a_id=a.id, org_b_id=b.id,
        match_score=0.65, match_method="probabilistic", status="dismissed",
    ))
    await db.flush()

    resp = await client.get("/api/v1/organizations/duplicates", headers=auth_headers)
    assert resp.json()["data"] == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_org_duplicates.py::test_list_duplicates_returns_pending -v`
Expected: 404 or 405 (route doesn't exist).

- [ ] **Step 3: Implement the endpoint**

Append to `backend/app/api/organizations_duplicates.py`:

```python
async def _org_summary(org: Organization, db: AsyncSession) -> OrgSummary:
    count_result = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.organization_id == org.id)
    )
    contact_count = count_result.scalar() or 0
    return OrgSummary(
        id=str(org.id),
        name=org.name,
        domain=org.domain,
        logo_url=org.logo_url,
        linkedin_url=org.linkedin_url,
        website=org.website,
        twitter_handle=org.twitter_handle,
        contact_count=contact_count,
    )


@router.get("/duplicates", response_model=Envelope[list[OrgIdentityMatchData]])
async def list_duplicates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[list[OrgIdentityMatchData]]:
    """Return all pending_review match pairs for the current user."""
    result = await db.execute(
        select(OrgIdentityMatch)
        .where(
            OrgIdentityMatch.user_id == current_user.id,
            OrgIdentityMatch.status == "pending_review",
        )
        .order_by(OrgIdentityMatch.match_score.desc())
    )
    matches = list(result.scalars().all())

    if not matches:
        return {"data": [], "error": None}

    # Batch-load orgs to avoid N+1
    org_ids = {m.org_a_id for m in matches} | {m.org_b_id for m in matches}
    orgs_result = await db.execute(
        select(Organization).where(Organization.id.in_(org_ids))
    )
    org_by_id = {o.id: o for o in orgs_result.scalars().all()}

    data: list[OrgIdentityMatchData] = []
    for m in matches:
        org_a = org_by_id.get(m.org_a_id)
        org_b = org_by_id.get(m.org_b_id)
        if org_a is None or org_b is None:
            continue  # one side deleted — match row will be cleaned up by cascade
        data.append(OrgIdentityMatchData(
            id=str(m.id),
            match_score=m.match_score,
            match_method=m.match_method,
            status=m.status,
            org_a=await _org_summary(org_a, db),
            org_b=await _org_summary(org_b, db),
            created_at=m.created_at,
        ))

    return {"data": data, "error": None}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_org_duplicates.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/organizations_duplicates.py backend/tests/test_api_org_duplicates.py
git commit -m "feat(orgs): GET /organizations/duplicates endpoint"
```

---

### Task 13: `POST /duplicates/{id}/merge` endpoint

**Files:**
- Modify: `backend/app/api/organizations_duplicates.py`
- Modify: `backend/tests/test_api_org_duplicates.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_api_org_duplicates.py` (also add `from app.models.contact import Contact` to the existing imports at the top of the file):

```python
@pytest.mark.asyncio
async def test_merge_match_moves_contacts(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    target = Organization(user_id=test_user.id, name="Anthropic")
    source = Organization(user_id=test_user.id, name="Anthropic, Inc.")
    db.add_all([target, source])
    await db.flush()
    contact = Contact(
        user_id=test_user.id, full_name="Alice",
        emails=["a@anthropic.com"], company="Anthropic, Inc.",
        organization_id=source.id,
    )
    db.add(contact)
    await db.flush()
    match = OrgIdentityMatch(
        user_id=test_user.id, org_a_id=target.id, org_b_id=source.id,
        match_score=0.72, match_method="probabilistic", status="pending_review",
    )
    db.add(match)
    await db.flush()
    match_id = match.id

    resp = await client.post(
        f"/api/v1/organizations/duplicates/{match_id}/merge",
        json={"target_id": str(target.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["merged"] is True
    assert body["target_id"] == str(target.id)
    assert body["contacts_moved"] == 1

    # Match marked resolved
    res = await db.execute(select(OrgIdentityMatch).where(OrgIdentityMatch.id == match_id))
    match_after = res.scalar_one()
    assert match_after.status == "merged"
    assert match_after.resolved_at is not None


@pytest.mark.asyncio
async def test_merge_match_target_must_be_in_pair(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    a = Organization(user_id=test_user.id, name="A")
    b = Organization(user_id=test_user.id, name="B")
    other = Organization(user_id=test_user.id, name="C")  # not in the pair
    db.add_all([a, b, other])
    await db.flush()
    match = OrgIdentityMatch(
        user_id=test_user.id, org_a_id=a.id, org_b_id=b.id,
        match_score=0.65, match_method="probabilistic", status="pending_review",
    )
    db.add(match)
    await db.flush()

    resp = await client.post(
        f"/api/v1/organizations/duplicates/{match.id}/merge",
        json={"target_id": str(other.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_match_cross_user_404(
    client: AsyncClient, auth_headers: dict, db: AsyncSession,
    test_user: User, user_factory,
):
    other_user = await user_factory()
    a = Organization(user_id=other_user.id, name="A")
    b = Organization(user_id=other_user.id, name="B")
    db.add_all([a, b])
    await db.flush()
    match = OrgIdentityMatch(
        user_id=other_user.id, org_a_id=a.id, org_b_id=b.id,
        match_score=0.65, match_method="probabilistic", status="pending_review",
    )
    db.add(match)
    await db.flush()

    resp = await client.post(
        f"/api/v1/organizations/duplicates/{match.id}/merge",
        json={"target_id": str(a.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_org_duplicates.py::test_merge_match_moves_contacts -v`
Expected: 404 (route doesn't exist).

- [ ] **Step 3: Implement the endpoint**

Append to `backend/app/api/organizations_duplicates.py`:

```python
@router.post(
    "/duplicates/{match_id}/merge",
    response_model=Envelope[MergeOrgMatchResult],
)
async def merge_match(
    match_id: uuid.UUID,
    payload: MergeOrgMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[MergeOrgMatchResult]:
    """User confirms a match: merge source -> target."""
    result = await db.execute(
        select(OrgIdentityMatch).where(
            OrgIdentityMatch.id == match_id,
            OrgIdentityMatch.user_id == current_user.id,
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    target_id = uuid.UUID(payload.target_id)
    if target_id not in (match.org_a_id, match.org_b_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_id must be one of the orgs in this match",
        )

    source_id = match.org_b_id if target_id == match.org_a_id else match.org_a_id

    # Load both orgs
    target_res = await db.execute(
        select(Organization).where(
            Organization.id == target_id,
            Organization.user_id == current_user.id,
        )
    )
    target = target_res.scalar_one_or_none()
    source_res = await db.execute(
        select(Organization).where(
            Organization.id == source_id,
            Organization.user_id == current_user.id,
        )
    )
    source = source_res.scalar_one_or_none()
    if target is None or source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    moved = await merge_org_pair(target, source, db)
    match.status = "merged"
    match.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "data": MergeOrgMatchResult(
            merged=True, target_id=str(target_id), contacts_moved=moved,
        ),
        "error": None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_org_duplicates.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/organizations_duplicates.py backend/tests/test_api_org_duplicates.py
git commit -m "feat(orgs): POST /organizations/duplicates/{id}/merge"
```

---

### Task 14: `POST /duplicates/{id}/dismiss` endpoint

**Files:**
- Modify: `backend/app/api/organizations_duplicates.py`
- Modify: `backend/tests/test_api_org_duplicates.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_api_org_duplicates.py`:

```python
@pytest.mark.asyncio
async def test_dismiss_match(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User
):
    a = Organization(user_id=test_user.id, name="A")
    b = Organization(user_id=test_user.id, name="B")
    db.add_all([a, b])
    await db.flush()
    match = OrgIdentityMatch(
        user_id=test_user.id, org_a_id=a.id, org_b_id=b.id,
        match_score=0.50, match_method="probabilistic", status="pending_review",
    )
    db.add(match)
    await db.flush()
    match_id = match.id

    resp = await client.post(
        f"/api/v1/organizations/duplicates/{match_id}/dismiss",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == {"dismissed": True}

    res = await db.execute(select(OrgIdentityMatch).where(OrgIdentityMatch.id == match_id))
    match_after = res.scalar_one()
    assert match_after.status == "dismissed"
    assert match_after.resolved_at is not None
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_org_duplicates.py::test_dismiss_match -v`
Expected: 404 (route doesn't exist).

- [ ] **Step 3: Implement the endpoint**

Append to `backend/app/api/organizations_duplicates.py`:

```python
@router.post(
    "/duplicates/{match_id}/dismiss",
    response_model=Envelope[DismissOrgMatchResult],
)
async def dismiss_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Envelope[DismissOrgMatchResult]:
    """User confirms 'not the same' — pair will not resurface."""
    result = await db.execute(
        select(OrgIdentityMatch).where(
            OrgIdentityMatch.id == match_id,
            OrgIdentityMatch.user_id == current_user.id,
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    match.status = "dismissed"
    match.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return {"data": DismissOrgMatchResult(dismissed=True), "error": None}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_org_duplicates.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/organizations_duplicates.py backend/tests/test_api_org_duplicates.py
git commit -m "feat(orgs): POST /organizations/duplicates/{id}/dismiss"
```

---

### Task 15: Regen OpenAPI + frontend API types + docs

**Files:**
- Modify: `backend/openapi.json`
- Modify: `frontend/src/lib/api-types.d.ts`
- Modify: `docs/docs/api-reference.md`

- [ ] **Step 1: Regenerate OpenAPI**

Run (from project root):

```bash
cd backend && PYTHONPATH=. python3 -c "
import json
from app.main import fastapi_app
from fastapi.openapi.utils import get_openapi
schema = get_openapi(title=fastapi_app.title, version=fastapi_app.version, routes=fastapi_app.routes)
with open('openapi.json', 'w') as f:
    json.dump(schema, f, indent=2)
print('regenerated')
"
```

Expected: prints `regenerated`.

- [ ] **Step 2: Regen frontend types**

Run: `cd frontend && npm run generate:api`
Expected: completes without error.

- [ ] **Step 3: Verify the four new routes appear**

Run: `grep -c '"/api/v1/organizations/scan-duplicates"\|"/api/v1/organizations/duplicates"' frontend/src/lib/api-types.d.ts`
Expected: at least 4 (one for scan-duplicates, one for the list, two for the path-parameterized endpoints).

- [ ] **Step 4: Add the 4 routes to the API reference**

Open `docs/docs/api-reference.md` and find the Organizations section. Append four rows to its table:

```markdown
| POST | `/api/v1/organizations/scan-duplicates` | Run a dedup scan; auto-merges deterministic pairs, queues fuzzy ones |
| GET | `/api/v1/organizations/duplicates` | List pending_review duplicate pairs |
| POST | `/api/v1/organizations/duplicates/{match_id}/merge` | Merge a pending pair (`target_id` body) |
| POST | `/api/v1/organizations/duplicates/{match_id}/dismiss` | Mark a pending pair as 'not the same' |
```

- [ ] **Step 5: Run the API-doc check**

Run: `cd backend && PYTHONPATH=. pytest tests/test_api_doc.py -v`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/openapi.json frontend/src/lib/api-types.d.ts docs/docs/api-reference.md
git commit -m "chore: regenerate OpenAPI + types for org dedup endpoints"
```

---

### Task 16: Extract `MatchCardShell` from `MatchCard`

**Files:**
- Create: `frontend/src/app/identity/_components/match-card-shell.tsx`
- Modify: `frontend/src/app/identity/_components/match-card.tsx`

- [ ] **Step 1: Create `match-card-shell.tsx`**

Create `frontend/src/app/identity/_components/match-card-shell.tsx`:

```tsx
"use client";

import { useState, type ReactNode } from "react";
import {
  AlertCircle,
  BarChart2,
  Check,
  CheckCircle,
  GitMerge,
  HelpCircle,
  X,
  Zap,
} from "lucide-react";

import { cn } from "@/lib/utils";

type MatchTypeStyle = {
  label: string;
  icon: ReactNode;
  pillColors: string;
  barColor: string;
};

function matchTypeStyle(method: string, score: number): MatchTypeStyle {
  if (method.startsWith("deterministic") || score >= 0.85) {
    return {
      label: "Exact match",
      icon: <CheckCircle className="w-3.5 h-3.5" />,
      pillColors:
        "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
      barColor: "bg-emerald-500",
    };
  }
  if (method === "probabilistic" && score < 0.65) {
    return {
      label: "Probabilistic",
      icon: <HelpCircle className="w-3.5 h-3.5" />,
      pillColors:
        "bg-sky-50 dark:bg-sky-950 text-sky-700 dark:text-sky-400 border-sky-200 dark:border-sky-800",
      barColor: "bg-sky-400",
    };
  }
  return {
    label: "Possible match",
    icon: <AlertCircle className="w-3.5 h-3.5" />,
    pillColors:
      "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800",
    barColor: "bg-amber-400",
  };
}

export type BreakdownRow = { label: string; weight: number };

export function MatchCardShell({
  matchScore,
  matchMethod,
  breakdownRows,
  leftPanel,
  rightPanel,
  mergeButtonLabel,
  onMerge,
  onReject,
  merging,
  rejecting,
}: {
  matchScore: number;
  matchMethod: string;
  breakdownRows: BreakdownRow[];
  leftPanel: ReactNode;
  rightPanel: ReactNode;
  mergeButtonLabel: string;
  onMerge: () => void;
  onReject: () => void;
  merging: boolean;
  rejecting: boolean;
}) {
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const score = matchScore ?? 0;
  const pct = Math.round(score * 100);
  const style = matchTypeStyle(matchMethod, score);
  const isAutoMergeReady = score >= 0.95;
  const isLowConfidence = score < 0.65;

  return (
    <div className="card-hover bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 overflow-hidden">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border", style.pillColors)}>
              {style.icon}
              {style.label}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono font-medium text-stone-700 dark:text-stone-300">{pct}% match</span>
              <div className="w-24 h-1.5 bg-stone-100 dark:bg-stone-800 rounded-full overflow-hidden">
                <div className={cn("h-full rounded-full", style.barColor)} style={{ width: `${pct}%` }} />
              </div>
            </div>
            {isAutoMergeReady && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-teal-50 dark:bg-teal-950 text-teal-700 dark:text-teal-400 border border-teal-200 dark:border-teal-800">
                <Zap className="w-3 h-3" />
                Auto-merge ready
              </span>
            )}
          </div>
          <button
            onClick={() => setBreakdownOpen((v) => !v)}
            className="text-xs text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 transition-colors flex items-center gap-1"
          >
            <BarChart2 className="w-3.5 h-3.5" />
            Match detail
          </button>
        </div>

        {breakdownOpen && (
          <div className="mb-4">
            <div className="bg-stone-50 dark:bg-stone-800 rounded-lg p-4 border border-stone-100 dark:border-stone-700">
              <p className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-3 uppercase tracking-wide">Match breakdown</p>
              <div className="space-y-2.5">
                {breakdownRows.map((item) => {
                  const contribution = Math.round(item.weight * score);
                  const hasMatch = contribution > 0;
                  return (
                    <div key={item.label} className="flex items-center gap-3">
                      {hasMatch ? (
                        <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                      ) : (
                        <X className="w-4 h-4 text-red-400 shrink-0" />
                      )}
                      <span className="text-xs text-stone-600 dark:text-stone-300 w-32 shrink-0">{item.label}</span>
                      <div className="flex-1 h-1.5 bg-stone-200 dark:bg-stone-700 rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full", hasMatch ? style.barColor : "bg-stone-300 dark:bg-stone-600")}
                          style={{ width: `${contribution}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-stone-400 dark:text-stone-500 w-8 text-right">{contribution}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-[1fr_auto_1fr] gap-4 items-stretch">
          {leftPanel}
          <div className="flex items-center justify-center">
            <div className="flex flex-col items-center gap-1">
              <div className="w-px h-8 bg-stone-200 dark:bg-stone-700" />
              <span className="text-xs font-mono font-medium text-stone-400 dark:text-stone-500 bg-stone-100 dark:bg-stone-800 rounded px-1.5 py-0.5">vs</span>
              <div className="w-px h-8 bg-stone-200 dark:bg-stone-700" />
            </div>
          </div>
          {rightPanel}
        </div>
      </div>

      <div className="px-5 py-3 border-t border-stone-100 dark:border-stone-800 bg-stone-50 dark:bg-stone-800 flex items-center justify-between">
        {isLowConfidence && (
          <p className="text-xs text-stone-400 dark:text-stone-500">Low confidence — manual review recommended</p>
        )}
        <div className={cn("flex items-center gap-2", !isLowConfidence && "ml-auto")}>
          <button
            onClick={onReject}
            disabled={rejecting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-stone-600 dark:text-stone-300 border border-stone-200 dark:border-stone-700 hover:bg-stone-100 dark:hover:bg-stone-800 disabled:opacity-50 transition-colors"
          >
            <X className="w-3.5 h-3.5" /> Not the same
          </button>
          <button
            onClick={onMerge}
            disabled={merging}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            <GitMerge className="w-3.5 h-3.5" /> {mergeButtonLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Slim down `match-card.tsx` to wrap the shell**

Replace the entire contents of `frontend/src/app/identity/_components/match-card.tsx` with:

```tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Mail,
  Twitter,
  MessageCircle,
  Building2,
  Phone,
  Briefcase,
  Tag,
  FileText,
  Globe,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

import type {
  IdentityMatch,
  IdentityMatchContact,
} from "@/hooks/use-identity";
import { ContactAvatar } from "@/components/contact-avatar";
import { MatchCardShell, type BreakdownRow } from "./match-card-shell";

const CONTACT_BREAKDOWN: BreakdownRow[] = [
  { label: "Email domain", weight: 40 },
  { label: "Name similarity", weight: 20 },
  { label: "Same company", weight: 20 },
  { label: "Username", weight: 10 },
  { label: "Mutual signals", weight: 10 },
];

function ContactPanel({ contact }: { contact: IdentityMatchContact }) {
  const [expanded, setExpanded] = useState(false);
  const displayName = contact.full_name ?? "Unnamed";
  const primaryEmail = contact.emails[0] ?? null;
  const extraEmails = contact.emails.slice(1);

  const hasExtra =
    extraEmails.length > 0 ||
    contact.phones.length > 0 ||
    contact.title ||
    contact.linkedin_url ||
    contact.tags.length > 0 ||
    contact.notes ||
    contact.source;

  return (
    <div className="bg-stone-50 dark:bg-stone-800 rounded-lg p-4 border border-stone-100 dark:border-stone-700">
      <div className="flex items-center gap-3 mb-3">
        <ContactAvatar avatarUrl={null} name={displayName} size="sm" />
        <div className="min-w-0 flex-1">
          <Link
            href={`/contacts/${contact.id}`}
            className="text-sm font-semibold text-stone-900 dark:text-stone-100 hover:text-teal-700 dark:hover:text-teal-400 transition-colors truncate block"
            onClick={(e) => e.stopPropagation()}
          >
            {displayName}
          </Link>
          {contact.source && (
            <p className="text-xs text-stone-400 dark:text-stone-500">
              Added via {contact.source}
            </p>
          )}
        </div>
      </div>

      <div className="space-y-1.5 text-xs text-stone-600 dark:text-stone-300">
        {contact.company && (
          <div className="flex items-center gap-2">
            <Building2 className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span>{contact.company}</span>
          </div>
        )}
        {primaryEmail && (
          <div className="flex items-center gap-2">
            <Mail className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono truncate">{primaryEmail}</span>
          </div>
        )}
        {contact.twitter_handle ? (
          <div className="flex items-center gap-2">
            <Twitter className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono">@{contact.twitter_handle}</span>
          </div>
        ) : null}
        {contact.telegram_username ? (
          <div className="flex items-center gap-2">
            <MessageCircle className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono">@{contact.telegram_username}</span>
          </div>
        ) : null}
      </div>

      {hasExtra && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-3 text-xs text-teal-600 dark:text-teal-400 hover:text-teal-800 dark:hover:text-teal-300 transition-colors flex items-center gap-1"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? "Less" : "More details"}
          </button>

          {expanded && (
            <div className="mt-2 pt-2 border-t border-stone-200 dark:border-stone-700 space-y-1.5 text-xs text-stone-600 dark:text-stone-300">
              {contact.title && (
                <div className="flex items-center gap-2">
                  <Briefcase className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
                  <span className="truncate">{contact.title}</span>
                </div>
              )}
              {extraEmails.map((email) => (
                <div key={email} className="flex items-center gap-2 truncate">
                  <Mail className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
                  <span className="font-mono truncate">{email}</span>
                </div>
              ))}
              {contact.phones.map((phone) => (
                <div key={phone} className="flex items-center gap-2">
                  <Phone className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
                  <span className="font-mono">{phone}</span>
                </div>
              ))}
              {contact.linkedin_url && (
                <div className="flex items-center gap-2 truncate">
                  <Globe className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
                  <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-teal-600 dark:text-teal-400 hover:underline font-mono truncate">
                    LinkedIn
                  </a>
                </div>
              )}
              {contact.tags.length > 0 && (
                <div className="flex items-start gap-2">
                  <Tag className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0 mt-0.5" />
                  <div className="flex flex-wrap gap-1">
                    {contact.tags.map((tag) => (
                      <span key={tag} className="px-1.5 py-0.5 rounded text-xs bg-stone-200 dark:bg-stone-700 text-stone-700 dark:text-stone-300">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {contact.notes && (
                <div className="flex items-start gap-2">
                  <FileText className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0 mt-0.5" />
                  <span className="text-xs text-stone-500 dark:text-stone-400 line-clamp-3">{contact.notes}</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function MatchCard({
  match,
  onMerge,
  onReject,
  merging,
  rejecting,
}: {
  match: IdentityMatch;
  onMerge: () => void;
  onReject: () => void;
  merging: boolean;
  rejecting: boolean;
}) {
  return (
    <MatchCardShell
      matchScore={match.match_score ?? 0}
      matchMethod={match.match_method}
      breakdownRows={CONTACT_BREAKDOWN}
      leftPanel={<ContactPanel contact={match.contact_a as IdentityMatchContact} />}
      rightPanel={<ContactPanel contact={match.contact_b as IdentityMatchContact} />}
      mergeButtonLabel="Merge"
      onMerge={onMerge}
      onReject={onReject}
      merging={merging}
      rejecting={rejecting}
    />
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean exit.

- [ ] **Step 4: Run identity tests**

Run: `cd frontend && npx vitest run src/app/identity`
Expected: all existing tests pass — public `MatchCard` API unchanged.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/identity/_components/
git commit -m "refactor(frontend): extract MatchCardShell from MatchCard for reuse"
```

---

## Phase 3 — Org tab + UI

### Task 17: `useOrgIdentity` hook

**Files:**
- Create: `frontend/src/hooks/use-org-identity.ts`

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/use-org-identity.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "@/lib/api-client";

export type OrgSummary = {
  id: string;
  name: string;
  domain: string | null;
  logo_url: string | null;
  linkedin_url: string | null;
  website: string | null;
  twitter_handle: string | null;
  contact_count: number;
};

export type OrgIdentityMatch = {
  id: string;
  match_score: number;
  match_method: string;
  status: string;
  org_a: OrgSummary;
  org_b: OrgSummary;
  created_at: string;
};

export function useOrgMatches() {
  return useQuery<OrgIdentityMatch[]>({
    queryKey: ["org-matches"],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/organizations/duplicates");
      return (data?.data ?? []) as OrgIdentityMatch[];
    },
    staleTime: 30 * 1000,
  });
}

export function useScanOrgs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await client.POST("/api/v1/organizations/scan-duplicates", {
        body: {},
      });
      return data?.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["org-matches"] });
      void qc.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
}

export function useMergeOrgMatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ matchId, targetId }: { matchId: string; targetId: string }) => {
      const { data, error } = await client.POST(
        "/api/v1/organizations/duplicates/{match_id}/merge",
        {
          params: { path: { match_id: matchId } },
          body: { target_id: targetId },
        },
      );
      if (error) throw new Error("Merge failed");
      return data?.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["org-matches"] });
      void qc.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
}

export function useDismissOrgMatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (matchId: string) => {
      const { data, error } = await client.POST(
        "/api/v1/organizations/duplicates/{match_id}/dismiss",
        { params: { path: { match_id: matchId } } },
      );
      if (error) throw new Error("Dismiss failed");
      return data?.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["org-matches"] });
    },
  });
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean exit.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/use-org-identity.ts
git commit -m "feat(frontend): useOrgIdentity hooks (scan, list, merge, dismiss)"
```

---

### Task 18: `OrgPanel` component

**Files:**
- Create: `frontend/src/app/identity/_components/org-panel.tsx`

- [ ] **Step 1: Create the panel**

Create `frontend/src/app/identity/_components/org-panel.tsx`:

```tsx
"use client";

import Link from "next/link";
import { Building2, Globe, Linkedin, Twitter, Users } from "lucide-react";

import { CompanyFavicon } from "@/components/company-favicon";
import type { OrgSummary } from "@/hooks/use-org-identity";

function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return /^https?:\/\//i.test(url) ? url : `https://${url}`;
}

export function OrgPanel({ org }: { org: OrgSummary }) {
  return (
    <div className="bg-stone-50 dark:bg-stone-800 rounded-lg p-4 border border-stone-100 dark:border-stone-700">
      <div className="flex items-center gap-3 mb-3">
        <CompanyFavicon domain={org.domain} size="md" />
        <div className="min-w-0 flex-1">
          <Link
            href={`/organizations/${org.id}`}
            className="text-sm font-semibold text-stone-900 dark:text-stone-100 hover:text-teal-700 dark:hover:text-teal-400 transition-colors truncate block"
            onClick={(e) => e.stopPropagation()}
          >
            {org.name}
          </Link>
          <p className="text-xs text-stone-400 dark:text-stone-500">
            <Users className="inline w-3 h-3 mr-1" />
            {org.contact_count} contact{org.contact_count !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      <div className="space-y-1.5 text-xs text-stone-600 dark:text-stone-300">
        {org.domain && (
          <div className="flex items-center gap-2">
            <Building2 className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono truncate">{org.domain}</span>
          </div>
        )}
        {org.website && (
          <div className="flex items-center gap-2 truncate">
            <Globe className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <a
              href={safeHref(org.website)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-teal-600 dark:text-teal-400 hover:underline font-mono truncate"
            >
              {org.website}
            </a>
          </div>
        )}
        {org.linkedin_url && (
          <div className="flex items-center gap-2 truncate">
            <Linkedin className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <a
              href={safeHref(org.linkedin_url)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-teal-600 dark:text-teal-400 hover:underline font-mono truncate"
            >
              LinkedIn
            </a>
          </div>
        )}
        {org.twitter_handle && (
          <div className="flex items-center gap-2">
            <Twitter className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono">@{org.twitter_handle}</span>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean exit.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/identity/_components/org-panel.tsx
git commit -m "feat(frontend): OrgPanel for org match cards"
```

---

### Task 19: `OrgMatchCard` component with tests

**Files:**
- Create: `frontend/src/app/identity/_components/org-match-card.tsx`
- Create: `frontend/src/app/identity/_components/org-match-card.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/identity/_components/org-match-card.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { OrgMatchCard } from "./org-match-card";
import type { OrgIdentityMatch } from "@/hooks/use-org-identity";

const match: OrgIdentityMatch = {
  id: "m1",
  match_score: 0.72,
  match_method: "probabilistic",
  status: "pending_review",
  created_at: "2026-05-13T00:00:00Z",
  org_a: {
    id: "a", name: "Anthropic", domain: "anthropic.com",
    logo_url: null, linkedin_url: null, website: null, twitter_handle: null,
    contact_count: 12,
  },
  org_b: {
    id: "b", name: "Anthropic, Inc.", domain: null,
    logo_url: null, linkedin_url: null, website: null, twitter_handle: null,
    contact_count: 3,
  },
};

describe("OrgMatchCard", () => {
  it("renders both org names", () => {
    render(<OrgMatchCard match={match} onMerge={vi.fn()} onReject={vi.fn()} merging={false} rejecting={false} />);
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    expect(screen.getByText("Anthropic, Inc.")).toBeInTheDocument();
  });

  it("merge button labels target as the org with more contacts", () => {
    render(<OrgMatchCard match={match} onMerge={vi.fn()} onReject={vi.fn()} merging={false} rejecting={false} />);
    // Anthropic has 12 contacts > Anthropic, Inc. with 3
    expect(screen.getByText(/Merge into Anthropic/)).toBeInTheDocument();
  });

  it("calls onMerge with the target id when merge button clicked", () => {
    const onMerge = vi.fn();
    render(<OrgMatchCard match={match} onMerge={onMerge} onReject={vi.fn()} merging={false} rejecting={false} />);
    fireEvent.click(screen.getByText(/Merge into Anthropic/));
    expect(onMerge).toHaveBeenCalledWith("a");
  });

  it("calls onReject when 'Not the same' clicked", () => {
    const onReject = vi.fn();
    render(<OrgMatchCard match={match} onMerge={vi.fn()} onReject={onReject} merging={false} rejecting={false} />);
    fireEvent.click(screen.getByText(/Not the same/));
    expect(onReject).toHaveBeenCalled();
  });

  it("shows breakdown rows when match detail toggled", () => {
    render(<OrgMatchCard match={match} onMerge={vi.fn()} onReject={vi.fn()} merging={false} rejecting={false} />);
    fireEvent.click(screen.getByText(/Match detail/));
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Domain")).toBeInTheDocument();
    expect(screen.getByText("LinkedIn")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd frontend && npx vitest run src/app/identity/_components/org-match-card.test.tsx`
Expected: error — `./org-match-card` doesn't exist.

- [ ] **Step 3: Create `OrgMatchCard`**

Create `frontend/src/app/identity/_components/org-match-card.tsx`:

```tsx
"use client";

import { MatchCardShell, type BreakdownRow } from "./match-card-shell";
import { OrgPanel } from "./org-panel";
import type { OrgIdentityMatch, OrgSummary } from "@/hooks/use-org-identity";

const ORG_BREAKDOWN: BreakdownRow[] = [
  { label: "Name", weight: 40 },
  { label: "Domain", weight: 20 },
  { label: "LinkedIn", weight: 20 },
  { label: "Website", weight: 10 },
  { label: "Twitter", weight: 10 },
];

function pickTarget(a: OrgSummary, b: OrgSummary): OrgSummary {
  return a.contact_count >= b.contact_count ? a : b;
}

export function OrgMatchCard({
  match,
  onMerge,
  onReject,
  merging,
  rejecting,
}: {
  match: OrgIdentityMatch;
  onMerge: (targetId: string) => void;
  onReject: () => void;
  merging: boolean;
  rejecting: boolean;
}) {
  const target = pickTarget(match.org_a, match.org_b);

  return (
    <MatchCardShell
      matchScore={match.match_score ?? 0}
      matchMethod={match.match_method}
      breakdownRows={ORG_BREAKDOWN}
      leftPanel={<OrgPanel org={match.org_a} />}
      rightPanel={<OrgPanel org={match.org_b} />}
      mergeButtonLabel={`Merge into ${target.name}`}
      onMerge={() => onMerge(target.id)}
      onReject={onReject}
      merging={merging}
      rejecting={rejecting}
    />
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/app/identity/_components/org-match-card.test.tsx`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/identity/_components/org-match-card.tsx frontend/src/app/identity/_components/org-match-card.test.tsx
git commit -m "feat(frontend): OrgMatchCard component with tests"
```

---

### Task 20: Add Orgs tab to `/identity` page

**Files:**
- Modify: `frontend/src/app/identity/page.tsx`

- [ ] **Step 1: Add new imports**

Open `frontend/src/app/identity/page.tsx`. The current imports look like:

```tsx
import { useState } from "react";
import { ... } from "lucide-react";
import { useIdentityMatches, ... } from "@/hooks/use-identity";
import { cn } from "@/lib/utils";
import { MatchCard } from "./_components/match-card";
```

Add these new imports alongside the existing ones:

```tsx
import { useRouter, useSearchParams } from "next/navigation";
import {
  useOrgMatches,
  useScanOrgs,
  useMergeOrgMatch,
  useDismissOrgMatch,
} from "@/hooks/use-org-identity";
import { OrgMatchCard } from "./_components/org-match-card";
```

- [ ] **Step 2: Wrap the existing body with a tab toggle (no JSX refactor)**

Do NOT extract the existing contact rendering into a separate component — just guard it with a conditional. This keeps the diff small and the contact flow untouched.

Inside the existing `IdentityPage` function, immediately after the existing `useState` calls at the top, add:

```tsx
  const searchParams = useSearchParams();
  const router = useRouter();
  const tab: "contacts" | "orgs" =
    searchParams.get("tab") === "orgs" ? "orgs" : "contacts";

  const setTab = (t: "contacts" | "orgs") => {
    const params = new URLSearchParams(searchParams.toString());
    if (t === "orgs") params.set("tab", "orgs");
    else params.delete("tab");
    router.replace(`/identity${params.toString() ? `?${params}` : ""}`);
  };
```

Then find the `<main className="max-w-6xl mx-auto px-4 py-8">` opening tag. Right after that opening `<main>`, insert the tab pills:

```tsx
        <div className="mb-6 flex items-center gap-2">
          {(["contacts", "orgs"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                tab === t
                  ? "bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-300"
                  : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200",
              )}
            >
              {t === "contacts" ? "Contacts" : "Organizations"}
            </button>
          ))}
        </div>
```

Then wrap **everything else that was inside `<main>`** (the existing header, scan button, scan-progress block, match list, etc. — but NOT the `<Toast />` element which is OUTSIDE `<main>`) with a tab conditional. The pattern is:

```tsx
        {tab === "contacts" && (
          <>
            {/* ALL existing JSX that was previously inside <main> after this point */}
          </>
        )}

        {tab === "orgs" && <OrgsTab />}
```

Concretely: locate the existing `<div className="animate-in stagger-1 mb-6 flex flex-col sm:flex-row...">` (the contact-tab header div). That is the first element you wrap. Wrap from there through to the closing `)}` of the match-list block. The `</main>` closing tag and the `{toastMsg && <Toast ... />}` after it stay where they are.

- [ ] **Step 3: Add the `OrgsTab` component**

At the bottom of `frontend/src/app/identity/page.tsx`, below the `IdentityPage` function definition:

```tsx
function OrgsTab() {
  const { data, isLoading } = useOrgMatches();
  const scanOrgs = useScanOrgs();
  const mergeOrg = useMergeOrgMatch();
  const dismissOrg = useDismissOrgMatch();
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [scanDismissed, setScanDismissed] = useState(false);

  const matches = data ?? [];
  const scanResult = scanOrgs.data as
    | { matches_found: number; auto_merged: number; pending_review: number }
    | undefined;

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3000);
  };

  const handleMerge = (matchId: string, targetId: string) => {
    mergeOrg.mutate(
      { matchId, targetId },
      {
        onSuccess: (res) =>
          showToast(`Merged — ${res?.contacts_moved ?? 0} contact(s) moved`),
        onError: (err) => showToast(`Merge failed: ${err.message}`),
      },
    );
  };

  const handleDismiss = (matchId: string) => {
    dismissOrg.mutate(matchId, {
      onSuccess: () => showToast("Marked as not the same"),
      onError: (err) => showToast(`Dismiss failed: ${err.message}`),
    });
  };

  return (
    <>
      <div className="animate-in stagger-1 mb-6 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100">
            Duplicate organizations
          </h1>
          <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">
            Review and merge duplicate orgs across all your data sources
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {matches.length > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              {matches.length} pending review
            </span>
          )}
          <button
            onClick={() => {
              setScanDismissed(false);
              scanOrgs.mutate();
            }}
            disabled={scanOrgs.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            <ScanSearch className={cn("w-4 h-4", scanOrgs.isPending && "animate-spin")} />
            {scanOrgs.isPending ? "Scanning..." : "Scan for duplicates"}
          </button>
        </div>
      </div>

      {scanOrgs.isPending && (
        <div className="mb-5">
          <div className="bg-teal-50 dark:bg-teal-950 border border-teal-200 dark:border-teal-800 rounded-xl p-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-5 h-5 border-2 border-teal-300 border-t-teal-600 rounded-full animate-spin shrink-0" />
              <span className="text-sm font-medium text-teal-800 dark:text-teal-300">
                Scanning organizations for duplicates...
              </span>
            </div>
            <p className="text-xs text-teal-600 dark:text-teal-400 mb-3 ml-8">
              Comparing names, domains, LinkedIn URLs, and websites...
            </p>
          </div>
        </div>
      )}

      {scanOrgs.isSuccess && scanResult && !scanDismissed && (
        <div className="mb-5">
          <div className="bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-xl p-4 flex items-center gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <p className="text-sm text-emerald-800 dark:text-emerald-300">
              <strong>Scan complete</strong> — {scanResult.matches_found} matches found
              {scanResult.auto_merged > 0 && `, ${scanResult.auto_merged} auto-merged`}
              {scanResult.pending_review > 0 && `, ${scanResult.pending_review} pending review`}
            </p>
            <button
              onClick={() => setScanDismissed(true)}
              className="ml-auto p-1 rounded text-emerald-500 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-48 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 animate-pulse"
            />
          ))}
        </div>
      ) : matches.length === 0 ? (
        <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-12 text-center">
          <div className="w-14 h-14 rounded-full bg-stone-100 dark:bg-stone-800 flex items-center justify-center mx-auto mb-4">
            <ScanSearch className="w-7 h-7 text-stone-400 dark:text-stone-500" />
          </div>
          <h3 className="text-base font-semibold text-stone-700 dark:text-stone-300 mb-1">
            No duplicate orgs found
          </h3>
          <p className="text-sm text-stone-400 dark:text-stone-500">
            Run a scan to detect potential duplicates
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {matches.map((m) => (
            <OrgMatchCard
              key={m.id}
              match={m}
              onMerge={(targetId) => handleMerge(m.id, targetId)}
              onReject={() => handleDismiss(m.id)}
              merging={mergeOrg.isPending}
              rejecting={dismissOrg.isPending}
            />
          ))}
        </div>
      )}

      {toastMsg && (
        <div className="fixed bottom-6 right-6 z-50">
          <div
            className="flex items-center gap-3 bg-stone-900 text-white text-sm px-4 py-3 rounded-xl shadow-xl border border-stone-700 cursor-pointer"
            onClick={() => setToastMsg(null)}
          >
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{toastMsg}</span>
          </div>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean exit.

- [ ] **Step 5: Smoke-run existing identity tests**

Run: `cd frontend && npx vitest run src/app/identity`
Expected: existing contact identity tests still pass; org tests already added in Task 19 still pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/identity/page.tsx
git commit -m "feat(frontend): Orgs tab on /identity with scan + review UI"
```

---

### Task 21: Final verification

**Files:** none — verification only.

- [ ] **Step 1: Run the targeted backend test suite**

Run: `cd backend && PYTHONPATH=. pytest tests/test_org_identity_scoring.py tests/test_org_identity_resolution.py tests/test_api_org_duplicates.py tests/test_organizations_api.py tests/test_api_doc.py -v`
Expected: all tests pass.

- [ ] **Step 2: Run CI guards**

Run: `cd backend && PYTHONPATH=. python3 scripts/check_response_models.py`
Expected: `OK: all API endpoints have response_model declared.`

Run: `bash .github/scripts/check-file-length.sh`
Expected: no new files over 500 lines (or only pre-existing ones).

Run: `bash .github/scripts/check-exception-handling.sh`
Expected: no new warnings.

- [ ] **Step 3: Run the frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: all tests pass.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean exit.

- [ ] **Step 5: Verify routes registered**

Run: `cd backend && PYTHONPATH=. python3 -c "
from app.main import fastapi_app
paths = sorted([r.path for r in fastapi_app.routes if hasattr(r, 'path') and 'duplicates' in r.path])
print('\n'.join(paths))
"`
Expected:
```
/api/v1/organizations/duplicates
/api/v1/organizations/duplicates/{match_id}/dismiss
/api/v1/organizations/duplicates/{match_id}/merge
/api/v1/organizations/scan-duplicates
```

---

## After all tasks complete

The feature is end-to-end functional: scan button on `/identity?tab=orgs` calls `POST /scan-duplicates` which auto-merges deterministic pairs and queues fuzzy ones; the queue renders via `GET /duplicates`; merge/dismiss buttons resolve individual pairs.

Commit history is split into three phase boundaries (after Tasks 9, 15, and 20) — each is a logical PR boundary if you want to land in pieces.

Suggested commit-to-PR mapping (rebase the branch as needed):

- **PR 1 — Backend foundation:** Tasks 1–9. No user-visible change. Migration runs on deploy.
- **PR 2 — API + frontend refactor:** Tasks 10–16. API live and testable; `MatchCardShell` extraction is the only frontend change.
- **PR 3 — Org tab + UI:** Tasks 17–20 plus the verification in Task 21. Feature live end-to-end.
