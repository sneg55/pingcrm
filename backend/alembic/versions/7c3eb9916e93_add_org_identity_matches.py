"""add org_identity_matches

Revision ID: 7c3eb9916e93
Revises: e0f1a2b3c4d5
Create Date: 2026-05-13 11:34:58.036757

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7c3eb9916e93'
down_revision: Union[str, None] = 'e0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_identity_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_a_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_b_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_score", sa.Float, nullable=False),
        sa.Column("match_method", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_org_identity_matches_user_id",
        "org_identity_matches",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_org_identity_matches_user_pair",
        "org_identity_matches",
        [sa.text("user_id"), sa.text("LEAST(org_a_id, org_b_id)"), sa.text("GREATEST(org_a_id, org_b_id)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_org_identity_matches_user_pair", table_name="org_identity_matches")
    op.drop_index("ix_org_identity_matches_user_id", table_name="org_identity_matches")
    op.drop_table("org_identity_matches")
