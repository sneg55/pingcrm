"""stub: accidentally created, no-op placeholder before bird cookies migration

This file was created in error. It is a no-op placeholder that allows the
real migration (5fcb77520fec) to slot into the chain.

Revision ID: 33a179132a25
Revises: ad8670aa51dd
Create Date: 2026-04-14
"""
from __future__ import annotations

from alembic import op


revision = "33a179132a25"
down_revision = "ad8670aa51dd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
