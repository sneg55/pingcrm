"""add telegram_user_id to contacts

Revision ID: f1a2b3c4d5e6
Revises: e560dad1f440
Create Date: 2026-03-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e560dad1f440'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('telegram_user_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'telegram_user_id')
