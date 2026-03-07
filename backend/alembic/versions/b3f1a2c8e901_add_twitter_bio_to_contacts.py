"""Add twitter_bio to contacts

Revision ID: b3f1a2c8e901
Revises: aaa04d9b4d92
Create Date: 2026-03-05 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1a2c8e901'
down_revision: Union[str, None] = 'aaa04d9b4d92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('twitter_bio', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'twitter_bio')
