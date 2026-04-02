"""add telegram_last_seen_at to contacts

Revision ID: 29efdb088152
Revises: cc17c1c24d03
Create Date: 2026-04-02 06:55:00.173151

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29efdb088152'
down_revision: Union[str, None] = 'cc17c1c24d03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('telegram_last_seen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'telegram_last_seen_at')
