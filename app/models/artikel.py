from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Artikel(db.Model):
    """Produkt oder Service mit Verkaufspreis. Ohne Steuersatz (§ 19 UStG)."""

    __tablename__ = "artikel"
    __table_args__ = (CheckConstraint("typ IN ('produkt', 'service')", name="artikel_typ_gueltig"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    typ: Mapped[str] = mapped_column(String(10))
    bezeichnung: Mapped[str] = mapped_column(String(200))
    beschreibung: Mapped[str | None] = mapped_column(Text)
    artikelnummer: Mapped[str | None] = mapped_column(String(50), unique=True)
    gtin: Mapped[str | None] = mapped_column(String(14))
    einheit: Mapped[str] = mapped_column(String(30))
    preis_cent: Mapped[int] = mapped_column(BigInteger)
    notiz: Mapped[str | None] = mapped_column(Text)
    archiviert: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    FELDER = (
        "typ",
        "bezeichnung",
        "beschreibung",
        "artikelnummer",
        "gtin",
        "einheit",
        "preis_cent",
        "notiz",
    )
