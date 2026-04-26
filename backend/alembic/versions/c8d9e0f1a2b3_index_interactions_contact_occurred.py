"""index interactions by contact_id, occurred_at desc

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-04-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_interactions_contact_occurred_desc",
        "interactions",
        ["contact_id", sa.text("occurred_at DESC")],
    )
    op.drop_index("ix_interactions_contact_id", table_name="interactions")


def downgrade() -> None:
    op.create_index(
        "ix_interactions_contact_id",
        "interactions",
        ["contact_id"],
    )
    op.drop_index(
        "ix_interactions_contact_occurred_desc",
        table_name="interactions",
    )
