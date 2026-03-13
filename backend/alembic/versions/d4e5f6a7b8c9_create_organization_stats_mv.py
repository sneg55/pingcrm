"""create_organization_stats_mv

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-13 16:03:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE MATERIALIZED VIEW organization_stats_mv AS
        SELECT
            c.organization_id,
            COUNT(*)::int AS contact_count,
            ROUND(AVG(c.relationship_score))::int AS avg_relationship_score,
            COALESCE(SUM(c.interaction_count), 0)::int AS total_interactions,
            MAX(c.last_interaction_at) AS last_interaction_at
        FROM contacts c
        WHERE c.organization_id IS NOT NULL
          AND c.priority_level != 'archived'
        GROUP BY c.organization_id
    """)
    op.execute(
        "CREATE UNIQUE INDEX ix_org_stats_mv_org_id "
        "ON organization_stats_mv (organization_id)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS organization_stats_mv")
