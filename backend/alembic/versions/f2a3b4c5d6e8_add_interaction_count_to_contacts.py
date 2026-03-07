"""Add interaction_count to contacts

Revision ID: f2a3b4c5d6e8
Revises: e2f3a4b5c6d7
Create Date: 2026-03-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("interaction_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        "UPDATE contacts c SET interaction_count = "
        "(SELECT COUNT(*) FROM interactions i WHERE i.contact_id = c.id)"
    )
    op.create_index("ix_contacts_interaction_count", "contacts", ["interaction_count"])


def downgrade() -> None:
    op.drop_index("ix_contacts_interaction_count", table_name="contacts")
    op.drop_column("contacts", "interaction_count")
