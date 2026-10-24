from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.euer import Zeile
from app.extensions import db


class EuerZeile(db.Model):
    """Zeile der Anlage EÜR in einem Steuerjahr (aus dem amtlichen Vordruck)."""

    __tablename__ = "euer_zeile"
    __table_args__ = (CheckConstraint("art IN ('einnahme', 'ausgabe')", name="euer_zeile_art"),)

    steuerjahr: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    zeile: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    kennzahl: Mapped[str | None] = mapped_column(String(5))
    bezeichnung: Mapped[str] = mapped_column(String(300))
    art: Mapped[str] = mapped_column(String(10))

    def als_zeile(self) -> Zeile:
        return Zeile(self.zeile, self.kennzahl, self.bezeichnung, self.art)


class EuerZuordnung(db.Model):
    """Welche Kategorie in welchem Steuerjahr in welche Zeile gehört.

    kategorie_id NULL steht für Zahlungen zu Ausgangsrechnungen.
    """

    __tablename__ = "euer_zuordnung"
    __table_args__ = (
        UniqueConstraint(
            "steuerjahr",
            "kategorie_id",
            name="euer_zuordnung_einmal",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["steuerjahr", "zeile"], ["euer_zeile.steuerjahr", "euer_zeile.zeile"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    steuerjahr: Mapped[int] = mapped_column(Integer)
    kategorie_id: Mapped[int | None] = mapped_column(ForeignKey("kategorie.id"))
    zeile: Mapped[int] = mapped_column(Integer)


class EuerSummen(db.Model):
    """Zeilen und Kennzahlen der Summen und der Gewinnermittlung je Steuerjahr.

    Auch sie verschieben sich mit dem Vordruck (2025: Summe Ausgaben in Zeile 75, 2026: Zeile 76),
    deshalb stehen sie als Daten hier und nicht im Text der Auswertung.
    """

    __tablename__ = "euer_summen"

    steuerjahr: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    einnahmen_zeile: Mapped[int] = mapped_column(Integer)
    einnahmen_kz: Mapped[str] = mapped_column(String(5))
    ausgaben_zeile: Mapped[int] = mapped_column(Integer)
    ausgaben_kz: Mapped[str] = mapped_column(String(5))
    # Gewinn = Einnahmen (Übertrag) abzüglich Ausgaben (Übertrag)
    gewinn_einnahmen_zeile: Mapped[int] = mapped_column(Integer)
    gewinn_ausgaben_zeile: Mapped[int] = mapped_column(Integer)
