"""add mcp_api_key_hash column to users

Revision ID: 7dc4816df9bf
Revises: a1b2c3d4e5f8
Create Date: 2026-03-25 12:27:47.456742

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7dc4816df9bf'
down_revision: Union[str, None] = 'a1b2c3d4e5f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('mcp_api_key_hash', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'mcp_api_key_hash')
