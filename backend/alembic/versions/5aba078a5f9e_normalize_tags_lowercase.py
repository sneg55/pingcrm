"""normalize_tags_lowercase

Revision ID: 5aba078a5f9e
Revises: 616a94d52e40
Create Date: 2026-03-16 10:59:04.458328

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5aba078a5f9e'
down_revision: Union[str, None] = '616a94d52e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Normalize all tags to lowercase and deduplicate within each contact.
    op.execute("""
        UPDATE contacts
        SET tags = (
            SELECT COALESCE(array_agg(DISTINCT lower(tag)), '{}')
            FROM unnest(tags) AS tag
        )
        WHERE tags IS NOT NULL AND array_length(tags, 1) > 0
    """)

    # 2. Trim whitespace from company names.
    op.execute("""
        UPDATE contacts
        SET company = btrim(company)
        WHERE company IS NOT NULL AND company != btrim(company)
    """)

    # 3. Normalize company name casing to most-common variant per
    #    case-insensitive group.  For each group of case-duplicates,
    #    pick the variant with the highest count as canonical.
    op.execute("""
        UPDATE contacts c
        SET company = canonical.name
        FROM (
            SELECT DISTINCT ON (lower(company))
                lower(company) AS key,
                company AS name
            FROM contacts
            WHERE company IS NOT NULL
            GROUP BY company
            ORDER BY lower(company), count(*) DESC
        ) canonical
        WHERE lower(c.company) = canonical.key
          AND c.company != canonical.name
    """)


def downgrade() -> None:
    # Tags were already mixed-case; no way to restore original casing.
    pass
