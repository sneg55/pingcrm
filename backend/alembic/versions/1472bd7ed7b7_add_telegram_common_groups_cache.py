"""add_telegram_common_groups_cache

Revision ID: 1472bd7ed7b7
Revises: b2c3d4e5f6a8
Create Date: 2026-03-06 16:03:41.774188

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1472bd7ed7b7'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('telegram_common_groups', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('contacts', sa.Column('telegram_groups_fetched_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'telegram_groups_fetched_at')
    op.drop_column('contacts', 'telegram_common_groups')
