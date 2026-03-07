"""add google_accounts table

Revision ID: e560dad1f440
Revises: c4e2d5f7a012
Create Date: 2026-03-06 06:40:45.253692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e560dad1f440'
down_revision: Union[str, None] = 'c4e2d5f7a012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'google_accounts',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('refresh_token', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('google_accounts')
