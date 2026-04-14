"""add bird cookie columns to users

Revision ID: 5fcb77520fec
Revises: ad8670aa51dd
Create Date: 2026-04-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "5fcb77520fec"
down_revision = "ad8670aa51dd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("twitter_bird_auth_token", sa.String(), nullable=True))
    op.add_column("users", sa.Column("twitter_bird_ct0", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "twitter_bird_status",
            sa.String(length=16),
            nullable=False,
            server_default="disconnected",
        ),
    )
    op.add_column(
        "users",
        sa.Column("twitter_bird_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "twitter_bird_checked_at")
    op.drop_column("users", "twitter_bird_status")
    op.drop_column("users", "twitter_bird_ct0")
    op.drop_column("users", "twitter_bird_auth_token")
