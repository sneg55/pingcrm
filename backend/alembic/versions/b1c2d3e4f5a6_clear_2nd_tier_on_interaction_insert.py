"""clear 2nd tier tag when an interaction is inserted

Revision ID: b1c2d3e4f5a6
Revises: 5fcb77520fec
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op

from app.models._triggers import (
    CLEAR_2ND_TIER_FUNCTION,
    CLEAR_2ND_TIER_TRIGGER,
    DROP_CLEAR_2ND_TIER,
)

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "5fcb77520fec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(CLEAR_2ND_TIER_FUNCTION)
    op.execute(CLEAR_2ND_TIER_TRIGGER)


def downgrade() -> None:
    op.execute(DROP_CLEAR_2ND_TIER)
