"""Shared DDL for Postgres triggers used by both alembic migrations and tests."""
from __future__ import annotations

CLEAR_2ND_TIER_FUNCTION = """
CREATE OR REPLACE FUNCTION clear_2nd_tier_on_interaction() RETURNS trigger AS $$
BEGIN
    UPDATE contacts
    SET tags = array_remove(array_remove(tags, '2nd tier'), '2nd Tier')
    WHERE id = NEW.contact_id
      AND (tags @> ARRAY['2nd tier']::varchar[]
           OR tags @> ARRAY['2nd Tier']::varchar[]);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CLEAR_2ND_TIER_TRIGGER = """
CREATE TRIGGER trg_clear_2nd_tier_on_interaction
AFTER INSERT ON interactions
FOR EACH ROW EXECUTE FUNCTION clear_2nd_tier_on_interaction();
"""

DROP_CLEAR_2ND_TIER = """
DROP TRIGGER IF EXISTS trg_clear_2nd_tier_on_interaction ON interactions;
DROP FUNCTION IF EXISTS clear_2nd_tier_on_interaction();
"""
