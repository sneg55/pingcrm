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
    # Normalize all tags to lowercase and deduplicate within each contact.
    # Uses a PostgreSQL subquery to:
    # 1. unnest the tags array
    # 2. lower() each tag
    # 3. select distinct to remove case-duplicates
    # 4. re-aggregate into an array
    op.execute("""
        UPDATE contacts
        SET tags = (
            SELECT COALESCE(array_agg(DISTINCT lower(tag)), '{}')
            FROM unnest(tags) AS tag
        )
        WHERE tags IS NOT NULL AND array_length(tags, 1) > 0
    """)


def downgrade() -> None:
    # Tags were already mixed-case; no way to restore original casing.
    pass
