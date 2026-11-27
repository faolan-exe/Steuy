"""Mahnwesen: Text der Zahlungserinnerung passt auch nach einer Teilzahlung

Revision ID: a9c1e3f5d702
Revises: f2b4d6a8c031
Create Date: 2026-11-27 18:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "a9c1e3f5d702"
down_revision = "f2b4d6a8c031"
branch_labels = None
depends_on = None

ALT = (
    'Guten Tag,\n\nsicher ist es Ihnen im Alltag nur entgangen: Für die '
    'Rechnung {nummer} vom {rechnungsdatum} habe ich noch keinen '
    'Zahlungseingang festgestellt. Sie war am {faellig} fällig.\n\nBitte '
    'überweisen Sie den offenen Betrag von {betrag} bis zum {frist}.\n\nBitte '
    'beachten Sie: Geht die Zahlung bis dahin nicht ein, muss ich Ihnen mit '
    'der nächsten Mahnung Verzugskosten in Rechnung stellen, also die '
    'gesetzliche Verzugspauschale von 40,00 € und Verzugszinsen.'
)

NEU = (
    'Guten Tag,\n\nsicher ist es Ihnen im Alltag nur entgangen: Für die '
    'Rechnung {nummer} vom {rechnungsdatum} ist noch ein Betrag von '
    '{betrag} offen. Sie war am {faellig} fällig.\n\nBitte überweisen Sie den '
    'offenen Betrag bis zum {frist}.\n\nBitte beachten Sie: Geht die Zahlung '
    'bis dahin nicht ein, muss ich Ihnen mit der nächsten Mahnung '
    'Verzugskosten in Rechnung stellen, also die gesetzliche '
    'Verzugspauschale von 40,00 € und Verzugszinsen.'
)


def _tausche(von: str, nach: str) -> None:
    """Nur der unveränderte Standardtext. Eigene Texte bleiben, wie sie sind."""
    op.execute(
        sa.text("UPDATE mahnstufe SET text = :nach WHERE nummer = 1 AND text = :von").bindparams(
            von=von, nach=nach
        )
    )


def upgrade():
    _tausche(ALT, NEU)


def downgrade():
    _tausche(NEU, ALT)
