"""rename priority_level normal to medium + add cascade to extension_pairings FK

Revision ID: a1b2c3d4e5f8
Revises: f0a1b2c3d4e5
Create Date: 2026-03-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f8'
down_revision: Union[str, None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename "normal" to "medium" in contacts.priority_level
    op.execute("UPDATE contacts SET priority_level = 'medium' WHERE priority_level = 'normal'")

    # Add ON DELETE CASCADE to extension_pairings.user_id FK
    op.drop_constraint('extension_pairings_user_id_fkey', 'extension_pairings', type_='foreignkey')
    op.create_foreign_key(
        'extension_pairings_user_id_fkey',
        'extension_pairings', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('extension_pairings_user_id_fkey', 'extension_pairings', type_='foreignkey')
    op.create_foreign_key(
        'extension_pairings_user_id_fkey',
        'extension_pairings', 'users',
        ['user_id'], ['id'],
    )
    op.execute("UPDATE contacts SET priority_level = 'normal' WHERE priority_level = 'medium'")
