"""add bcc_hash column to contacts

Revision ID: cc17c1c24d03
Revises: 7dc4816df9bf
Create Date: 2026-03-26 12:10:42.813648

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'cc17c1c24d03'
down_revision: Union[str, None] = '7dc4816df9bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('bcc_hash', sa.String(length=8), nullable=True))
    op.create_index(op.f('ix_contacts_bcc_hash'), 'contacts', ['bcc_hash'], unique=False)

    # Backfill bcc_hash for existing contacts using first 7 chars of md5(id::text)
    op.execute("""
        UPDATE contacts
        SET bcc_hash = LEFT(MD5(id::text || user_id::text), 7)
        WHERE bcc_hash IS NULL
    """)


def downgrade() -> None:
    op.drop_index(op.f('ix_contacts_bcc_hash'), table_name='contacts')
    op.drop_column('contacts', 'bcc_hash')
