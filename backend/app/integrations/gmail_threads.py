from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.gmail_helpers import (
    _clean_snippet,
    _extract_bcc_hashes,
    _extract_header,
    _extract_plain_body,
    _find_contact_by_bcc_hash,
    _find_contact_by_email,
    _parse_email_addresses,
)
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User

logger = logging.getLogger(__name__)


def _process_thread_messages(
    thread_data: dict, own_emails: frozenset[str]
) -> list[dict]:
    messages = thread_data.get("messages", [])
    if not messages:
        return []

    thread_id = thread_data.get("id", "")

    first_headers = messages[0].get("payload", {}).get("headers", [])
    subject = _extract_header(first_headers, "subject") or "(no subject)"

    all_participants: set[str] = set()
    for msg in messages:
        msg_headers = msg.get("payload", {}).get("headers", [])
        for hdr in ("from", "to", "cc"):
            all_participants.update(_parse_email_addresses(_extract_header(msg_headers, hdr)))

    results = []
    for msg in messages:
        msg_id = msg.get("id", "")
        if not msg_id:
            continue

        msg_headers = msg.get("payload", {}).get("headers", [])
        from_addrs = _parse_email_addresses(_extract_header(msg_headers, "from"))
        to_addrs = _parse_email_addresses(_extract_header(msg_headers, "to"))
        cc_addrs = _parse_email_addresses(_extract_header(msg_headers, "cc"))
        bcc_addrs = _parse_email_addresses(_extract_header(msg_headers, "bcc"))

        all_addrs = to_addrs + cc_addrs + bcc_addrs
        bcc_hashes = list(dict.fromkeys(
            h for own in sorted(own_emails) for h in _extract_bcc_hashes(all_addrs, own)
        ))
        rfc_message_id = _extract_header(msg_headers, "message-id").strip() or None

        if any(addr in own_emails for addr in from_addrs):
            direction = "outbound"
            counterpart_emails = [
                e for e in (to_addrs + cc_addrs)
                if e not in own_emails and "+" not in e.split("@")[0]
            ]
        else:
            direction = "inbound"
            counterpart_emails = [e for e in from_addrs if e not in own_emails]

        internal_date_ms = int(msg.get("internalDate", 0))
        occurred_at = datetime.fromtimestamp(internal_date_ms / 1000, tz=UTC)

        body = _extract_plain_body(msg.get("payload", {}))
        snippet = body if body else (msg.get("snippet", "") or "")

        results.append({
            "message_id": msg_id,
            "thread_id": thread_id,
            "subject": subject,
            "direction": direction,
            "snippet": snippet,
            "occurred_at": occurred_at,
            "counterpart_emails": counterpart_emails,
            "all_participants": list(all_participants),
            "bcc_hashes": bcc_hashes,
            "rfc_message_id": rfc_message_id,
        })

    return results


def _backfill_rfc_id(interaction: Interaction, rfc_id: str | None) -> None:
    if rfc_id and not (interaction.extra_data or {}).get("rfc_message_id"):
        interaction.extra_data = {**(interaction.extra_data or {}), "rfc_message_id": rfc_id}


async def _rfc_message_already_synced(
    rfc_id: str, contact_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> bool:
    result = await db.execute(
        select(Interaction.id).where(
            Interaction.user_id == user_id,
            Interaction.contact_id == contact_id,
            Interaction.extra_data["rfc_message_id"].as_string() == rfc_id,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _sync_thread_messages(
    thread_data: dict,
    user: User,
    own_emails: frozenset[str],
    db: AsyncSession,
    service: Any = None,
) -> int:
    msg_metas = _process_thread_messages(thread_data, own_emails)

    has_bcc = any(meta.get("bcc_hashes") for meta in msg_metas)
    if has_bcc and service and not _extract_plain_body(thread_data.get("messages", [{}])[0].get("payload", {})):
        try:
            full_data = (
                service.users()
                .threads()
                .get(userId="me", id=thread_data.get("id", ""), format="full")
                .execute()
            )
            msg_metas = _process_thread_messages(full_data, own_emails)
        except Exception:
            logger.exception(
                "Failed to re-fetch thread %s with full format for user %s",
                thread_data.get("id"), user.id,
            )
    if not msg_metas:
        return 0

    new_count = 0

    for meta in msg_metas:
        ref_id = f"gmail:{meta['message_id']}"

        matched_contacts: list[Contact] = []
        matched_via_bcc = False
        for bcc_hash in meta.get("bcc_hashes", []):
            contact = await _find_contact_by_bcc_hash(bcc_hash, user.id, db)
            if contact and contact not in matched_contacts:
                matched_contacts.append(contact)
                matched_via_bcc = True

        if not matched_contacts:
            for addr in meta["counterpart_emails"]:
                contact = await _find_contact_by_email(addr, user.id, db)
                if contact and contact not in matched_contacts:
                    matched_contacts.append(contact)

        if not matched_contacts:
            for addr in meta["all_participants"]:
                if addr in own_emails:
                    continue
                contact = await _find_contact_by_email(addr, user.id, db)
                if contact and contact not in matched_contacts:
                    matched_contacts.append(contact)

        if not matched_contacts:
            continue

        preview = meta["snippet"] if matched_via_bcc else _clean_snippet(meta["snippet"])

        if not preview.strip():
            continue

        for contact in matched_contacts:
            existing_result = await db.execute(
                select(Interaction).where(
                    Interaction.raw_reference_id == ref_id,
                    Interaction.contact_id == contact.id,
                    Interaction.user_id == user.id,
                ).limit(1)
            )
            already_synced = existing_result.scalar_one_or_none()
            if already_synced:
                _backfill_rfc_id(already_synced, meta.get("rfc_message_id"))
                continue

            old_ref = meta["thread_id"]
            old_result = await db.execute(
                select(Interaction).where(
                    Interaction.raw_reference_id == old_ref,
                    Interaction.contact_id == contact.id,
                    Interaction.user_id == user.id,
                ).limit(1)
            )
            old_existing = old_result.scalar_one_or_none()
            if old_existing:
                old_existing.raw_reference_id = ref_id
                old_existing.direction = meta["direction"]
                old_existing.content_preview = preview[:500] if preview else None
                old_existing.occurred_at = meta["occurred_at"]
                _backfill_rfc_id(old_existing, meta.get("rfc_message_id"))
                continue

            rfc_id = meta.get("rfc_message_id")
            if rfc_id:
                if await _rfc_message_already_synced(rfc_id, contact.id, user.id, db):
                    continue

            interaction = Interaction(
                id=uuid.uuid4(),
                contact_id=contact.id,
                user_id=user.id,
                platform="email",
                direction=meta["direction"],
                content_preview=preview[:500] if preview else None,
                raw_reference_id=ref_id,
                occurred_at=meta["occurred_at"],
                extra_data={"rfc_message_id": rfc_id} if rfc_id else None,
            )
            db.add(interaction)
            new_count += 1

            if (
                contact.last_interaction_at is None
                or contact.last_interaction_at < meta["occurred_at"]
            ):
                contact.last_interaction_at = meta["occurred_at"]

    return new_count
