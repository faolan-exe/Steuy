from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class ShopBestellung(db.Model):
    """Eine importierte WooCommerce-Bestellung. Eindeutig über die ID im Shop (Idempotenz)."""

    __tablename__ = "shop_bestellung"

    id: Mapped[int] = mapped_column(primary_key=True)
    externe_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    nummer: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    zahlungsart_shop: Mapped[str] = mapped_column(String(60))
    summe_cent: Mapped[int] = mapped_column(BigInteger)
    bezahlt_am: Mapped[date | None] = mapped_column(Date)
    erstattet_cent: Mapped[int] = mapped_column(BigInteger, server_default="0", default=0)
    kontakt_id: Mapped[int | None] = mapped_column(ForeignKey("kontakt.id", ondelete="RESTRICT"))
    rechnung_id: Mapped[int | None] = mapped_column(
        ForeignKey("rechnung.id", ondelete="RESTRICT"), unique=True
    )
    zahlung_id: Mapped[int | None] = mapped_column(ForeignKey("zahlung.id", ondelete="RESTRICT"))
    hinweis: Mapped[str | None] = mapped_column(Text)
    hinweis_erledigt_von: Mapped[int | None] = mapped_column(ForeignKey("nutzer.id"))
    rohdaten: Mapped[dict[str, Any]] = mapped_column(JSONB)
    abrufe: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    importiert_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    aktualisiert_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    kontakt = relationship("Kontakt")
    rechnung = relationship("Rechnung")
    zahlung = relationship("Zahlung")
