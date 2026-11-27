"""Mahnwesen: Verzugspauschale, eigene Textvorlagen, neue Standardtexte mit Anrede

Revision ID: d7f1b3a9e625
Revises: c3d8f1a6b257
Create Date: 2026-11-27 15:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "d7f1b3a9e625"
down_revision = "c3d8f1a6b257"
branch_labels = None
depends_on = None

ANREDE = "Guten Tag,\n\n"

ALT = {
    1: (
        'sicher ist es Ihrer Aufmerksamkeit entgangen: Für die unten genannte '
        'Rechnung haben wir noch keinen Zahlungseingang festgestellt. Bitte '
        'überweisen Sie den offenen Betrag bis zum angegebenen Datum.'
    ),
    2: (
        'leider ist der unten genannte Betrag trotz unserer Zahlungserinnerung '
        'noch offen. Bitte überweisen Sie ihn bis zum angegebenen Datum.'
    ),
    3: (
        'trotz Zahlungserinnerung und Mahnung ist der unten genannte Betrag '
        'weiterhin offen. Bitte überweisen Sie ihn umgehend, spätestens bis zum '
        'angegebenen Datum.'
    ),
}

NEU = {
    1: (
        'Guten Tag,\n\nsicher ist es Ihnen im Alltag nur entgangen: Für die '
        'Rechnung {nummer} vom {rechnungsdatum} habe ich noch keinen '
        'Zahlungseingang festgestellt.\n\nBitte überweisen Sie den offenen Betrag '
        'bis zum {frist}. Vielen Dank!'
    ),
    2: (
        'Guten Tag,\n\ntrotz meiner Zahlungserinnerung ist die Rechnung {nummer} '
        'vom {rechnungsdatum} noch offen. Sie war am {faellig} fällig.\n\nBitte '
        'überweisen Sie den unten genannten Betrag bis spätestens {frist}. Geht '
        'bis dahin keine Zahlung ein, mahne ich erneut und behalte mir vor, '
        'Verzugszinsen zu berechnen.'
    ),
    3: (
        'Guten Tag,\n\ntrotz Zahlungserinnerung und Mahnung habe ich zur Rechnung '
        '{nummer} vom {rechnungsdatum} noch keine vollständige Zahlung '
        'erhalten. Dies ist meine letzte Mahnung.\n\nBitte überweisen Sie den '
        'unten genannten Betrag bis spätestens {frist}. Geht das Geld bis dahin '
        'nicht ein, behalte ich mir ohne weitere Ankündigung rechtliche '
        'Schritte vor, zum Beispiel ein gerichtliches Mahnverfahren. Dadurch '
        'können weitere Kosten für Sie entstehen.\n\nGibt es einen Grund, warum '
        'Sie noch nicht zahlen konnten, melden Sie sich bitte vorher bei mir.'
    ),
}


def upgrade():
    op.add_column(
        "mahnung",
        sa.Column("pauschale_cent", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.create_table(
        "mahnvorlage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    # Unveränderte Standardtexte werden ersetzt. Eigene Texte bleiben und bekommen die Anrede,
    # die bisher fest über dem Text stand.
    for nummer in (1, 2, 3):
        op.execute(
            sa.text(
                "UPDATE mahnstufe SET text = CASE WHEN text = :alt THEN :neu "
                "ELSE :anrede || text END WHERE nummer = :nummer"
            ).bindparams(alt=ALT[nummer], neu=NEU[nummer], anrede=ANREDE, nummer=nummer)
        )


def downgrade():
    for nummer in (1, 2, 3):
        op.execute(
            sa.text(
                "UPDATE mahnstufe SET text = CASE WHEN text = :neu THEN :alt "
                "WHEN starts_with(text, :anrede) THEN substr(text, length(:anrede) + 1) "
                "ELSE text END WHERE nummer = :nummer"
            ).bindparams(alt=ALT[nummer], neu=NEU[nummer], anrede=ANREDE, nummer=nummer)
        )
    op.drop_table("mahnvorlage")
    op.drop_column("mahnung", "pauschale_cent")
