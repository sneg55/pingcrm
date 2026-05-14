"""remove_meta_sidebar_interactions

Delete Interaction rows that were synthesized from Messenger/Instagram sidebar
scrapes. The sidebar exposes no real message ID and no real timestamp, and for
E2EE chats it shows a "secured with end-to-end encryption" banner instead of
real preview text. Those rows were created with bogus `occurred_at = now()` and
content equal to the system banner, producing daily duplicates per contact.

The extension is being changed in the same release to stop synthesizing these
rows; this migration scrubs the rows that already accumulated.

Revision ID: a7b8c9d0e1f2
Revises: 7c3eb9916e93
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = '7c3eb9916e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Stash the contact_ids whose stats will need recomputing.
    op.execute("""
        CREATE TEMP TABLE _sidebar_affected_contacts ON COMMIT DROP AS
        SELECT DISTINCT contact_id
        FROM interactions
        WHERE raw_reference_id LIKE 'facebook:fb_sidebar_%'
           OR raw_reference_id LIKE 'instagram:ig_sidebar_%'
    """)

    # 2. Delete the synthetic rows.
    op.execute("""
        DELETE FROM interactions
        WHERE raw_reference_id LIKE 'facebook:fb_sidebar_%'
           OR raw_reference_id LIKE 'instagram:ig_sidebar_%'
    """)

    # 3. Recompute interaction_count and last_interaction_at for each affected
    #    contact. If the contact had no other interactions, count becomes 0 and
    #    last_interaction_at becomes NULL.
    op.execute("""
        UPDATE contacts c
        SET interaction_count = sub.cnt,
            last_interaction_at = sub.last_at
        FROM (
            SELECT a.contact_id,
                   COUNT(i.id) AS cnt,
                   MAX(i.occurred_at) AS last_at
            FROM _sidebar_affected_contacts a
            LEFT JOIN interactions i ON i.contact_id = a.contact_id
            GROUP BY a.contact_id
        ) sub
        WHERE c.id = sub.contact_id
    """)


def downgrade() -> None:
    # The deleted rows were synthetic placeholders, not real messages. There
    # is nothing to restore.
    pass
