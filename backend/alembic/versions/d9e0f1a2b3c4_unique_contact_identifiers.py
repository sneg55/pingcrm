"""partial unique indexes for twitter and linkedin contact identifiers

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-04-27

Belt-and-suspenders against duplicate contacts on the twitter and linkedin
axes where exact matches are duplicates. App-level prevention lives in
app.services.contact_resolver; these indexes catch anything that bypasses it.

Telegram already has equivalent indexes from prior migrations
(uq_contacts_telegram_user_id_per_user, uq_contacts_telegram_username_per_user).
Email is intentionally not covered: the column is text[] and Postgres can't
directly express "no two rows share any unnest(lower(emails))" — the
resolver's advisory lock is the email guard.

Prereq: existing exact-match duplicates must be merged before this runs.
See backend/scripts/merge_exact_match_dups.py.
"""
from alembic import op


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Normalize empty-string identifiers to NULL so the partial indexes don't
    # try to enforce uniqueness on (user_id, '') groups. Pre-resolver code
    # paths sometimes wrote empty strings instead of NULL.
    op.execute(
        """
        UPDATE contacts SET
            twitter_user_id     = NULLIF(trim(twitter_user_id), ''),
            twitter_handle      = NULLIF(trim(twitter_handle), ''),
            linkedin_profile_id = NULLIF(trim(linkedin_profile_id), '')
        WHERE
            (twitter_user_id IS NOT NULL     AND trim(twitter_user_id) = '')
         OR (twitter_handle IS NOT NULL      AND trim(twitter_handle) = '')
         OR (linkedin_profile_id IS NOT NULL AND trim(linkedin_profile_id) = '')
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_user_twitter_user_id
            ON contacts (user_id, twitter_user_id)
            WHERE twitter_user_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_user_twitter_handle_lower
            ON contacts (user_id, lower(twitter_handle))
            WHERE twitter_handle IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_user_linkedin_profile_id
            ON contacts (user_id, linkedin_profile_id)
            WHERE linkedin_profile_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_contacts_user_twitter_user_id")
    op.execute("DROP INDEX IF EXISTS uq_contacts_user_twitter_handle_lower")
    op.execute("DROP INDEX IF EXISTS uq_contacts_user_linkedin_profile_id")
