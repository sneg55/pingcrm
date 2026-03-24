"""add sync_settings to users

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-03-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, None] = 'e9f0a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('sync_settings', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'sync_settings')
