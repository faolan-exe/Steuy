from datetime import date, datetime

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
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.mahnung import Stufe
from app.extensions import db


class Mahnstufe(db.Model):
    __tablename__ = "mahnstufe"
    __table_args__ = (
        CheckConstraint("nummer BETWEEN 1 AND 3", name="mahnstufe_nummer"),
        CheckConstraint("tage_nach >= 0 AND frist_tage >= 0", name="mahnstufe_tage"),
    )

    nummer: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    bezeichnung: Mapped[str] = mapped_column(String(60))
    tage_nach: Mapped[int] = mapped_column(Integer)
    frist_tage: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    def als_stufe(self) -> Stufe:
        return Stufe(self.nummer, self.bezeichnung, self.tage_nach, self.frist_tage)


class Mahnung(db.Model):
    """Erstellte Zahlungserinnerung oder Mahnung. Unveränderlich (Trigger)."""

    __tablename__ = "mahnung"
    __table_args__ = (UniqueConstraint("rechnung_id", "stufe", name="mahnung_stufe_einmal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rechnung_id: Mapped[int] = mapped_column(ForeignKey("rechnung.id", ondelete="RESTRICT"))
    stufe: Mapped[int] = mapped_column(Integer)
    bezeichnung: Mapped[str] = mapped_column(String(60))
    datum: Mapped[date] = mapped_column(Date)
    offen_cent: Mapped[int] = mapped_column(BigInteger)
    frist_bis: Mapped[date] = mapped_column(Date)
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    automatisch: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    erstellt_von: Mapped[int] = mapped_column(ForeignKey("nutzer.id"))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    rechnung = relationship("Rechnung", back_populates="mahnungen")
