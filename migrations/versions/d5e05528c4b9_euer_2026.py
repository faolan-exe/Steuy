"""euer_2026

Revision ID: d5e05528c4b9
Revises: 4a5afb1d92cc
Create Date: 2026-10-22 16:08:32.759395

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e05528c4b9'
down_revision = '4a5afb1d92cc'
branch_labels = None
depends_on = None


# Anlage EÜR 2026, amtlicher Vordruck (BMF-Schreiben vom 01.09.2026). Gegenüber 2025 ist bei
# den Betriebsausgaben eine Zeile hinzugekommen (Rücklage Tierbewertung, Zeile 27), deshalb
# verschieben sich die Ausgabenzeilen ab „Waren“ um eins. Kennzahlen sind unverändert.
ZEILEN = [
    (12, "111", "Betriebseinnahmen als umsatzsteuerlicher Kleinunternehmer (nach § 19 Abs. 1 UStG)", "einnahme"),
    (29, "100", "Waren, Rohstoffe und Hilfsstoffe einschließlich der Nebenkosten", "ausgabe"),
    (30, "110", "Bezogene Fremdleistungen", "ausgabe"),
    (33, "131", "AfA auf immaterielle Wirtschaftsgüter", "ausgabe"),
    (34, "130", "AfA auf bewegliche Wirtschaftsgüter", "ausgabe"),
    (37, "132", "Aufwendungen für geringwertige Wirtschaftsgüter nach § 6 Abs. 2 EStG", "ausgabe"),
    (40, "150", "Miete/Pacht für Geschäftsräume und betrieblich genutzte Grundstücke", "ausgabe"),
    (44, "280", "Aufwendungen für Telekommunikation (z. B. Telefon, Internet)", "ausgabe"),
    (45, "221", "Übernachtungs- und Reisenebenkosten bei Geschäftsreisen des Steuerpflichtigen", "ausgabe"),
    (46, "281", "Fortbildungskosten (ohne Reisekosten)", "ausgabe"),
    (50, "223", "Beiträge, Gebühren, Abgaben und Versicherungen (ohne solche für Gebäude und Kfz)", "ausgabe"),
    (51, "228", "Laufende EDV-Kosten (z. B. Beratung, Wartung, Reparatur)", "ausgabe"),
    (52, "229", "Arbeitsmittel (z. B. Bürobedarf, Porto, Fachliteratur)", "ausgabe"),
    (55, "224", "Werbekosten (z. B. Inserate, Werbespots, Plakate)", "ausgabe"),
    (61, "183", "Übrige unbeschränkt abziehbare Betriebsausgaben", "ausgabe"),
    (71, "146", "Sonstige tatsächliche Fahrtkosten ohne AfA und Zinsen (z. B. Reparaturen, Wartungen, Treibstoff, öffentliche Verkehrsmittel)", "ausgabe"),
]

# Gleiche fachliche Zuordnung wie 2025, nur mit den neuen Zeilennummern
ZUORDNUNG = {
    None: 12,  # Zahlungen zu Ausgangsrechnungen
    "Umsatzerlöse": 12,
    "Sonstige Einnahmen": 12,
    "Waren und Material": 29,
    "Fremdleistungen": 30,
    "Büromaterial": 52,
    "Software und Abos": 51,
    "Telefon und Internet": 44,
    "Werbung": 55,
    "Reisekosten": 45,
    "Fahrzeugkosten": 71,
    "Fortbildung": 46,
    "Miete und Raumkosten": 40,
    "Versicherungen und Beiträge": 50,
    "Gebühren": 61,
    "Geringwertige Anschaffungen": 37,
    "Sonstige Ausgaben": 61,
}


def upgrade():
    op.bulk_insert(
        sa.table(
            "euer_zeile",
            sa.column("steuerjahr", sa.Integer),
            sa.column("zeile", sa.Integer),
            sa.column("kennzahl", sa.String),
            sa.column("bezeichnung", sa.String),
            sa.column("art", sa.String),
        ),
        [
            {"steuerjahr": 2026, "zeile": z, "kennzahl": kz, "bezeichnung": text, "art": art}
            for z, kz, text, art in ZEILEN
        ],
    )
    verbindung = op.get_bind()
    for name, zeile in ZUORDNUNG.items():
        kategorie_id = None
        if name is not None:
            kategorie_id = verbindung.execute(
                sa.text("SELECT id FROM kategorie WHERE name = :n"), {"n": name}
            ).scalar()
            if kategorie_id is None:
                continue
        verbindung.execute(
            sa.text(
                "INSERT INTO euer_zuordnung (steuerjahr, kategorie_id, zeile) VALUES (2026, :k, :z)"
            ),
            {"k": kategorie_id, "z": zeile},
        )


def downgrade():
    op.execute("DELETE FROM euer_zuordnung WHERE steuerjahr = 2026")
    op.execute("DELETE FROM euer_zeile WHERE steuerjahr = 2026")
