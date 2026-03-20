"""add twitter_dm_cursor to users

Revision ID: dc46fcbffa66
Revises: e5a6b7c8d9f0
Create Date: 2026-03-20 17:59:34.619275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'dc46fcbffa66'
down_revision: Union[str, None] = 'e5a6b7c8d9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('twitter_dm_cursor', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'twitter_dm_cursor')
