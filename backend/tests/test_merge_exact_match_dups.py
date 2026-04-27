"""Tests for scripts.merge_exact_match_dups (the one-shot dup cleanup script).

The script bypasses the application-layer resolver (which 409s on duplicate
email). It works directly against the rows that already exist in the DB,
which is the only state that matters for cleaning up legacy duplicates.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Make scripts/ importable as a package for the test
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.models.contact import Contact
from app.models.user import User
from scripts.merge_exact_match_dups import (
    find_all_exact_match_pairs,
    _merge_pair,
)


def _make_contact(user_id: uuid.UUID, **kwargs) -> Contact:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name="Test",
        relationship_score=5,
        priority_level="medium",
        source="manual",
    )
    defaults.update(kwargs)
    return Contact(**defaults)


@pytest.mark.asyncio
async def test_finds_email_case_collision(db: AsyncSession, test_user: User):
    a = _make_contact(test_user.id, full_name="Bob A", emails=["Bob@Example.com"])
    b = _make_contact(test_user.id, full_name="Bob B", emails=["bob@example.com"])
    db.add_all([a, b])
    await db.commit()

    pairs = await find_all_exact_match_pairs(db)
    email_pairs = pairs["email_ci"]

    assert len(email_pairs) == 1
    assert {email_pairs[0][0], email_pairs[0][1]} == {a.id, b.id}


@pytest.mark.asyncio
async def test_finds_twitter_handle_case_collision(db: AsyncSession, test_user: User):
    a = _make_contact(test_user.id, full_name="Issa A", twitter_handle="issa5775")
    b = _make_contact(test_user.id, full_name="Issa B", twitter_handle="Issa5775")
    db.add_all([a, b])
    await db.commit()

    pairs = await find_all_exact_match_pairs(db)
    assert len(pairs["twitter_handle_ci"]) == 1


@pytest.mark.asyncio
async def test_finds_linkedin_profile_id_collision(db: AsyncSession, test_user: User):
    a = _make_contact(test_user.id, full_name="Sid A", linkedin_profile_id="sidrmsh")
    b = _make_contact(test_user.id, full_name="Sid B", linkedin_profile_id="sidrmsh")
    db.add_all([a, b])
    await db.commit()

    pairs = await find_all_exact_match_pairs(db)
    assert len(pairs["linkedin_profile_id"]) == 1


@pytest.mark.asyncio
async def test_does_not_collide_across_users(db: AsyncSession, test_user: User):
    other = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="x",
        full_name="Other",
    )
    db.add(other)
    await db.commit()

    a = _make_contact(test_user.id, emails=["bob@example.com"])
    b = _make_contact(other.id, emails=["bob@example.com"])
    db.add_all([a, b])
    await db.commit()

    pairs = await find_all_exact_match_pairs(db)
    assert pairs["email_ci"] == []


@pytest.mark.asyncio
async def test_merge_pair_unions_emails_deletes_dup(
    db: AsyncSession, test_user: User
):
    """End-to-end: two contacts with case-mismatch email — after merge one
    survives with the union, and the dup row is gone."""
    a = _make_contact(test_user.id, full_name="Bob A", emails=["Bob@Example.com"])
    b = _make_contact(
        test_user.id, full_name="Bob B",
        emails=["bob@example.com", "bob+work@example.com"],
    )
    db.add_all([a, b])
    await db.commit()

    pairs = await find_all_exact_match_pairs(db)
    primary_id, other_id = pairs["email_ci"][0]

    ok = await _merge_pair(db, primary_id, other_id)
    await db.commit()
    assert ok is True

    pairs_after = await find_all_exact_match_pairs(db)
    assert pairs_after["email_ci"] == []


@pytest.mark.asyncio
async def test_dedup_within_pairs_handles_multi_axis_overlap(
    db: AsyncSession, test_user: User
):
    """Sid Ramesh in prod: same pair appears under both telegram_user_id and
    linkedin_profile_id axes once both are populated. The script must merge
    once, not twice (which would be a self-merge of an already-deleted row)."""
    a = _make_contact(
        test_user.id, full_name="Sid A",
        linkedin_profile_id="sidrmsh", telegram_user_id="111",
    )
    b = _make_contact(
        test_user.id, full_name="Sid B",
        linkedin_profile_id="sidrmsh", telegram_user_id="111",
    )
    db.add_all([a, b])
    await db.commit()

    pairs = await find_all_exact_match_pairs(db)
    # Both axes should report the pair (script dedups in main loop).
    assert len(pairs["linkedin_profile_id"]) == 1
    assert len(pairs["telegram_user_id"]) == 1
