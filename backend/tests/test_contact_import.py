"""Tests for app/services/contact_import.py."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.user import User
from app.services.contact_import import (
    _normalize_linkedin_name,
    import_csv,
    import_linkedin_connections,
    import_linkedin_messages,
    parse_name_org,
)


# ---------------------------------------------------------------------------
# Local user fixture — unique email per test to avoid unique-constraint
# collisions when setup_database recreates the schema between tests.
# Uses flush (not commit) so teardown rollback works cleanly.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="function")
async def user(db: AsyncSession) -> User:
    from app.core.auth import hash_password

    u = User(
        id=uuid.uuid4(),
        email=f"import_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("pw"),
        full_name="Import Test User",
    )
    db.add(u)
    await db.flush()
    return u


# ---------------------------------------------------------------------------
# parse_name_org unit tests (no DB needed)
# ---------------------------------------------------------------------------


def test_parse_name_org_no_separator():
    name, org = parse_name_org("Alice Smith")
    assert name == "Alice Smith"
    assert org is None


def test_parse_name_org_pipe_separator():
    name, org = parse_name_org("Jan | Safe Foundation")
    assert name == "Jan"
    assert org == "Safe Foundation"


def test_parse_name_org_at_separator():
    name, org = parse_name_org("Mickey @ Arcadia")
    assert name == "Mickey"
    assert org == "Arcadia"


def test_parse_name_org_slash_separator():
    name, org = parse_name_org("Alice / ACME Corp")
    assert name == "Alice"
    assert org == "ACME Corp"


def test_parse_name_org_empty_string():
    name, org = parse_name_org("")
    assert name is None
    assert org is None


def test_parse_name_org_none_input():
    name, org = parse_name_org(None)
    assert name is None
    assert org is None


# ---------------------------------------------------------------------------
# import_csv tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_csv_standard_columns(db: AsyncSession, user: User):
    """Standard CSV with full_name, emails, phones columns creates contacts."""
    csv_bytes = (
        "full_name,emails,phones,company,title,notes\n"
        "Alice Smith,alice@example.com,+1111111111,Acme,Engineer,First note\n"
        "Bob Jones,bob@example.com;bob2@example.com,+2222222222,Beta Corp,Manager,\n"
    ).encode()

    result = await import_csv(csv_bytes, user.id, db)

    assert result["errors"] == []
    assert len(result["created"]) == 2

    names = {r["full_name"] for r in result["created"]}
    assert names == {"Alice Smith", "Bob Jones"}

    rows = (await db.execute(select(Contact).where(Contact.user_id == user.id))).scalars().all()
    assert len(rows) == 2

    alice = next(r for r in rows if r.full_name == "Alice Smith")
    assert alice.emails == ["alice@example.com"]
    assert alice.phones == ["+1111111111"]
    assert alice.company == "Acme"
    assert alice.title == "Engineer"
    assert alice.notes == "First note"
    assert alice.source == "csv"

    bob = next(r for r in rows if r.full_name == "Bob Jones")
    assert bob.emails == ["bob@example.com", "bob2@example.com"]


@pytest.mark.asyncio
async def test_import_csv_alternate_column_names(db: AsyncSession, user: User):
    """Alternate column names (name, first_name, last_name, job_title, twitter, telegram) are mapped."""
    csv_bytes = (
        "name,first_name,last_name,job_title,twitter,telegram\n"
        "Carol White,Carol,White,Designer,@carolw,carolw_tg\n"
    ).encode()

    result = await import_csv(csv_bytes, user.id, db)

    assert result["errors"] == []
    assert len(result["created"]) == 1

    rows = (await db.execute(select(Contact).where(Contact.user_id == user.id))).scalars().all()
    carol = rows[0]
    assert carol.full_name == "Carol White"
    assert carol.given_name == "Carol"
    assert carol.family_name == "White"
    assert carol.title == "Designer"
    assert carol.twitter_handle == "@carolw"
    assert carol.telegram_username == "carolw_tg"


@pytest.mark.asyncio
async def test_import_csv_name_with_org_separator(db: AsyncSession, user: User):
    """A full_name value containing an org separator is split into name and company."""
    csv_bytes = (
        "full_name,emails\n"
        "Dave | TechCo,dave@tech.co\n"
    ).encode()

    result = await import_csv(csv_bytes, user.id, db)

    assert result["errors"] == []
    rows = (await db.execute(select(Contact).where(Contact.user_id == user.id))).scalars().all()
    dave = rows[0]
    assert dave.full_name == "Dave"
    assert dave.company == "TechCo"


@pytest.mark.asyncio
async def test_import_csv_tags_parsed(db: AsyncSession, user: User):
    """Semicolon-separated tags are stored as a list."""
    csv_bytes = (
        "full_name,tags\n"
        "Eve Black,vip;investor;friend\n"
    ).encode()

    result = await import_csv(csv_bytes, user.id, db)

    assert result["errors"] == []
    rows = (await db.execute(select(Contact).where(Contact.user_id == user.id))).scalars().all()
    assert rows[0].tags == ["vip", "investor", "friend"]


@pytest.mark.asyncio
async def test_import_csv_empty_file(db: AsyncSession, user: User):
    """A CSV with only a header row (no data) creates no contacts and no errors."""
    csv_bytes = b"full_name,emails,phones\n"

    result = await import_csv(csv_bytes, user.id, db)

    assert result["errors"] == []
    assert result["created"] == []

    rows = (await db.execute(select(Contact).where(Contact.user_id == user.id))).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_import_csv_missing_name_field(db: AsyncSession, user: User):
    """A CSV without any name column still creates contacts (full_name will be None)."""
    csv_bytes = (
        "emails,phones\n"
        "noname@example.com,+9999999999\n"
    ).encode()

    result = await import_csv(csv_bytes, user.id, db)

    # No errors — the service does not require a name
    assert result["errors"] == []
    assert len(result["created"]) == 1

    rows = (await db.execute(select(Contact).where(Contact.user_id == user.id))).scalars().all()
    assert rows[0].full_name is None
    assert rows[0].emails == ["noname@example.com"]


@pytest.mark.asyncio
async def test_import_csv_large_batch(db: AsyncSession, user: User):
    """Importing 100 rows creates exactly 100 contacts without errors."""
    rows_data = "\n".join(
        f"Person {i},person{i}@example.com,+100000{i:04d},Company {i},Role {i},"
        for i in range(100)
    )
    csv_bytes = ("full_name,emails,phones,company,title,notes\n" + rows_data + "\n").encode()

    result = await import_csv(csv_bytes, user.id, db)

    assert result["errors"] == []
    assert len(result["created"]) == 100

    count_result = await db.execute(select(Contact).where(Contact.user_id == user.id))
    assert len(count_result.scalars().all()) == 100


@pytest.mark.asyncio
async def test_import_csv_utf8_bom_handling(db: AsyncSession, user: User):
    """A CSV with a UTF-8 BOM byte order mark is handled correctly."""
    csv_bytes = "\ufefffield_a,full_name,emails\nignored,BOM User,bom@example.com\n".encode("utf-8-sig")

    result = await import_csv(csv_bytes, user.id, db)

    assert result["errors"] == []
    assert len(result["created"]) == 1
    rows = (await db.execute(select(Contact).where(Contact.user_id == user.id))).scalars().all()
    assert rows[0].full_name == "BOM User"


# ---------------------------------------------------------------------------
# import_linkedin_connections tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_linkedin_connections_basic(db: AsyncSession, user: User):
    """A LinkedIn Connections CSV with preamble lines is parsed correctly."""
    csv_bytes = (
        "Notes: LinkedIn connections export\n"
        "First Name,Last Name,Email Address,Company,Position,Connected On,URL\n"
        "Frank,Castle,frank@example.com,Shield,Agent,01 Jan 2023,https://linkedin.com/in/frank\n"
    ).encode()

    result = await import_linkedin_connections(csv_bytes, user.id, db)

    assert result["errors"] == []
    assert result["created"] == 1
    assert result["skipped"] == 0

    rows = (await db.execute(select(Contact).where(Contact.user_id == user.id))).scalars().all()
    assert len(rows) == 1
    frank = rows[0]
    assert frank.full_name == "Frank Castle"
    assert frank.given_name == "Frank"
    assert frank.family_name == "Castle"
    assert frank.emails == ["frank@example.com"]
    assert frank.company == "Shield"
    assert frank.title == "Agent"
    assert frank.linkedin_url == "https://linkedin.com/in/frank"
    assert frank.source == "linkedin"


@pytest.mark.asyncio
async def test_import_linkedin_connections_no_preamble(db: AsyncSession, user: User):
    """LinkedIn CSV without preamble lines (header is the first row) still works."""
    csv_bytes = (
        "First Name,Last Name,Email Address,Company,Position,Connected On,URL\n"
        "Grace,Hopper,grace@example.com,Navy,Admiral,01 Jan 1960,\n"
    ).encode()

    result = await import_linkedin_connections(csv_bytes, user.id, db)

    assert result["created"] == 1
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_import_linkedin_connections_duplicate_detection(db: AsyncSession, user: User):
    """A contact that already exists (same full_name + company) is skipped."""
    # Pre-create the contact
    existing = Contact(
        user_id=user.id,
        full_name="Hank Pym",
        company="Pym Tech",
        source="manual",
    )
    db.add(existing)
    await db.flush()

    csv_bytes = (
        "First Name,Last Name,Email Address,Company,Position,Connected On,URL\n"
        "Hank,Pym,hank@pymtech.com,Pym Tech,Scientist,01 Jan 2020,\n"
    ).encode()

    result = await import_linkedin_connections(csv_bytes, user.id, db)

    assert result["created"] == 0
    assert result["skipped"] == 1
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_import_linkedin_connections_no_name_rows_skipped(db: AsyncSession, user: User):
    """Rows with empty first and last name are silently skipped."""
    csv_bytes = (
        "First Name,Last Name,Email Address,Company,Position,Connected On,URL\n"
        ",,empty@example.com,Nowhere,Unknown,01 Jan 2023,\n"
        "Valid,Person,valid@example.com,Co,Title,01 Jan 2023,\n"
    ).encode()

    result = await import_linkedin_connections(csv_bytes, user.id, db)

    assert result["created"] == 1
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_import_linkedin_connections_empty_csv(db: AsyncSession, user: User):
    """A LinkedIn CSV with only the header row creates no contacts."""
    csv_bytes = (
        "First Name,Last Name,Email Address,Company,Position,Connected On,URL\n"
    ).encode()

    result = await import_linkedin_connections(csv_bytes, user.id, db)

    assert result["created"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# import_linkedin_messages tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="function")
async def user_with_contact(db: AsyncSession) -> tuple[User, Contact]:
    """User + a linked contact for LinkedIn messages tests."""
    from app.core.auth import hash_password

    u = User(
        id=uuid.uuid4(),
        email=f"liimport_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("pw"),
        full_name="LI Import User",
    )
    db.add(u)
    await db.flush()

    contact = Contact(
        user_id=u.id,
        full_name="Irene Adler",
        source="linkedin",
    )
    db.add(contact)
    await db.flush()
    return u, contact


@pytest.mark.asyncio
async def test_import_linkedin_messages_inbound(
    db: AsyncSession, user_with_contact: tuple[User, Contact]
):
    """An inbound message (FROM contact, TO user) creates an inbound Interaction."""
    u, contact = user_with_contact
    csv_bytes = (
        "CONVERSATION ID,FROM,TO,DATE,SUBJECT,CONTENT\n"
        "conv1,Irene Adler,li import user,2023-06-01 10:00:00 UTC,,Hello from Irene\n"
    ).encode()

    result = await import_linkedin_messages(csv_bytes, u.id, "li import user", db)

    assert result["new_interactions"] == 1
    assert result["skipped"] == 0
    assert result["unmatched"] == 0

    interactions = (
        await db.execute(select(Interaction).where(Interaction.contact_id == contact.id))
    ).scalars().all()
    assert len(interactions) == 1
    iact = interactions[0]
    assert iact.direction == "inbound"
    assert iact.content_preview == "Hello from Irene"
    assert iact.platform == "linkedin"
    assert iact.raw_reference_id == "linkedin:conv1:2023-06-01 10:00:00 UTC"


@pytest.mark.asyncio
async def test_import_linkedin_messages_outbound(
    db: AsyncSession, user_with_contact: tuple[User, Contact]
):
    """An outbound message (FROM user, TO contact) creates an outbound Interaction."""
    u, contact = user_with_contact
    csv_bytes = (
        "CONVERSATION ID,FROM,TO,DATE,SUBJECT,CONTENT\n"
        "conv2,li import user,Irene Adler,2023-06-02 12:00:00 UTC,,Hi back\n"
    ).encode()

    result = await import_linkedin_messages(csv_bytes, u.id, "li import user", db)

    assert result["new_interactions"] == 1

    interactions = (
        await db.execute(select(Interaction).where(Interaction.contact_id == contact.id))
    ).scalars().all()
    assert interactions[0].direction == "outbound"


@pytest.mark.asyncio
async def test_import_linkedin_messages_duplicate_skipped(
    db: AsyncSession, user_with_contact: tuple[User, Contact]
):
    """Importing the same message CSV twice skips duplicates on the second import."""
    u, contact = user_with_contact
    csv_bytes = (
        "CONVERSATION ID,FROM,TO,DATE,SUBJECT,CONTENT\n"
        "conv3,Irene Adler,li import user,2023-06-03 09:00:00 UTC,,Dedup test\n"
    ).encode()

    result1 = await import_linkedin_messages(csv_bytes, u.id, "li import user", db)
    await db.flush()

    result2 = await import_linkedin_messages(csv_bytes, u.id, "li import user", db)

    assert result1["new_interactions"] == 1
    assert result2["new_interactions"] == 0
    assert result2["skipped"] == 1


@pytest.mark.asyncio
async def test_import_linkedin_messages_unmatched_contact(db: AsyncSession, user: User):
    """Messages whose counterpart does not exist as a contact are counted as unmatched."""
    csv_bytes = (
        "CONVERSATION ID,FROM,TO,DATE,SUBJECT,CONTENT\n"
        "conv4,Unknown Person,import test user,2023-06-04 08:00:00 UTC,,Hey stranger\n"
    ).encode()

    result = await import_linkedin_messages(csv_bytes, user.id, "import test user", db)

    assert result["new_interactions"] == 0
    assert result["unmatched"] == 1
    assert "Unknown Person" in result["unmatched_names"]


@pytest.mark.asyncio
async def test_import_linkedin_messages_updates_last_interaction_at(
    db: AsyncSession, user_with_contact: tuple[User, Contact]
):
    """Importing messages updates contact.last_interaction_at to the most recent message date."""
    u, contact = user_with_contact
    csv_bytes = (
        "CONVERSATION ID,FROM,TO,DATE,SUBJECT,CONTENT\n"
        "conv5,Irene Adler,li import user,2024-01-15 14:00:00 UTC,,Recent message\n"
    ).encode()

    await import_linkedin_messages(csv_bytes, u.id, "li import user", db)
    await db.flush()
    await db.refresh(contact)

    assert contact.last_interaction_at is not None
    assert contact.last_interaction_at.year == 2024
    assert contact.last_interaction_at.month == 1
    assert contact.last_interaction_at.day == 15


# ---------------------------------------------------------------------------
# _normalize_linkedin_name unit tests
# ---------------------------------------------------------------------------


def test_normalize_strips_suffix_mba():
    assert _normalize_linkedin_name("Aaron Schneider, MBA") == "aaron schneider"


def test_normalize_strips_suffix_phd():
    assert _normalize_linkedin_name("Jane Doe, PhD") == "jane doe"


def test_normalize_strips_emoji_star():
    assert _normalize_linkedin_name("Adam Shaw ★") == "adam shaw"


def test_normalize_strips_special_chars():
    assert _normalize_linkedin_name("María García-López") == "maría garcía lópez"


def test_normalize_collapses_whitespace():
    assert _normalize_linkedin_name("  John   Smith  ") == "john smith"


def test_normalize_empty():
    assert _normalize_linkedin_name("") == ""


# ---------------------------------------------------------------------------
# import_linkedin_connections — duplicate contact tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_linkedin_connections_multiple_existing_duplicates(
    db: AsyncSession, user: User,
):
    """If the DB already has two contacts with the same name+company,
    the dedup check must not crash (previously used scalar_one_or_none)."""
    for _ in range(2):
        db.add(Contact(user_id=user.id, full_name="Dupe Person", company="SameCo", source="manual"))
    await db.flush()

    csv_bytes = (
        "First Name,Last Name,Email Address,Company,Position,Connected On,URL\n"
        "Dupe,Person,,SameCo,,,\n"
    ).encode()

    result = await import_linkedin_connections(csv_bytes, user.id, db)

    assert result["errors"] == []
    assert result["skipped"] == 1
    assert result["created"] == 0


# ---------------------------------------------------------------------------
# import_linkedin_messages — normalized matching
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="function")
async def user_with_varied_contacts(db: AsyncSession) -> tuple[User, list[Contact]]:
    """User + contacts with clean names for normalized matching tests."""
    from app.core.auth import hash_password

    u = User(
        id=uuid.uuid4(),
        email=f"norm_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("pw"),
        full_name="Norm Test User",
    )
    db.add(u)
    await db.flush()

    contacts = []
    for name in ["Aaron Schneider", "Adam Shaw", "Jane Doe"]:
        c = Contact(user_id=u.id, full_name=name, source="linkedin")
        db.add(c)
        contacts.append(c)
    await db.flush()
    return u, contacts


@pytest.mark.asyncio
async def test_import_messages_matches_name_with_suffix(
    db: AsyncSession, user_with_varied_contacts: tuple[User, list[Contact]],
):
    """'Aaron Schneider, MBA' in messages matches contact 'Aaron Schneider'."""
    u, contacts = user_with_varied_contacts
    csv_bytes = (
        'CONVERSATION ID,FROM,TO,DATE,SUBJECT,CONTENT\n'
        'conv10,"Aaron Schneider, MBA",norm test user,2024-01-01 10:00:00 UTC,,Hello\n'
    ).encode()

    result = await import_linkedin_messages(csv_bytes, u.id, "norm test user", db)

    assert result["new_interactions"] == 1
    assert result["unmatched"] == 0


@pytest.mark.asyncio
async def test_import_messages_matches_name_with_emoji(
    db: AsyncSession, user_with_varied_contacts: tuple[User, list[Contact]],
):
    """'Adam Shaw ★' in messages matches contact 'Adam Shaw'."""
    u, contacts = user_with_varied_contacts
    csv_bytes = (
        "CONVERSATION ID,FROM,TO,DATE,SUBJECT,CONTENT\n"
        "conv11,Adam Shaw \u2605,norm test user,2024-02-01 10:00:00 UTC,,Hey there\n"
    ).encode()

    result = await import_linkedin_messages(csv_bytes, u.id, "norm test user", db)

    assert result["new_interactions"] == 1
    assert result["unmatched"] == 0
