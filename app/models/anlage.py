from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Anlagegut(db.Model):
    """Anschaffung, die über mehrere Jahre abgeschrieben wird. Unveränderlich (DB-Trigger);
    falsch angelegt heißt: die zugehörige Buchung stornieren."""

    __tablename__ = "anlagegut"
    __table_args__ = (
        CheckConstraint(
            "art IN ('computer', 'software', 'beweglich', 'immateriell')", name="anlagegut_art"
        ),
        CheckConstraint("anschaffungskosten_cent > 0", name="anlagegut_kosten"),
        CheckConstraint("nutzungsdauer_jahre BETWEEN 1 AND 50", name="anlagegut_dauer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    buchung_id: Mapped[int] = mapped_column(
        ForeignKey("buchung.id", ondelete="RESTRICT"), unique=True
    )
    bezeichnung: Mapped[str] = mapped_column(String(200))
    art: Mapped[str] = mapped_column(String(15))
    anschaffungsdatum: Mapped[date] = mapped_column(Date)
    anschaffungskosten_cent: Mapped[int] = mapped_column(BigInteger)
    nutzungsdauer_jahre: Mapped[int] = mapped_column(Integer)
    erstellt_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    buchung = relationship("Buchung")

    @property
    def aktiv(self) -> bool:
        """Eine stornierte Buchung hebt auch das Anlagegut auf."""
        return not self.buchung.storniert


class AfaVorgabe(db.Model):
    """GWG-Grenze je Steuerjahr (netto). Als Daten, weil sie sich ändern kann."""

    __tablename__ = "afa_vorgabe"

    steuerjahr: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    gwg_netto_cent: Mapped[int] = mapped_column(BigInteger)


class Nutzungsdauer(db.Model):
    """Vorschläge aus der amtlichen AfA-Tabelle für allgemein verwendbare Anlagegüter."""

    __tablename__ = "nutzungsdauer"

    id: Mapped[int] = mapped_column(primary_key=True)
    bezeichnung: Mapped[str] = mapped_column(String(120), unique=True)
    jahre: Mapped[int] = mapped_column(Integer)
    quelle: Mapped[str] = mapped_column(String(200))
