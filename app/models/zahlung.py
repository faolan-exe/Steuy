from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Zahlung(db.Model):
    """Zahlungseingang zu einer Rechnung. Append-only: Korrektur nur per Gegenbuchung."""

    __tablename__ = "zahlung"
    __table_args__ = (
        CheckConstraint(
            "zahlungsart IN ('ueberweisung', 'paypal', 'karte', 'bar', 'sonstige')",
            name="zahlung_art",
        ),
        CheckConstraint(
            "(storno_von_id IS NULL AND betrag_cent > 0) "
            "OR (storno_von_id IS NOT NULL AND betrag_cent < 0)",
            name="zahlung_vorzeichen",
        ),
        CheckConstraint(
            "angekommen_cent IS NULL OR angekommen_cent >= 0", name="zahlung_angekommen"
        ),
        CheckConstraint(
            "(rechnung_id IS NULL) <> (buchung_id IS NULL)", name="zahlung_genau_ein_bezug"
        ),
        CheckConstraint(
            "(nachweis_sha256 IS NULL) = (nachweis_mime IS NULL)", name="zahlung_nachweis"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rechnung_id: Mapped[int | None] = mapped_column(ForeignKey("rechnung.id", ondelete="RESTRICT"))
    buchung_id: Mapped[int | None] = mapped_column(ForeignKey("buchung.id", ondelete="RESTRICT"))
    datum: Mapped[date] = mapped_column(Date)
    betrag_cent: Mapped[int] = mapped_column(BigInteger)
    angekommen_cent: Mapped[int | None] = mapped_column(BigInteger)
    zahlungsart: Mapped[str] = mapped_column(String(20))
    notiz: Mapped[str | None] = mapped_column(Text)
    referenz: Mapped[str | None] = mapped_column(String(100))
    nachweis_sha256: Mapped[str | None] = mapped_column(String(64))
    nachweis_name: Mapped[str | None] = mapped_column(String(255))
    nachweis_mime: Mapped[str | None] = mapped_column(String(50))
    storno_von_id: Mapped[int | None] = mapped_column(
        ForeignKey("zahlung.id", ondelete="RESTRICT"), unique=True
    )
    erfasst_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    erfasst_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rechnung = relationship("Rechnung", back_populates="zahlungen")
    buchung = relationship("Buchung", back_populates="zahlungen")
    storno = relationship("Zahlung", remote_side=[id], uselist=False, viewonly=True)
    erfasser = relationship("Nutzer", viewonly=True)
