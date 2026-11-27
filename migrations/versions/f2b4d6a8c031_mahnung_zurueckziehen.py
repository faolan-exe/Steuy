"""Mahnungen löschen (nie verschickt) oder zurückziehen (verschickt)

Revision ID: f2b4d6a8c031
Revises: e8a2c4f6b937
Create Date: 2026-11-27 17:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "f2b4d6a8c031"
down_revision = "e8a2c4f6b937"
branch_labels = None
depends_on = None

ALTER_SCHUTZ = """
    CREATE OR REPLACE FUNCTION mahnung_schuetzen() RETURNS trigger AS $$
    BEGIN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN
            RAISE EXCEPTION 'Mahnungen sind unveränderlich';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM rechnung WHERE id = NEW.rechnung_id AND finalisiert_am IS NOT NULL
        ) THEN
            RAISE EXCEPTION 'Mahnungen nur zu finalisierten Rechnungen';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
"""

# Inhalt bleibt unveränderlich. Erlaubt: einmal zurückziehen (nur die drei Felder) und löschen,
# solange es keinen Versand(-versuch) gibt.
NEUER_SCHUTZ = """
    CREATE OR REPLACE FUNCTION mahnung_schuetzen() RETURNS trigger AS $$
    DECLARE
        felder text[] := ARRAY['zurueckgezogen_am', 'zurueckgezogen_von', 'zurueckgezogen_grund'];
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF EXISTS (SELECT 1 FROM versand WHERE mahnung_id = OLD.id) THEN
                RAISE EXCEPTION 'Verschickte Mahnungen sind unveränderlich und nicht löschbar';
            END IF;
            RETURN OLD;
        END IF;
        IF TG_OP = 'UPDATE' THEN
            IF OLD.zurueckgezogen_am IS NOT NULL OR NEW.zurueckgezogen_am IS NULL
               OR (to_jsonb(NEW) - felder) IS DISTINCT FROM (to_jsonb(OLD) - felder) THEN
                RAISE EXCEPTION 'Mahnungen sind unveränderlich';
            END IF;
            RETURN NEW;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM rechnung WHERE id = NEW.rechnung_id AND finalisiert_am IS NOT NULL
        ) THEN
            RAISE EXCEPTION 'Mahnungen nur zu finalisierten Rechnungen';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
"""


def upgrade():
    op.add_column("mahnung", sa.Column("zurueckgezogen_am", sa.DateTime(timezone=True)))
    op.add_column("mahnung", sa.Column("zurueckgezogen_von", sa.Integer()))
    op.add_column("mahnung", sa.Column("zurueckgezogen_grund", sa.String(length=200)))
    op.create_foreign_key(
        "mahnung_zurueckgezogen_von_fkey", "mahnung", "nutzer", ["zurueckgezogen_von"], ["id"]
    )
    # Eine zurückgezogene Stufe darf neu erstellt werden
    op.drop_constraint("mahnung_stufe_einmal", "mahnung", type_="unique")
    op.create_index(
        "mahnung_stufe_einmal",
        "mahnung",
        ["rechnung_id", "stufe"],
        unique=True,
        postgresql_where=sa.text("zurueckgezogen_am IS NULL"),
    )
    op.execute(NEUER_SCHUTZ)


def downgrade():
    op.execute(ALTER_SCHUTZ)
    op.drop_index("mahnung_stufe_einmal", table_name="mahnung")
    op.create_unique_constraint("mahnung_stufe_einmal", "mahnung", ["rechnung_id", "stufe"])
    op.drop_constraint("mahnung_zurueckgezogen_von_fkey", "mahnung", type_="foreignkey")
    op.drop_column("mahnung", "zurueckgezogen_grund")
    op.drop_column("mahnung", "zurueckgezogen_von")
    op.drop_column("mahnung", "zurueckgezogen_am")
