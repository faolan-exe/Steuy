from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Kategorie(db.Model):
    """Kategorie für Einnahmen und Ausgaben. Zuordnung zur Anlage EÜR folgt je Steuerjahr."""

    __tablename__ = "kategorie"
    __table_args__ = (CheckConstraint("art IN ('einnahme', 'ausgabe')", name="kategorie_art"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    art: Mapped[str] = mapped_column(String(10))
    beschreibung: Mapped[str | None] = mapped_column(Text)
    sortierung: Mapped[int] = mapped_column(Integer, default=0)
    aktiv: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)


class Beleg(db.Model):
    """Hochgeladene Datei. Wird nie gelöscht, nur verworfen (harte Regel 5)."""

    __tablename__ = "beleg"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    dateiname: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(50))
    groesse: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str | None] = mapped_column(Text)
    vorschlag: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    verworfen: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    hochgeladen_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    hochgeladen_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    buchungen: Mapped[list["Buchung"]] = relationship(back_populates="beleg")

    @property
    def verbucht(self) -> bool:
        return any(b.storno_von_id is None for b in self.buchungen)


class Buchung(db.Model):
    """Einnahme oder Ausgabe ohne Ausgangsrechnung. Nach dem Festschreiben unveränderlich."""

    __tablename__ = "buchung"
    __table_args__ = (
        CheckConstraint("art IN ('einnahme', 'ausgabe')", name="buchung_art"),
        CheckConstraint("status IN ('entwurf', 'festgeschrieben')", name="buchung_status"),
        CheckConstraint("betrieblich_prozent BETWEEN 0 AND 100", name="buchung_prozent"),
        CheckConstraint(
            "(storno_von_id IS NULL AND betrag_cent > 0) OR "
            "(storno_von_id IS NOT NULL AND betrag_cent < 0 AND status = 'festgeschrieben')",
            name="buchung_vorzeichen",
        ),
        CheckConstraint(
            "(status = 'entwurf') = (festgeschrieben_am IS NULL)", name="buchung_festschreibung"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    art: Mapped[str] = mapped_column(String(10), default="ausgabe")
    status: Mapped[str] = mapped_column(String(20), default="entwurf")
    beleg_id: Mapped[int | None] = mapped_column(ForeignKey("beleg.id", ondelete="RESTRICT"))
    kontakt_id: Mapped[int | None] = mapped_column(ForeignKey("kontakt.id", ondelete="RESTRICT"))
    partner: Mapped[str | None] = mapped_column(String(200))
    belegdatum: Mapped[date] = mapped_column(Date)
    belegnummer: Mapped[str | None] = mapped_column(String(60))
    beschreibung: Mapped[str | None] = mapped_column(Text)
    kategorie_id: Mapped[int | None] = mapped_column(ForeignKey("kategorie.id"))
    betrag_cent: Mapped[int] = mapped_column(BigInteger)
    betrieblich_prozent: Mapped[int] = mapped_column(Integer, default=100)
    storno_von_id: Mapped[int | None] = mapped_column(
        ForeignKey("buchung.id", ondelete="RESTRICT"), unique=True
    )
    festgeschrieben_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    festgeschrieben_von: Mapped[int | None] = mapped_column(ForeignKey("nutzer.id"))
    erstellt_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    beleg: Mapped[Beleg | None] = relationship(back_populates="buchungen")
    kategorie: Mapped[Kategorie | None] = relationship()
    kontakt = relationship("Kontakt")
    zahlungen: Mapped[list["Zahlung"]] = relationship(  # noqa: F821
        back_populates="buchung", order_by="Zahlung.id"
    )

    @property
    def ist_entwurf(self) -> bool:
        return self.status == "entwurf"

    @property
    def bezahlt_cent(self) -> int:
        return sum(z.betrag_cent for z in self.zahlungen)

    @property
    def offen_cent(self) -> int:
        if self.storno_von_id is not None or self.storniert:
            return 0
        return self.betrag_cent - self.bezahlt_cent

    @property
    def storniert(self) -> bool:
        return self.storno is not None

    anlagegut = relationship("Anlagegut", uselist=False, viewonly=True)
    storno: Mapped["Buchung | None"] = relationship(
        "Buchung",
        primaryjoin="Buchung.id == foreign(Buchung.storno_von_id)",
        uselist=False,
        viewonly=True,
    )

    @property
    def zahlstatus(self) -> str:
        if self.ist_entwurf:
            return "entwurf"
        if self.storno_von_id is not None or self.storniert:
            return "storniert"
        bezahlt = self.bezahlt_cent
        if bezahlt <= 0:
            return "offen"
        return "bezahlt" if bezahlt >= self.betrag_cent else "teilbezahlt"


class BuchungGebuehr(db.Model):
    """Welche Zahlungsgebühren eine Gebühren-Ausgabe abdeckt.

    Nach einem Storno der Ausgabe darf dieselbe Gebühr erneut gebucht werden.
    """

    __tablename__ = "buchung_gebuehr"

    buchung_id: Mapped[int] = mapped_column(
        ForeignKey("buchung.id", ondelete="CASCADE"), primary_key=True
    )
    zahlung_id: Mapped[int] = mapped_column(
        ForeignKey("zahlung.id", ondelete="RESTRICT"), primary_key=True
    )
