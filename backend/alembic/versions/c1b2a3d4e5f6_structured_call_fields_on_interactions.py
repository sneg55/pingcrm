"""add structured call_type and duration_seconds to interactions

Adds two nullable columns so phone/video call events can be represented as
structured data instead of a prefixed `content_preview` string. Backfills
existing rows that have a `"Phone call"` or `"Video call"` prefix and clears
their `content_preview` so the frontend renders them via the structured path.

Revision ID: c1b2a3d4e5f6
Revises: a7b8c9d0e1f2
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1b2a3d4e5f6'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('interactions', sa.Column('call_type', sa.String(length=16), nullable=True))
    op.add_column('interactions', sa.Column('duration_seconds', sa.Integer(), nullable=True))

    op.execute("""
        UPDATE interactions
        SET call_type = 'phone',
            duration_seconds = NULLIF(substring(content_preview from '\\((\\d+)s\\)'), '')::int,
            content_preview = NULL
        WHERE content_preview LIKE 'Phone call%'
    """)
    op.execute("""
        UPDATE interactions
        SET call_type = 'video',
            duration_seconds = NULLIF(substring(content_preview from '\\((\\d+)s\\)'), '')::int,
            content_preview = NULL
        WHERE content_preview LIKE 'Video call%'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE interactions
        SET content_preview = CASE
            WHEN call_type = 'phone' AND duration_seconds IS NOT NULL
                THEN 'Phone call (' || duration_seconds || 's)'
            WHEN call_type = 'phone'
                THEN 'Phone call'
            WHEN call_type = 'video' AND duration_seconds IS NOT NULL
                THEN 'Video call (' || duration_seconds || 's)'
            WHEN call_type = 'video'
                THEN 'Video call'
            ELSE content_preview
        END
        WHERE call_type IS NOT NULL
    """)
    op.drop_column('interactions', 'duration_seconds')
    op.drop_column('interactions', 'call_type')
