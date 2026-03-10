"""Add twitter_user_id to contacts

Revision ID: a8b9c0d1e2f3
Revises: 97d166ac9db2
Create Date: 2026-03-10 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "97d166ac9db2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("twitter_user_id", sa.String(), nullable=True))
    op.create_index("ix_contacts_twitter_user_id", "contacts", ["twitter_user_id"])


def downgrade() -> None:
    op.drop_index("ix_contacts_twitter_user_id", table_name="contacts")
    op.drop_column("contacts", "twitter_user_id")
