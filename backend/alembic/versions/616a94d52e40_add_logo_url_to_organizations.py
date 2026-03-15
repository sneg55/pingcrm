"""add_logo_url_to_organizations

Revision ID: 616a94d52e40
Revises: e5f6a7b8c9d0
Create Date: 2026-03-15 06:45:01.317184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '616a94d52e40'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('logo_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'logo_url')
