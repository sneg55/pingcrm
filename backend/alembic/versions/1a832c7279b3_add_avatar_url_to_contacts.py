"""add avatar_url to contacts

Revision ID: 1a832c7279b3
Revises: 1472bd7ed7b7
Create Date: 2026-03-06 20:17:20.918195

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1a832c7279b3'
down_revision: Union[str, None] = '1472bd7ed7b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('avatar_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'avatar_url')
