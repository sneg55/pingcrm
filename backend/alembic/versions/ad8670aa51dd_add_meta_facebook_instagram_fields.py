"""add meta facebook instagram fields

Revision ID: ad8670aa51dd
Revises: 723492ba17b7
Create Date: 2026-04-10 13:07:37.175482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ad8670aa51dd'
down_revision: Union[str, None] = '723492ba17b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Contact: Facebook/Instagram fields
    op.add_column('contacts', sa.Column('facebook_id', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('facebook_name', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('facebook_avatar_url', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('instagram_id', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('instagram_username', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('instagram_avatar_url', sa.String(), nullable=True))
    op.create_index(op.f('ix_contacts_facebook_id'), 'contacts', ['facebook_id'], unique=False)
    op.create_index(op.f('ix_contacts_instagram_id'), 'contacts', ['instagram_id'], unique=False)

    # Interaction: extra_data JSON column for reactions/read receipts
    op.add_column('interactions', sa.Column('extra_data', postgresql.JSON(astext_type=sa.Text()), nullable=True))

    # User: Meta connection fields
    op.add_column('users', sa.Column('meta_connected', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('meta_connected_name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('meta_sync_facebook', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('meta_sync_instagram', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'meta_sync_instagram')
    op.drop_column('users', 'meta_sync_facebook')
    op.drop_column('users', 'meta_connected_name')
    op.drop_column('users', 'meta_connected')
    op.drop_column('interactions', 'extra_data')
    op.drop_index(op.f('ix_contacts_instagram_id'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_facebook_id'), table_name='contacts')
    op.drop_column('contacts', 'instagram_avatar_url')
    op.drop_column('contacts', 'instagram_username')
    op.drop_column('contacts', 'instagram_id')
    op.drop_column('contacts', 'facebook_avatar_url')
    op.drop_column('contacts', 'facebook_name')
    op.drop_column('contacts', 'facebook_id')
