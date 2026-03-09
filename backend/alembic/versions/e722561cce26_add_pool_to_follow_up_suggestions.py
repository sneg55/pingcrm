"""add_pool_to_follow_up_suggestions

Revision ID: e722561cce26
Revises: d6e7f8a1b2c3
Create Date: 2026-03-09 08:06:40.954727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e722561cce26'
down_revision: Union[str, None] = 'd6e7f8a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('follow_up_suggestions', sa.Column('pool', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('follow_up_suggestions', 'pool')
