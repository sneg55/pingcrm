"""add contact coordinates

Revision ID: b7c8d9e0f1a2
Revises: b1c2d3e4f5a6
Create Date: 2026-04-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("contacts", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("contacts", sa.Column("geocoded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contacts", sa.Column("geocoded_location", sa.String(), nullable=True))
    op.create_index(
        "ix_contacts_user_latlng",
        "contacts",
        ["user_id", "latitude", "longitude"],
    )


def downgrade() -> None:
    op.drop_index("ix_contacts_user_latlng", table_name="contacts")
    op.drop_column("contacts", "geocoded_location")
    op.drop_column("contacts", "geocoded_at")
    op.drop_column("contacts", "longitude")
    op.drop_column("contacts", "latitude")
