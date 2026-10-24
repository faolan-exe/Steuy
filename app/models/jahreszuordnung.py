from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Jahreszuordnung(db.Model):
    """Entscheidung, in welches EÜR-Jahr eine Zahlung am Jahreswechsel gehört.
    Unveränderlich (DB-Trigger), damit nachvollziehbar bleibt, wer was bestätigt hat."""

    __tablename__ = "jahreszuordnung"

    zahlung_id: Mapped[int] = mapped_column(
        ForeignKey("zahlung.id", ondelete="RESTRICT"), primary_key=True
    )
    jahr: Mapped[int] = mapped_column(Integer)
    bestaetigt_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    bestaetigt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    zahlung = relationship("Zahlung")
