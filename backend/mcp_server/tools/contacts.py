"""MCP tools for contact search and lookup."""

import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.services.contact_search import build_contact_filter_query
from mcp_server.server import mcp_app
from mcp_server.db import get_session

_current_user_id = None


def set_user_id(uid):
    global _current_user_id
    _current_user_id = uid


# Map MCP-friendly score labels → internal filter values
_SCORE_MAP = {
    "strong": "strong",
    "warm": "active",
    "cold": "dormant",
}


async def _search_contacts(
    user_id: _uuid.UUID,
    db: AsyncSession,
    *,
    query: str | None = None,
    tag: str | None = None,
    score: str | None = None,
    priority: str | None = None,
    limit: int = 20,
) -> str:
    """Search contacts and return a Markdown table."""
    mapped_score = _SCORE_MAP.get(score) if score else None

    stmt = build_contact_filter_query(
        user_id,
        search=query,
        tag=tag,
        score=mapped_score,
        priority=priority,
    )
    stmt = stmt.order_by(Contact.relationship_score.desc()).limit(limit)

    result = await db.execute(stmt)
    contacts = result.scalars().all()

    if not contacts:
        return "No contacts found matching your criteria."

    lines = ["| Name | Company | Title | Score | Last Interaction | Tags |"]
    lines.append("|---|---|---|---|---|---|")
    for c in contacts:
        name = c.full_name or "—"
        company = c.company or "—"
        title = c.title or "—"
        score_val = str(c.relationship_score)
        last_ix = c.last_interaction_at.strftime("%Y-%m-%d") if c.last_interaction_at else "—"
        tags = ", ".join(c.tags) if c.tags else "—"
        lines.append(f"| {name} | {company} | {title} | {score_val} | {last_ix} | {tags} |")

    return "\n".join(lines)


async def _get_contact(
    user_id: _uuid.UUID,
    db: AsyncSession,
    *,
    contact_id: str | None = None,
    name: str | None = None,
) -> str:
    """Look up a single contact by UUID or fuzzy name match."""
    if not contact_id and not name:
        return "Provide either contact_id or name to look up a contact."

    contact: Contact | None = None

    if contact_id:
        try:
            cid = _uuid.UUID(contact_id)
        except (ValueError, AttributeError):
            return "Invalid contact ID — expected a UUID."

        stmt = select(Contact).where(Contact.id == cid, Contact.user_id == user_id)
        result = await db.execute(stmt)
        contact = result.scalar_one_or_none()
    else:
        # Fuzzy name search via ILIKE
        pattern = f"%{name}%"
        stmt = (
            select(Contact)
            .where(Contact.user_id == user_id, Contact.full_name.ilike(pattern))
            .limit(1)
        )
        result = await db.execute(stmt)
        matches = result.scalars().all()
        contact = matches[0] if matches else None

    if not contact:
        return "Contact not found."

    # Build formatted profile
    lines = [f"# {contact.full_name or '(unnamed)'}"]

    if contact.title or contact.company:
        parts = [p for p in [contact.title, contact.company] if p]
        lines.append(f"**{' at '.join(parts)}**")

    lines.append("")

    if contact.emails:
        lines.append(f"**Emails:** {', '.join(contact.emails)}")
    if contact.phones:
        lines.append(f"**Phones:** {', '.join(contact.phones)}")

    lines.append(f"**Score:** {contact.relationship_score}/10")
    lines.append(f"**Interactions:** {contact.interaction_count}")
    lines.append(f"**Priority:** {contact.priority_level}")

    if contact.last_interaction_at:
        lines.append(f"**Last interaction:** {contact.last_interaction_at.strftime('%Y-%m-%d')}")

    if contact.tags:
        lines.append(f"**Tags:** {', '.join(contact.tags)}")

    # Bios
    bios = []
    if contact.twitter_bio:
        bios.append(f"**Twitter:** {contact.twitter_bio}")
    if contact.linkedin_headline:
        bios.append(f"**LinkedIn:** {contact.linkedin_headline}")
    if contact.linkedin_bio:
        bios.append(f"**LinkedIn bio:** {contact.linkedin_bio}")
    if contact.telegram_bio:
        bios.append(f"**Telegram:** {contact.telegram_bio}")

    if bios:
        lines.append("")
        lines.append("## Bios")
        lines.extend(bios)

    return "\n".join(lines)


@mcp_app.tool()
async def search_contacts(
    query: str | None = None,
    tag: str | None = None,
    score: str | None = None,
    priority: str | None = None,
    limit: int | None = None,
) -> str:
    """Search your contacts by name, company, tag, score tier (strong/warm/cold), or priority level."""
    async with get_session() as db:
        return await _search_contacts(
            _current_user_id,
            db,
            query=query or None,
            tag=tag or None,
            score=score or None,
            priority=priority or None,
            limit=limit if limit is not None else 20,
        )


@mcp_app.tool()
async def get_contact(contact_id: str | None = None, name: str | None = None) -> str:
    """Get full profile for a contact. Provide either contact_id (UUID) or name for fuzzy search."""
    async with get_session() as db:
        return await _get_contact(_current_user_id, db, contact_id=contact_id or None, name=name or None)
