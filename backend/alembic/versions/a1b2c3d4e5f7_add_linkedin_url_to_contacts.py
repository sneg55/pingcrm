"""Add linkedin_url to contacts

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("linkedin_url", sa.String(), nullable=True))
    # Migrate existing LinkedIn URLs from notes field
    op.execute("""
        UPDATE contacts
        SET linkedin_url = substring(notes FROM 'LinkedIn: (https://[^ ]+)'),
            notes = NULL
        WHERE notes LIKE 'LinkedIn: https://%'
        AND linkedin_url IS NULL
    """)


def downgrade() -> None:
    op.drop_column("contacts", "linkedin_url")
