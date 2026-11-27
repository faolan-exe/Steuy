"""Mahnwesen: Standardtexte drohen Verzugskosten an, Platzhalter für die Verzugspauschale

Revision ID: e8a2c4f6b937
Revises: d7f1b3a9e625
Create Date: 2026-11-27 16:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "e8a2c4f6b937"
down_revision = "d7f1b3a9e625"
branch_labels = None
depends_on = None

ALT = {
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

NEU = {
    1: (
        'Guten Tag,\n\nsicher ist es Ihnen im Alltag nur entgangen: Für die '
        'Rechnung {nummer} vom {rechnungsdatum} habe ich noch keinen '
        'Zahlungseingang festgestellt. Sie war am {faellig} fällig.\n\nBitte '
        'überweisen Sie den offenen Betrag von {betrag} bis zum {frist}.\n\nBitte '
        'beachten Sie: Geht die Zahlung bis dahin nicht ein, muss ich Ihnen mit '
        'der nächsten Mahnung Verzugskosten in Rechnung stellen, also die '
        'gesetzliche Verzugspauschale von 40,00 € und Verzugszinsen.'
    ),
    2: (
        'Guten Tag,\n\ntrotz meiner Zahlungserinnerung ist die Rechnung {nummer} '
        'vom {rechnungsdatum} noch offen. Sie war am {faellig} fällig, Sie '
        'befinden sich damit in Zahlungsverzug.\n\n{pauschale}\n\nBitte überweisen '
        'Sie den Gesamtbetrag von {gesamt} bis spätestens {frist}. Geht bis '
        'dahin keine Zahlung ein, entstehen Ihnen weitere Kosten: Ich berechne '
        'Verzugszinsen und mahne erneut.'
    ),
    3: (
        'Guten Tag,\n\ntrotz Zahlungserinnerung und Mahnung habe ich zur Rechnung '
        '{nummer} vom {rechnungsdatum} noch keine vollständige Zahlung '
        'erhalten. Dies ist meine letzte Mahnung.\n\n{pauschale}\n\nBitte '
        'überweisen Sie den Gesamtbetrag von {gesamt} bis spätestens {frist}. '
        'Geht das Geld bis dahin nicht ein, leite ich ohne weitere Ankündigung '
        'ein gerichtliches Mahnverfahren ein. Die Kosten dafür und die '
        'Verzugszinsen gehen zu Ihren Lasten.\n\nGibt es einen Grund, warum Sie '
        'noch nicht zahlen konnten, melden Sie sich bitte vorher bei mir.'
    ),
}


def _tausche(von: dict, nach: dict) -> None:
    """Nur unveränderte Standardtexte. Eigene Texte bleiben, wie sie sind."""
    for nummer in (1, 2, 3):
        op.execute(
            sa.text("UPDATE mahnstufe SET text = :nach WHERE nummer = :nummer AND text = :von")
            .bindparams(von=von[nummer], nach=nach[nummer], nummer=nummer)
        )


def upgrade():
    _tausche(ALT, NEU)


def downgrade():
    _tausche(NEU, ALT)
