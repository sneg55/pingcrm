"""Add telegram_bio to contacts

Revision ID: c4e2d5f7a012
Revises: b3f1a2c8e901
Create Date: 2026-03-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e2d5f7a012'
down_revision: Union[str, None] = 'b3f1a2c8e901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('telegram_bio', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'telegram_bio')
