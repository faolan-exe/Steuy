"""lieferschein

Revision ID: 7c3e91a4b2d8
Revises: 5ac20c87b9ac
Create Date: 2026-10-23 22:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c3e91a4b2d8'
down_revision = '5ac20c87b9ac'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "rechnung",
        "belegart",
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="rechnung",
    )
    op.drop_constraint("rechnung_belegart", "rechnung", type_="check")
    op.create_check_constraint(
        "rechnung_belegart",
        "rechnung",
        "belegart IN ('rechnung', 'angebot', 'korrektur', 'lieferschein')",
    )
    op.create_check_constraint(
        "rechnung_lieferschein_bezug",
        "rechnung",
        "belegart <> 'lieferschein' OR bezug_id IS NOT NULL",
    )
    op.execute(
        "INSERT INTO nummernkreis (belegart, praefix, stellen, naechste_nummer) "
        "VALUES ('lieferschein', 'LS', 4, 1)"
    )


def downgrade():
    # Schlägt fehl, solange es Lieferscheine gibt: finalisierte Belege sind unveränderlich.
    op.execute("DELETE FROM nummernkreis WHERE belegart = 'lieferschein'")
    op.drop_constraint("rechnung_lieferschein_bezug", "rechnung", type_="check")
    op.drop_constraint("rechnung_belegart", "rechnung", type_="check")
    op.create_check_constraint(
        "rechnung_belegart", "rechnung", "belegart IN ('rechnung', 'angebot', 'korrektur')"
    )
    op.alter_column(
        "rechnung",
        "belegart",
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
        existing_server_default="rechnung",
    )
