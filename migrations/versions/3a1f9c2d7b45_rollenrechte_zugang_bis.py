"""rollenrechte und zugang_bis

Revision ID: 3a1f9c2d7b45
Revises: 12bce76f87ac
Create Date: 2026-10-21 19:05:00

"""

import sqlalchemy as sa
from alembic import op

revision = "3a1f9c2d7b45"
down_revision = "12bce76f87ac"
branch_labels = None
depends_on = None

# Standardrechte laut docs/domain/rollen.md, Stand dieser Migration. Bewusst nicht aus dem
# App-Code importiert, damit die Migration auch nach späteren Codeänderungen gleich bleibt.
STANDARD = {
    "buchhalter": [
        "belege",
        "stammdaten",
        "entwuerfe",
        "rechnungen_versenden",
        "zahlungen",
        "buchen",
        "auswertungen",
        "export",
        "protokoll",
    ],
    "mitarbeiter": ["belege", "stammdaten", "entwuerfe"],
    "steuerberater": ["auswertungen", "export", "protokoll"],
}


def upgrade():
    op.add_column("nutzer", sa.Column("zugang_bis", sa.Date(), nullable=True))
    tabelle = op.create_table(
        "rollenrecht",
        sa.Column("rolle", sa.String(length=20), nullable=False),
        sa.Column("recht", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "rolle IN ('buchhalter', 'mitarbeiter', 'steuerberater')",
            name="rollenrecht_rolle_einstellbar",
        ),
        sa.PrimaryKeyConstraint("rolle", "recht"),
    )
    op.bulk_insert(
        tabelle,
        [{"rolle": rolle, "recht": recht} for rolle, rechte in STANDARD.items() for recht in rechte],
    )


def downgrade():
    op.drop_table("rollenrecht")
    op.drop_column("nutzer", "zugang_bis")
