from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Versand(db.Model):
    """Verschickte E-Mail zu einer Rechnung, einem Angebot oder einer Mahnung. Nur anhängen."""

    __tablename__ = "versand"
    __table_args__ = (
        CheckConstraint("rechnung_id IS NOT NULL OR mahnung_id IS NOT NULL", name="versand_bezug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rechnung_id: Mapped[int | None] = mapped_column(ForeignKey("rechnung.id", ondelete="RESTRICT"))
    mahnung_id: Mapped[int | None] = mapped_column(ForeignKey("mahnung.id", ondelete="RESTRICT"))
    an: Mapped[str] = mapped_column(String(254))
    kopie_an: Mapped[str | None] = mapped_column(String(254))
    betreff: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    anhang: Mapped[str] = mapped_column(String(255))
    erfolgreich: Mapped[bool] = mapped_column(Boolean)
    fehler: Mapped[str | None] = mapped_column(Text)
    gesendet_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    gesendet_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    absender = relationship("Nutzer", viewonly=True)
