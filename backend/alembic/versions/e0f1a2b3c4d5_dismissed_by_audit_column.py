"""dismissed_by audit column on follow_up_suggestions

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-05-09

Distinguishes user-driven dismissals from system-driven ones (sync paths
auto-dismissing on new interactions). The 30-day post-dismiss cooldown
in followup_engine.py only makes sense for user dismissals — a system
dismissal triggered by a Telegram backfill arriving 4 hours after a
suggestion was created should not lock the contact out of suggestions
for a month.

Backfill semantics: any row currently in dismiss-cooldown (status='dismissed',
updated_at within the last 60 days) is tagged 'system'. The buggy dismiss
paths were active up until commit 18fa665 (deployed 2026-05-09), so
everything currently in cooldown is overwhelmingly likely to be a system
dismissal. Older dismissed rows (>60d) are left NULL — they're past
cooldown anyway and the distinction doesn't matter.
"""
from alembic import op
import sqlalchemy as sa


revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "follow_up_suggestions",
        sa.Column("dismissed_by", sa.String(length=8), nullable=True),
    )
    # Backfill: rows in cooldown right now were almost certainly system-dismissed.
    op.execute(
        """
        UPDATE follow_up_suggestions
        SET dismissed_by = 'system'
        WHERE status = 'dismissed'
          AND updated_at >= now() - interval '60 days'
          AND dismissed_by IS NULL
        """
    )
    op.create_index(
        "ix_follow_up_suggestions_dismissed_by",
        "follow_up_suggestions",
        ["dismissed_by"],
        postgresql_where=sa.text("dismissed_by IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_follow_up_suggestions_dismissed_by", table_name="follow_up_suggestions")
    op.drop_column("follow_up_suggestions", "dismissed_by")
